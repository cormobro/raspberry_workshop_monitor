<?php
/** AtelierBorne 0.6.3 — native Dolibarr stock entries/exits from the workshop terminal.
 * Tracking follows the product card: 0 = quantity, 1 = lot, 2 = unique serial number.
 * Requires the manufacturing trait (single warehouse, replay protection, serial format). */
trait AtelierStock {
    private static $sReasons=array('reception'=>'Réception fournisseur','retour'=>'Retour','casse'=>'Casse','inventaire'=>'Correction inventaire','consommation'=>'Consommation atelier','autre'=>'Autre');
    private function sActor($write=false) {
        $u=$this->actor();
        if (!isModEnabled('stock')) $this->mFail('Activez le module stock');
        if (!$u->hasRight('stock','lire') || !$u->hasRight('produit','lire')) $this->mFail('Droits requis : lire les produits et les stocks',403);
        if ($write && !$u->hasRight('stock','mouvement','creer')) $this->mFail('Droit Dolibarr requis : créer des mouvements de stock',403);
        require_once DOL_DOCUMENT_ROOT.'/product/class/product.class.php';
        require_once DOL_DOCUMENT_ROOT.'/product/stock/class/mouvementstock.class.php';
        require_once DOL_DOCUMENT_ROOT.'/product/stock/class/productlot.class.php';
        return $u;
    }
    private function sProduct($pid,$lock=false) {
        $rows=$this->mRows('SELECT rowid,ref,label,tobatch,fk_product_type,stockable_product,sell_or_eat_by_mandatory FROM '.MAIN_DB_PREFIX.'product WHERE rowid='.(int)$pid.' AND entity IN ('.getEntity('product').')'.($lock?' FOR UPDATE':''));
        if (!$rows) $this->mFail('Produit introuvable',404);
        return $rows[0];
    }
    private function sTracking($p) { $t=(int)$p['tobatch'];return $t===2?'serial':($t===1?'lot':'none'); }
    private function sQty($pid,$w,$lock=false) {
        $rows=$this->mRows('SELECT rowid,reel FROM '.MAIN_DB_PREFIX.'product_stock WHERE fk_product='.(int)$pid.' AND fk_entrepot='.(int)$w.($lock?' FOR UPDATE':''));
        return $rows?array((int)$rows[0]['rowid'],(float)$rows[0]['reel']):array(0,0.0);
    }
    /** Current quantity of one product in the workshop warehouse, with lots/serials present.
     * @access protected
     * @url GET stock/{id}
     * @param int $id Product id
     * @return array
     */
    public function stockProduct($id) {
        $this->sActor();$p=$this->sProduct($id);$w=$this->mWarehouse();
        list($stockId,$qty)=$this->sQty($p['rowid'],$w);$batches=array();
        if ((int)$p['tobatch'] && $stockId) {
            foreach ($this->mRows('SELECT batch,qty FROM '.MAIN_DB_PREFIX.'product_batch WHERE fk_product_stock='.$stockId.' AND qty>0 ORDER BY batch'.$this->db->plimit(500,0)) as $b)
                $batches[]=array('batch'=>(string)$b['batch'],'qty'=>(float)$b['qty']);
        }
        return array('id'=>(int)$p['rowid'],'ref'=>$p['ref'],'label'=>$p['label'],'physical'=>(int)$p['fk_product_type']===0 && (int)$p['stockable_product']===1,'tracking'=>$this->sTracking($p),'warehouse_id'=>$w,'qty'=>$qty,'batches'=>$batches,'reasons'=>self::$sReasons);
    }
    /** Same as stock/{id}, found by exact product reference (QR codes of the quick scan).
     * @access protected
     * @url GET stockbyref
     * @param string $ref Product reference
     * @return array
     */
    public function stockByRef($ref) {
        $this->sActor();$ref=trim((string)$ref);
        if ($ref==='' || dol_strlen($ref)>128) $this->mFail('Référence produit invalide',400);
        $rows=$this->mRows('SELECT rowid FROM '.MAIN_DB_PREFIX."product WHERE ref='".$this->db->escape($ref)."' AND entity IN (".getEntity('product').')');
        if (!$rows) $this->mFail('Produit « '.$ref.' » introuvable dans Dolibarr',404);
        return $this->stockProduct((int)$rows[0]['rowid']);
    }
    /** Real stock entry or exit, checked again on the server, replay-safe and bound to the operator.
     * @access protected
     * @url POST stock/move
     * @param array $request_data Body
     * @return array
     */
    public function stockMove($request_data=null) {
        $u=$this->sActor(true);$d=(array)$request_data;
        return $this->mOperation('stock',$d,function() use($u,$d) {
            $dir=(string)($d['direction']??'');
            if ($dir!=='in' && $dir!=='out') $this->mFail('Sens de mouvement invalide',400);
            $reason=(string)($d['reason']??'');
            if (!isset(self::$sReasons[$reason])) $this->mFail('Motif inconnu',400);
            $comment=preg_replace('/\s+/u',' ',(string)($d['comment']??''));
            if ($comment===null) $this->mFail('Précision du motif illisible (encodage)',400);
            $comment=trim($comment);
            if (dol_strlen($comment)>200) $this->mFail('Précision du motif trop longue (200 caractères maximum)',400);
            if ($reason==='autre' && dol_strlen($comment)<3) $this->mFail('Précisez le motif « Autre »',400);
            $qty=$d['qty']??null;
            if (!is_numeric($qty) || !is_finite((float)$qty) || (float)$qty<=0 || (float)$qty>1000000) $this->mFail('Quantité invalide',400);
            $qty=(float)$qty;
            // Locking the product row serializes moves even when no stock row exists yet.
            $p=$this->sProduct($d['product_id']??0,true);$pid=(int)$p['rowid'];
            if ((int)$p['fk_product_type']!==0) $this->mFail('Seuls les produits physiques ont un stock');
            // Dolibarr 22 silently skips the movement for a product with stock management disabled.
            if ((int)$p['stockable_product']!==1) $this->mFail('Ce produit n’est pas géré en stock dans Dolibarr (fiche produit)');
            $tracking=$this->sTracking($p);$batch='';
            if ($tracking!=='none') {
                if (!isModEnabled('productbatch')) $this->mFail('Activez le module Lots / Numéros de série');
                $batch=$this->mSerial($d['batch']??'');
            }
            if ($tracking==='serial' && $qty!==1.0) $this->mFail('Un numéro de série correspond à une seule unité',400);
            // A new lot/serial of a product whose card requires an eat-by/sell-by date cannot be created without dates.
            if ($dir==='in' && $tracking!=='none' && (int)$p['sell_or_eat_by_mandatory']>0 && !$this->mRows('SELECT rowid FROM '.MAIN_DB_PREFIX.'product_lot WHERE fk_product='.(int)$p['rowid']." AND batch='".$this->db->escape($batch)."'"))
                $this->mFail('Date limite obligatoire sur ce produit : faites cette première entrée depuis Dolibarr');
            $w=$this->mWarehouse();
            list($stockId,$before)=$this->sQty($pid,$w,true);
            if ($dir==='out') {
                if ($before+0.00000001<$qty) $this->mFail('Stock insuffisant : '.(0+$before).' disponible(s)');
                if ($tracking!=='none') {
                    $r=$stockId?$this->mRows('SELECT rowid,qty FROM '.MAIN_DB_PREFIX.'product_batch WHERE fk_product_stock='.$stockId." AND batch='".$this->db->escape($batch)."' FOR UPDATE"):array();
                    if (!$r || (float)$r[0]['qty']+0.00000001<$qty) $this->mFail($tracking==='serial'?'Ce numéro de série n’est pas en stock dans l’entrepôt : '.$batch:'Quantité insuffisante pour le lot '.$batch);
                }
            } elseif ($tracking==='serial') {
                // Unique per product (Dolibarr behaviour): refuse a serial still present in any warehouse.
                $r=$this->mRows('SELECT pb.rowid FROM '.MAIN_DB_PREFIX.'product_batch pb INNER JOIN '.MAIN_DB_PREFIX.'product_stock ps ON ps.rowid=pb.fk_product_stock WHERE ps.fk_product='.$pid." AND pb.batch='".$this->db->escape($batch)."' AND pb.qty>0 FOR UPDATE");
                if ($r) $this->mFail('Ce numéro de série est déjà en stock : '.$batch);
            }
            $product=new Product($this->db);if ($product->fetch($pid)<=0) $this->mFail('Lecture produit impossible',500);
            $label=dol_trunc('Borne atelier — '.self::$sReasons[$reason].($comment!==''?' : '.$comment:''),240,'right','UTF-8',1);
            $code='AB-'.$d['operation_id'];$sm=new MouvementStock($this->db);
            // Entry valued at the current weighted average price, so the PMP is unchanged.
            $id=$dir==='out'?$sm->livraison($u,$pid,$w,$qty,0,$label,dol_now(),'','',$batch,0,$code):$sm->reception($u,$pid,$w,$qty,(float)$product->pmp,$label,'','',$batch,dol_now(),0,$code);
            if ($id<=0) $this->mFail('Mouvement refusé par Dolibarr : '.($sm->error?:implode(', ',(array)$sm->errors)),500);
            list(,$after)=$this->sQty($pid,$w);
            return array('movement_id'=>(int)$id,'product_id'=>$pid,'ref'=>$p['ref'],'direction'=>$dir,'qty'=>$qty,'batch'=>$batch,'reason'=>$reason,'before'=>$before,'after'=>$after,'operator'=>$u->login,'at'=>date('c'));
        },(int)$u->id);
    }
}
