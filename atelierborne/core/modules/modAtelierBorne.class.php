<?php
require_once DOL_DOCUMENT_ROOT.'/core/modules/DolibarrModules.class.php';
class modAtelierBorne extends DolibarrModules
{
    public function __construct($db) {
        $this->db=$db; $this->numero=508431; $this->rights_class='atelierborne';
        $this->family='projects'; $this->module_position='90'; $this->name='AtelierBorne';
        $this->description='Borne atelier : projets et taches, mouvements de stock, fabrication de batteries';
        $this->version='0.6.3'; $this->const_name='MAIN_MODULE_ATELIERBORNE';
        $this->picto='project'; $this->editor_name='Bcell - AtelierBorne';
        $this->module_parts=array(); $this->dirs=array(); $this->config_page_url=array();
        $this->depends=array('modApi','modProjet'); $this->requiredby=array(); $this->conflictwith=array();
        $this->phpmin=array(7,4); $this->need_dolibarr_version=array(22,0);
        $this->rights=array(); $this->menu=array(); $this->const=array(); $this->tabs=array();
    }
    public function init($options='') {
        $sql=array();
        $sql[]='CREATE TABLE IF NOT EXISTS '.MAIN_DB_PREFIX.'atelierborne_ops (entity integer NOT NULL, token varchar(36) NOT NULL, kind varchar(20) NOT NULL, request_hash varchar(64) NOT NULL, response longtext, PRIMARY KEY (entity,token)) ENGINE=InnoDB';
        $sql[]='CREATE TABLE IF NOT EXISTS '.MAIN_DB_PREFIX.'atelierborne_trace (rowid integer AUTO_INCREMENT PRIMARY KEY, entity integer NOT NULL, fk_mo integer NOT NULL, document_id varchar(36) NOT NULL, battery_serial varchar(100) NOT NULL, payload longtext, UNIQUE KEY uk_ab_mo (entity,fk_mo), UNIQUE KEY uk_ab_doc (entity,document_id), UNIQUE KEY uk_ab_serial (entity,battery_serial)) ENGINE=InnoDB';
        return $this->_init($sql,$options);
    }
    public function remove($options='') { return $this->_remove(array(),$options); }
}
