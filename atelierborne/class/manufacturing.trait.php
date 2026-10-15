<?php
/** AtelierBorne 0.6.2 — native Dolibarr 22 manufacturing, with atomic replay protection. */
trait AtelierManufacturing {
    private function mActor($write=false) {
        $u=$this->actor();
        foreach (array('mrp','bom','stock','productbatch') as $module) if (!isModEnabled($module)) throw new \Luracast\Restler\RestException(409,'Activez le module '.$module);
        if (!$u->hasRight('mrp','read') || ($write && (!$u->hasRight('mrp','write') || !$u->hasRight('stock','mouvement','creer')))) throw new \Luracast\Restler\RestException(403,'Droits requis : lire/écrire les OF et créer des mouvements de stock');
        require_once DOL_DOCUMENT_ROOT.'/mrp/class/mo.class.php';
        require_once DOL_DOCUMENT_ROOT.'/mrp/class/moline.class.php';
        require_once DOL_DOCUMENT_ROOT.'/bom/class/bom.class.php';
        require_once DOL_DOCUMENT_ROOT.'/product/class/product.class.php';
        require_once DOL_DOCUMENT_ROOT.'/product/stock/class/mouvementstock.class.php';
        require_once DOL_DOCUMENT_ROOT.'/product/stock/class/productlot.class.php';
        return $u;
    }
    private function mRows($sql) { $r=$this->query($sql);$a=array();while($o=$this->db->fetch_object($r))$a[]=(array)$o;return $a; }
    private function mFail($message,$code=409) { throw new \Luracast\Restler\RestException($code,$message); }
    private function mWarehouse() {
        global $conf;
        $rows=$this->mRows('SELECT rowid,ref FROM '.MAIN_DB_PREFIX.'entrepot WHERE statut=1 AND entity='.(int)$conf->entity);
        if(count($rows)!==1)$this->mFail('Un seul entrepôt actif est requis pour cette borne');
        return (int)$rows[0]['rowid'];
    }
    private function mMo($id,$lock=false) {
        global $conf;
        $r=$this->mRows('SELECT rowid FROM '.MAIN_DB_PREFIX.'mrp_mo WHERE rowid='.(int)$id.' AND entity='.(int)$conf->entity.($lock?' FOR UPDATE':''));
        if(!$r)$this->mFail('OF introuvable dans cette entité',404);
        $m=new Mo($this->db);if($m->fetch((int)$id)<=0)$this->mFail('Lecture OF impossible',500);
        if((float)$m->qty!==1.0 || (int)$m->mrptype!==0)$this->mFail('Un OF de fabrication doit produire exactement une batterie');
        return $m;
    }
    private function mLines($m) {
        return $this->mRows('SELECT l.rowid as id,l.fk_product as product_id,l.role,l.qty,l.disable_stock_change,p.ref,p.label,p.tobatch,p.fk_product_type FROM '.MAIN_DB_PREFIX.'mrp_production l INNER JOIN '.MAIN_DB_PREFIX.'product p ON p.rowid=l.fk_product WHERE l.fk_mo='.(int)$m->id." AND l.role IN ('toconsume','toproduce') ORDER BY l.rowid");
    }
    private function mSignature($lines) { return hash('sha256',json_encode($lines)); }
    private function mDetails($m) {
        $lines=$this->mLines($m);$p=new Product($this->db);$p->fetch($m->fk_product);
        return array('id'=>(int)$m->id,'ref'=>$m->ref,'bom_id'=>(int)$m->fk_bom,'product_id'=>(int)$m->fk_product,'model'=>$p->ref,'model_label'=>$p->label,'status'=>(int)$m->status,'warehouse_id'=>$this->mWarehouse(),'lines'=>$lines,'signature'=>$this->mSignature($lines));
    }
    /** List available single-battery orders.
     * @access protected
     * @url GET manufacturing/orders
     * @param int $page Page
     * @param int $limit Page size
     * @return array
     */
    public function manufacturingOrders($page=0,$limit=100) {
        global $conf;$this->mActor();
        return $this->mRows('SELECT m.rowid as id,m.ref,m.label,m.status,m.fk_bom,m.fk_product,p.ref as product_ref,p.label as product_label FROM '.MAIN_DB_PREFIX.'mrp_mo m INNER JOIN '.MAIN_DB_PREFIX.'product p ON p.rowid=m.fk_product WHERE m.entity='.(int)$conf->entity.' AND m.qty=1 AND m.mrptype=0 AND m.status IN (0,1,2) ORDER BY m.rowid DESC'.$this->db->plimit(max(1,min(100,(int)$limit)),max(0,(int)$page)*max(1,min(100,(int)$limit))));
    }
    /** List active manufacturing BOMs with the product name used by the operator.
     * @access protected
     * @url GET manufacturing/boms
     * @param int $page Page
     * @param int $limit Page size
     * @return array
     */
    public function manufacturingBoms($page=0,$limit=100) {
        global $conf;$this->mActor();
        return $this->mRows('SELECT b.rowid as id,b.ref as bom_ref,b.label as bom_label,b.fk_product as product_id,p.ref as product_ref,p.label as product_label FROM '.MAIN_DB_PREFIX.'bom_bom b INNER JOIN '.MAIN_DB_PREFIX.'product p ON p.rowid=b.fk_product WHERE b.entity='.(int)$conf->entity.' AND b.status=1 AND b.bomtype=0 ORDER BY p.label,p.ref,b.ref'.$this->db->plimit(max(1,min(100,(int)$limit)),max(0,(int)$page)*max(1,min(100,(int)$limit))));
    }
    /** Read order and expected components.
     * @access protected
     * @url GET manufacturing/orders/{id}
     * @param int $id Order id
     * @return array
     */
    public function manufacturingOrder($id) { $this->mActor();return $this->mDetails($this->mMo($id)); }
    /** Delete a native draft MO without touching stock.
     * @access protected
     * @url POST manufacturing/delete
     * @param array $request_data Body
     * @return array
     */
    public function manufacturingDelete($request_data=null) {
        $u=$this->mActor(true);$d=(array)$request_data;
        if (!$u->hasRight('mrp','delete')) $this->mFail('Droit Dolibarr requis : supprimer les ordres de fabrication',403);
        return $this->mOperation('delete',$d,function() use($d,$u) {
            $m=$this->mMo($d['mo_id']??0,true);
            if ((int)$m->status<0 || (int)$m->status>2) $this->mFail('Cet OF est terminé ou annulé et ne peut pas être supprimé.',409);
            $used=$this->mRows("SELECT rowid FROM ".MAIN_DB_PREFIX."mrp_production WHERE fk_mo=".(int)$m->id." AND role IN ('consumed','produced')");
            if ($used) $this->mFail('Cet OF contient déjà un mouvement de production et ne peut pas être supprimé.',409);
            if ($m->delete($u,0,true)<=0) $this->mFail('Suppression de l’OF refusée : '.$m->error,500);
            return array('deleted'=>true,'mo_id'=>(int)$d['mo_id']);
        });
    }
    /** Create one order using a live BOM.
     * @access protected
     * @url POST manufacturing/create
     * @param array $request_data Body
     * @return array
     */
    public function manufacturingCreate($request_data=null) {
        $u=$this->mActor(true);$d=(array)$request_data;
        return $this->mOperation('create',$d,function() use($d,$u) {
            global $conf;
            $bomRef=trim((string)($d['bom_ref']??''));
            $b=new BOM($this->db);
            if ($bomRef==='') $this->mFail('Référence de nomenclature vide',400);
            if ($b->fetch(0,$bomRef)<=0) $this->mFail('Nomenclature « '.$bomRef.' » introuvable dans l’entité '.$conf->entity.' : vérifiez la référence exacte.',404);
            // BOM does not expose entity as a public property in Dolibarr 22;
            // read the authoritative row explicitly instead of treating it as 0.
            $meta=$this->mRows('SELECT entity,status,bomtype FROM '.MAIN_DB_PREFIX.'bom_bom WHERE rowid='.(int)$b->id);
            if (!$meta) $this->mFail('Métadonnées introuvables pour la nomenclature « '.$bomRef.' ».',500);
            $meta=$meta[0];
            if ((int)$meta['entity']!==(int)$conf->entity) $this->mFail('Nomenclature « '.$bomRef.' » trouvée dans l’entité '.$meta['entity'].' au lieu de l’entité '.$conf->entity.'.',409);
            if ((int)$meta['status']!==1) $this->mFail('Nomenclature « '.$bomRef.' » trouvée mais non active (statut '.$meta['status'].'). Validez-la dans Dolibarr.',409);
            if ((int)$meta['bomtype']!==0) $this->mFail('Nomenclature « '.$bomRef.' » configurée en démontage. Une nomenclature de fabrication est requise.',409);
            $m=new Mo($this->db);$m->entity=$conf->entity;$m->ref='(PROV)';$m->fk_bom=$b->id;$m->fk_product=$b->fk_product;$m->qty=1;$m->status=0;$m->fk_warehouse=$this->mWarehouse();$m->label='Atelier — '.$b->ref;
            if($m->create($u)<=0)$this->mFail('Création OF : '.$m->error,500);
            if($m->validate($u)<=0)$this->mFail('Validation OF : '.$m->error,500);
            return $this->mDetails($this->mMo($m->id));
        });
    }
    private function mOperation($kind,$d,$fn,$actorId=0) {
        global $conf;
        $token=(string)($d['operation_id']??'');if(!preg_match('/^[a-f0-9-]{36}$/D',$token))$this->mFail('Identifiant de requête invalide',400);
        // $actorId binds a replay to the user who first sent it (stock moves). Left at 0
        // for manufacturing so operations pending from 0.5.5 keep their original hash.
        $hash=hash('sha256',json_encode($d).($actorId?'|user:'.(int)$actorId:''));$where='entity='.(int)$conf->entity." AND token='".$this->db->escape($token)."'";
        $this->db->begin();
        try {
            // The unique key also serializes simultaneous retries of one operation.
            $this->query('INSERT INTO '.MAIN_DB_PREFIX."atelierborne_ops (entity,token,kind,request_hash) VALUES (".(int)$conf->entity.",'".$this->db->escape($token)."','".$kind."','".$hash."') ON DUPLICATE KEY UPDATE token=token");
            $r=$this->mRows('SELECT * FROM '.MAIN_DB_PREFIX.'atelierborne_ops WHERE '.$where.' FOR UPDATE')[0];
            if($r['request_hash']!==$hash || $r['kind']!==$kind)$this->mFail('Cette requête a déjà été utilisée avec un autre contenu');
            if(!empty($r['response'])){$result=json_decode($r['response'],true);$this->db->commit();return $result;}
            $result=$fn();$this->query('UPDATE '.MAIN_DB_PREFIX."atelierborne_ops SET response='".$this->db->escape(json_encode($result))."' WHERE ".$where);
            $this->db->commit();return $result;
        } catch(\Throwable $e) {$this->db->rollback();throw $e;}
    }
    private function mSerial($s) {
        $s=trim((string)$s);if(!preg_match('/^[A-Za-z0-9][A-Za-z0-9._:\/-]{0,99}$/D',$s))$this->mFail('Numéro de série vide ou invalide',400);return $s;
    }
    private function mNumber($v,$label,$zero=false) {
        if(!is_numeric($v) || !is_finite((float)$v) || ($zero?(float)$v<0:(float)$v<=0))$this->mFail('Mesure obligatoire invalide : '.$label,400);
    }
    private function mLockStock($pid,$warehouse,$qty,$serial='') {
        $rows=$this->mRows('SELECT rowid,reel FROM '.MAIN_DB_PREFIX.'product_stock WHERE fk_product='.(int)$pid.' AND fk_entrepot='.(int)$warehouse.' FOR UPDATE');
        if(!$rows || (float)$rows[0]['reel']+0.00000001<$qty)$this->mFail('Stock insuffisant pour le produit '.$pid);
        if($serial!=='') {
            $r=$this->mRows('SELECT rowid,qty FROM '.MAIN_DB_PREFIX.'product_batch WHERE fk_product_stock='.(int)$rows[0]['rowid']." AND batch='".$this->db->escape($serial)."' FOR UPDATE");
            if(count($r)!==1 || (float)$r[0]['qty']!==1.0 || $qty!==1.0)$this->mFail('Numéro absent ou quantité différente de 1 : '.$serial);
        }
    }
    /** Check a scanned serial against actual stock.
     * @access protected
     * @url GET manufacturing/serial
     * @param int $product_id Product id
     * @param string $serial Serial
     * @return array
     */
    public function manufacturingSerial($product_id,$serial) {
        $this->mActor();$serial=$this->mSerial($serial);$this->db->begin();
        try {$this->mLockStock((int)$product_id,$this->mWarehouse(),1.0,$serial);$this->db->commit();return array('available'=>true,'serial'=>$serial);}
        catch(\Throwable $e){$this->db->rollback();throw $e;}
    }
    private function mDocument($d,$lines) {
        $f=(array)($d['fields']??array());$this->mSerial($f['battery_serial']??'');$this->mSerial($f['seal']??'');
        if(($f['calibration_result']??'')!=='Conforme')$this->mFail('Le calibrage doit être déclaré conforme');
        foreach(array('pack_voltage','pack_ir','capacity_ah') as $k)$this->mNumber($f[$k]??null,$k,$k==='pack_ir');
        for($i=1;$i<=16;$i++){ $this->mNumber($f['cell_'.$i.'_voltage']??null,'C'.$i.' tension');$this->mNumber($f['cell_'.$i.'_ir']??null,'C'.$i.' résistance',true); }
        if(empty($f['assembly_operator']) || empty($f['calibration_operator']))$this->mFail('Opérateurs des étapes manquants');
        if(strlen(json_encode($d))>150000)$this->mFail('Fiche trop volumineuse',400);
        return $f;
    }
    private function mNote($fields,$title) {
        $s='<h3>'.htmlspecialchars($title,ENT_QUOTES,'UTF-8').'</h3><table>';
        foreach($fields as $k=>$v)if(is_scalar($v))$s.='<tr><td>'.htmlspecialchars((string)$k,ENT_QUOTES,'UTF-8').'</td><td>'.htmlspecialchars((string)$v,ENT_QUOTES,'UTF-8').'</td></tr>';
        return $s.'</table>';
    }
    /** Final manufacturing, all movements in a single transaction.
     * @access protected
     * @url POST manufacturing/finalize
     * @param array $request_data Body
     * @return array
     */
    public function manufacturingFinalize($request_data=null) {
        $u=$this->mActor(true);$d=(array)$request_data;
        return $this->mOperation('finalize',$d,function() use($u,$d) {
            global $conf;
            $m=$this->mMo($d['mo_id']??0,true);$lines=$this->mLines($m);$w=$this->mWarehouse();
            if(!in_array((int)$m->status,array(0,1,2),true))$this->mFail('Cet OF est déjà terminé ou annulé');
            if($this->mSignature($lines)!==($d['signature']??''))$this->mFail('Les composants de l’OF ont changé. Rechargez l’OF avant de valider');
            if(!preg_match('/^[a-f0-9-]{36}$/D',(string)($d['document_id']??'')))$this->mFail('Identifiant de fiche invalide',400);
            $f=$this->mDocument($d,$lines);
            foreach($lines as $cl)if((int)$cl['id']===(int)($d['cell_line_id']??0)){
                if($cl['role']!=='toconsume' || (float)$cl['qty']!==16.0)$this->mFail('Ligne cellules invalide');
                if((int)$cl['tobatch'])for($ci=1;$ci<=16;$ci++)if(($f['cell_'.$ci.'_serial']??'')!==($f['serial_'.$cl['id'].'_'.$ci]??''))$this->mFail('Correspondance des positions de cellules incohérente');
            }
            $serial=$this->mSerial($f['battery_serial']);
            $existing=$this->mRows('SELECT rowid FROM '.MAIN_DB_PREFIX."mrp_production WHERE fk_mo=".(int)$m->id." AND role IN ('consumed','produced')");if($existing)$this->mFail('OF déjà partiellement consommé/produit : terminez-le dans Dolibarr');
            // Lock product rows in a stable order, including the output product.
            $ids=array_unique(array_map(function($l){return (int)$l['product_id'];},$lines));sort($ids);
            foreach($ids as $pid)$this->mRows('SELECT rowid FROM '.MAIN_DB_PREFIX.'product WHERE rowid='.$pid.' FOR UPDATE');
            $prior=$this->mRows('SELECT rowid FROM '.MAIN_DB_PREFIX.'product_lot WHERE fk_product='.(int)$m->fk_product." AND batch='".$this->db->escape($serial)."'");if($prior)$this->mFail('Ce numéro de batterie existe déjà dans Dolibarr');
            $moves=array();$seen=array();$outputs=0;$cost=0;
            foreach($lines as $l){
                $qty=(float)$l['qty'];if($qty<=0)$this->mFail('Quantité de nomenclature invalide');
                if((int)$l['fk_product_type']!==0 || (int)$l['disable_stock_change']!==0)$this->mFail('Cette version nécessite des composants physiques avec mouvement de stock actif');
                if($l['role']==='toproduce'){
                    $outputs++;if($qty!==1.0 || (int)$l['product_id']!==(int)$m->fk_product || !(int)$l['tobatch'])$this->mFail('Le produit fini doit être suivi par numéro de série, quantité 1');
                    $moves[]=array($l,1.0,$serial);continue;
                }
                $cp=new Product($this->db);if($cp->fetch($l['product_id'])<=0)$this->mFail('Produit introuvable');$cost+=(float)$cp->pmp*$qty;
                if(preg_match('/bms|balanc|equilib/i',$l['ref'].' '.$l['label']) && !(int)$l['tobatch'])$this->mFail('Activez le suivi par série pour '.$l['ref']);
                if((int)$l['tobatch']){
                    if($qty!==floor($qty) || $qty>100)$this->mFail('Quantité sérialisée non entière ou excessive');
                    for($i=1;$i<=$qty;$i++){
                        $s=$this->mSerial($f['serial_'.$l['id'].'_'.$i]??'');
                        $key=$l['product_id'].'|'.strtolower($s);if(isset($seen[$key]))$this->mFail('Composant scanné deux fois : '.$s);$seen[$key]=true;
                        $moves[]=array($l,1.0,$s);
                    }
                }else $moves[]=array($l,$qty,'');
            }
            if($outputs!==1)$this->mFail('Un seul produit fini attendu');
            // Aggregate repeated product lines before checking available stock.
            $totals=array();foreach($moves as $v)if($v[0]['role']==='toconsume'){$pid=$v[0]['product_id'];$totals[$pid]=($totals[$pid]??0)+$v[1];}
            foreach($totals as $pid=>$qty)$this->mLockStock($pid,$w,$qty);
            foreach($moves as $v)if($v[0]['role']==='toconsume' && $v[2]!=='')$this->mLockStock($v[0]['product_id'],$w,$v[1],$v[2]);
            if((int)$m->status===0 && $m->validate($u)<=0)$this->mFail('Validation OF impossible',500);
            foreach($moves as $v){
                list($l,$qty,$batch)=$v;$sm=new MouvementStock($this->db);$sm->setOrigin($m->element,$m->id);$sm->context['mrp_role']=$l['role'];$code='AB-'.$d['operation_id'];
                $movement=$l['role']==='toconsume'?$sm->livraison($u,$l['product_id'],$w,$qty,0,'Atelier '.$m->ref,dol_now(),'','',$batch,0,$code):$sm->reception($u,$l['product_id'],$w,$qty,$cost,'Atelier '.$m->ref,'','',$batch,dol_now(),0,$code);
                if($movement<=0)$this->mFail('Mouvement refusé : '.$sm->error,500);
                $ml=new MoLine($this->db);$ml->fk_mo=$m->id;$ml->fk_product=$l['product_id'];$ml->fk_warehouse=$w;$ml->qty=$qty;$ml->batch=$batch;$ml->role=$l['role']==='toconsume'?'consumed':'produced';$ml->fk_mrp_production=$l['id'];$ml->fk_stock_movement=$movement;$ml->position=1;$ml->fk_user_creat=$u->id;
                if($ml->create($u)<=0)$this->mFail('Ligne de production refusée : '.$ml->error,500);
            }
            $f['validation_user']=$u->login;$f['validation_date']=date('c');$note=$this->mNote($f,'Atelier — batterie '.$serial);
            if($m->update_note(($m->note_public??'').$note,'_public',0)<=0)$this->mFail('Enregistrement de la traçabilité refusé',500);
            $lot=new Productlot($this->db);if($lot->fetch(0,$m->fk_product,$serial)<=0 || $lot->update_note(($lot->note_public??'').$note,'_public',0)<=0)$this->mFail('Traçabilité du numéro de batterie non enregistrée',500);
            if($m->setStatut(Mo::STATUS_PRODUCED,0,'','MRP_MO_PRODUCED')<=0)$this->mFail('Clôture OF refusée',500);
            $this->query('INSERT INTO '.MAIN_DB_PREFIX."atelierborne_trace (entity,fk_mo,document_id,battery_serial,payload) VALUES (".(int)$conf->entity.','.(int)$m->id.",'".$this->db->escape($d['document_id'])."','".$this->db->escape($serial)."','".$this->db->escape(json_encode($d))."')");
            return array('mo_id'=>(int)$m->id,'mo_ref'=>$m->ref,'battery_serial'=>$serial,'status'=>'completed','validated_by'=>$u->login,'validated_at'=>$f['validation_date']);
        });
    }
    /** Scrap a defective component, without counting it as an OF consumption.
     * @access protected
     * @url POST manufacturing/scrap
     * @param array $request_data Body
     * @return array
     */
    public function manufacturingScrap($request_data=null) {
        $u=$this->mActor(true);$d=(array)$request_data;
        return $this->mOperation('scrap',$d,function()use($u,$d){
            $m=$this->mMo($d['mo_id']??0,true);if(!in_array((int)$m->status,array(0,1,2),true))$this->mFail('OF terminé ou annulé');
            $line=null;foreach($this->mLines($m) as $l)if((int)$l['id']===(int)($d['line_id']??0) && $l['role']==='toconsume')$line=$l;
            if(!$line)$this->mFail('Composant étranger à cet OF');$reason=trim((string)($d['reason']??''));if(strlen($reason)<3)$this->mFail('Motif de rebut obligatoire');
            $s=(int)$line['tobatch']?$this->mSerial($d['serial']??''):'';$w=$this->mWarehouse();$this->mLockStock($line['product_id'],$w,1.0,$s);
            $sm=new MouvementStock($this->db);$sm->setOrigin($m->element,$m->id);$id=$sm->livraison($u,$line['product_id'],$w,1,0,'REBUT Atelier '.$m->ref.' : '.$reason,dol_now(),'','',$s,0,'AB-'.$d['operation_id']);if($id<=0)$this->mFail('Rebut refusé : '.$sm->error,500);
            return array('movement_id'=>(int)$id,'serial'=>$s,'reason'=>$reason,'operator'=>$u->login);
        });
    }
    /** Append corrections to an already completed battery record; no stock movement.
     * @access protected
     * @url POST manufacturing/correction
     * @param array $request_data Body
     * @return array
     */
    public function manufacturingCorrection($request_data=null) {
        $u=$this->mActor(true);$d=(array)$request_data;
        return $this->mOperation('correction',$d,function()use($u,$d){
            global $conf;$m=$this->mMo($d['mo_id']??0,true);
            $rows=$this->mRows('SELECT rowid,battery_serial FROM '.MAIN_DB_PREFIX.'atelierborne_trace WHERE entity='.(int)$conf->entity.' AND fk_mo='.(int)$m->id." AND document_id='".$this->db->escape($d['document_id']??'')."'");if(!$rows)$this->mFail('Fiche terminée introuvable');
            $fields=(array)($d['fields']??array());if(strlen(json_encode($fields))>150000)$this->mFail('Fiche trop volumineuse');
            $note=$this->mNote($fields,'Correction documentaire '.date('c').' — '.$u->login.' (stock inchangé)');
            if($m->update_note(($m->note_public??'').$note,'_public',0)<=0)$this->mFail('Correction non enregistrée',500);
            $lot=new Productlot($this->db);if($lot->fetch(0,$m->fk_product,$rows[0]['battery_serial'])<=0 || $lot->update_note(($lot->note_public??'').$note,'_public',0)<=0)$this->mFail('Correction de la fiche série refusée',500);
            return array('saved'=>true,'stock_changed'=>false);
        });
    }
}
