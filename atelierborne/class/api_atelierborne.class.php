<?php
/** AtelierBorne 0.6.3 — endpoints for authenticated internal users. */
use Luracast\Restler\RestException;
require_once DOL_DOCUMENT_ROOT.'/projet/class/project.class.php';
require_once DOL_DOCUMENT_ROOT.'/projet/class/task.class.php';

/** Workshop API.
 * @class DolibarrApiAccess {@requires user}
 * @access protected
 */
require_once __DIR__.'/manufacturing.trait.php';
require_once __DIR__.'/stock.trait.php';

/** @access protected
 * @class DolibarrApiAccess {@requires user}
 */
class Atelierborne extends DolibarrApi
{
    use AtelierManufacturing;
    use AtelierStock;
    const VERSION='0.6.3';
    public function __construct() { global $db; $this->db=$db; }
    private function actor($projects=false) {
        // @access protected makes Restler run Dolibarr's authentication,
        // account validity checks and permission loading before this method.
        $u = DolibarrApiAccess::$user;
        if (!is_object($u) || empty($u->id)) throw new RestException(401,'Authenticated Dolibarr user required');
        if ((int) $u->socid > 0) throw new RestException(403,'Internal user required');
        if ($projects && !$u->hasRight('projet','lire') && !$u->hasRight('projet','all','lire')) throw new RestException(403,'Project read permission required');
        return $u;
    }
    private function query($sql) {
        $res=$this->db->query($sql);
        if (!$res) throw new RestException(500,'Database operation failed');
        return $res;
    }
    private function scope($u) {
        if ($u->hasRight('projet','all','lire')) return "p.entity IN (".getEntity('project').")";
        return "p.entity IN (".getEntity('project').") AND (p.public=1 OR EXISTS (SELECT 1 FROM ".MAIN_DB_PREFIX."element_contact ec INNER JOIN ".MAIN_DB_PREFIX."c_type_contact ct ON ct.rowid=ec.fk_c_type_contact WHERE ec.element_id=p.rowid AND ec.statut=4 AND ct.element='project' AND ct.source='internal' AND ec.fk_socpeople=".(int)$u->id."))";
    }
    private function assignments($id,$u) {
        $res=$this->query("SELECT ec.fk_socpeople,ct.source FROM ".MAIN_DB_PREFIX."element_contact ec INNER JOIN ".MAIN_DB_PREFIX."c_type_contact ct ON ct.rowid=ec.fk_c_type_contact WHERE ec.element_id=".(int)$id." AND ec.statut=4 AND ct.element='project_task' AND ct.code='TASKEXECUTIVE'");
        $count=0; $mine=false;
        while ($row=$this->db->fetch_object($res)) { $count++; if ($row->source==='internal' && (int)$row->fk_socpeople===(int)$u->id) $mine=true; }
        return array('assigned_count'=>$count,'mine'=>$mine);
    }
    /** Current API identity and permissions.
     * @access protected
     * @url GET identity
     * @return array
     */
    public function identity() {
        $u=$this->actor();
        return array('id'=>(int)$u->id,'login'=>$u->login,'name'=>trim($u->firstname.' '.$u->lastname),'can_read_stock'=>(bool)$u->hasRight('stock','lire'),'can_read_products'=>(bool)$u->hasRight('produit','lire'),'can_read_projects'=>(bool)($u->hasRight('projet','lire') || $u->hasRight('projet','all','lire')),'can_claim'=>(bool)$u->hasRight('projet','creer'),'can_move_stock'=>(bool)(isModEnabled('stock') && $u->hasRight('stock','lire') && $u->hasRight('stock','mouvement','creer')),'can_delete_mo'=>(bool)$u->hasRight('mrp','delete'),'version'=>self::VERSION);
    }
    /** Shared projects and projects where the current user is an active internal contact,
     * with task counters (total, done at 100 %, available to claim).
     * @access protected
     * @url GET projects
     * @param int $page Page, starting at zero
     * @param int $limit Page length, maximum 100
     * @return array
     */
    public function projects($page=0,$limit=100) {
        $u=$this->actor(true); $limit=max(1,min(100,(int)$limit)); $page=max(0,(int)$page);
        $res=$this->query("SELECT p.rowid as id,p.ref,p.title,p.public,p.fk_statut as status,"
            ."(SELECT COUNT(*) FROM ".MAIN_DB_PREFIX."projet_task t WHERE t.fk_projet=p.rowid) as tasks_total,"
            ."(SELECT COUNT(*) FROM ".MAIN_DB_PREFIX."projet_task t WHERE t.fk_projet=p.rowid AND COALESCE(t.progress,0)>=100) as tasks_done,"
            ."(SELECT COUNT(*) FROM ".MAIN_DB_PREFIX."projet_task t WHERE t.fk_projet=p.rowid AND p.fk_statut=1 AND COALESCE(t.progress,0)<100 AND NOT EXISTS (SELECT 1 FROM ".MAIN_DB_PREFIX."element_contact ec INNER JOIN ".MAIN_DB_PREFIX."c_type_contact ct ON ct.rowid=ec.fk_c_type_contact WHERE ec.element_id=t.rowid AND ec.statut=4 AND ct.element='project_task' AND ct.code='TASKEXECUTIVE')) as tasks_available"
            ." FROM ".MAIN_DB_PREFIX."projet p WHERE ".$this->scope($u)." ORDER BY p.rowid".$this->db->plimit($limit,$page*$limit));
        $rows=array();while ($row=$this->db->fetch_object($res)) $rows[]=$row;
        return $rows;
    }
    /** Tasks of visible projects, optionally restricted to available tasks.
     * @access protected
     * @url GET tasks
     * @param int $project_id Project identifier or zero for all visible projects
     * @param int $available One to include only unassigned unfinished tasks of open projects
     * @param int $page Page, starting at zero
     * @param int $limit Page length, maximum 100
     * @param int $mine One to include only unfinished tasks assigned to the current user
     * @return array
     */
    public function tasks($project_id=0,$available=0,$page=0,$limit=100,$mine=0) {
        $u=$this->actor(true);$limit=max(1,min(100,(int)$limit));$page=max(0,(int)$page);
        $sql="SELECT t.rowid as id,t.ref,t.label,t.progress,t.fk_projet as project_id,p.title as project_title,p.fk_statut as project_status FROM ".MAIN_DB_PREFIX."projet_task t INNER JOIN ".MAIN_DB_PREFIX."projet p ON p.rowid=t.fk_projet WHERE ".$this->scope($u);
        if ((int)$project_id>0) $sql.=' AND p.rowid='.(int)$project_id;
        if ($available) $sql.=" AND p.fk_statut=1 AND COALESCE(t.progress,0)<100 AND NOT EXISTS (SELECT 1 FROM ".MAIN_DB_PREFIX."element_contact ec INNER JOIN ".MAIN_DB_PREFIX."c_type_contact ct ON ct.rowid=ec.fk_c_type_contact WHERE ec.element_id=t.rowid AND ec.statut=4 AND ct.element='project_task' AND ct.code='TASKEXECUTIVE')";
        if ($mine) $sql.=" AND p.fk_statut=1 AND COALESCE(t.progress,0)<100 AND EXISTS (SELECT 1 FROM ".MAIN_DB_PREFIX."element_contact ec INNER JOIN ".MAIN_DB_PREFIX."c_type_contact ct ON ct.rowid=ec.fk_c_type_contact WHERE ec.element_id=t.rowid AND ec.statut=4 AND ct.element='project_task' AND ct.code='TASKEXECUTIVE' AND ct.source='internal' AND ec.fk_socpeople=".(int)$u->id.")";
        $sql.=' ORDER BY t.rowid'.$this->db->plimit($limit,$page*$limit);
        $res=$this->query($sql);$rows=array();
        while ($row=$this->db->fetch_object($res)) $rows[]=(array)$row;
        foreach ($rows as &$row) { $row=array_merge($row,$this->assignments($row['id'],$u)); }
        unset($row);return $rows;
    }
    /** Assign a currently free task to the authenticated API user only.
     * @access protected
     * @url POST tasks/{id}/claim
     * @param int $id Task identifier
     * @return array
     */
    public function claim($id) {
        $u=$this->actor(true);
        if (!$u->hasRight('projet','creer')) throw new RestException(403,'Project create/modify permission required');
        $id=(int)$id;if ($id<=0) throw new RestException(400,'Invalid task');
        $this->db->begin();
        try {
            // All terminal claims lock the same native task row before checking assignments.
            $lock=$this->query('SELECT rowid FROM '.MAIN_DB_PREFIX.'projet_task WHERE rowid='.$id.' FOR UPDATE');
            if (!$this->db->fetch_object($lock)) throw new RestException(404,'Task not found');
            $res=$this->query('SELECT t.progress,p.fk_statut FROM '.MAIN_DB_PREFIX.'projet_task t INNER JOIN '.MAIN_DB_PREFIX.'projet p ON p.rowid=t.fk_projet WHERE t.rowid='.$id.' AND '.$this->scope($u));
            $row=$this->db->fetch_object($res);
            if (!$row) throw new RestException(403,'Project access denied');
            $assignment=$this->assignments($id,$u);
            // Retrying the same user's claim after a lost response is harmless.
            if ($assignment['mine']) { $this->db->commit();return array('task_id'=>$id,'user_id'=>(int)$u->id,'already_assigned'=>true); }
            if ($assignment['assigned_count']>0) throw new RestException(409,'Task already assigned');
            if ((int)$row->fk_statut!==1 || (int)$row->progress>=100) throw new RestException(409,'Task is not available');
            $task=new Task($this->db);
            if ($task->fetch($id)<=0) throw new RestException(404,'Task not found');
            // Native contact triggers use the global user for their audit actor.
            $previousUser=isset($GLOBALS['user'])?$GLOBALS['user']:null;
            $GLOBALS['user']=$u;
            try { $result=$task->add_contact((int)$u->id,'TASKEXECUTIVE','internal'); }
            finally { $GLOBALS['user']=$previousUser; }
            if ($result<=0) throw new RestException(500,'Could not assign task');
            $this->db->commit();
            return array('task_id'=>$id,'user_id'=>(int)$u->id,'already_assigned'=>false);
        } catch (\Throwable $e) { $this->db->rollback();throw $e; }
    }

    /** Lock a task visible to the user; returns project status and progress.
     * Must be called inside a transaction. */
    private function lockedTask($id,$u) {
        $lock=$this->query('SELECT rowid FROM '.MAIN_DB_PREFIX.'projet_task WHERE rowid='.(int)$id.' FOR UPDATE');
        if (!$this->db->fetch_object($lock)) throw new RestException(404,'Task not found');
        $res=$this->query('SELECT t.progress,p.fk_statut FROM '.MAIN_DB_PREFIX.'projet_task t INNER JOIN '.MAIN_DB_PREFIX.'projet p ON p.rowid=t.fk_projet WHERE t.rowid='.(int)$id.' AND '.$this->scope($u));
        $row=$this->db->fetch_object($res);
        if (!$row) throw new RestException(403,'Project access denied');
        return $row;
    }
    /** Run a native Task method with the API user as audit actor for triggers. */
    private function asUser($u,$fn) {
        $previousUser=isset($GLOBALS['user'])?$GLOBALS['user']:null;
        $GLOBALS['user']=$u;
        try { return $fn(); } finally { $GLOBALS['user']=$previousUser; }
    }
    /** Remove only the current user's executive assignment; other contacts and progress are kept.
     * @access protected
     * @url POST tasks/{id}/unassign
     * @param int $id Task identifier
     * @return array
     */
    public function unassign($id) {
        $u=$this->actor(true);
        if (!$u->hasRight('projet','creer')) throw new RestException(403,'Project create/modify permission required');
        $id=(int)$id;if ($id<=0) throw new RestException(400,'Invalid task');
        $this->db->begin();
        try {
            $this->lockedTask($id,$u);
            $res=$this->query("SELECT ec.rowid FROM ".MAIN_DB_PREFIX."element_contact ec INNER JOIN ".MAIN_DB_PREFIX."c_type_contact ct ON ct.rowid=ec.fk_c_type_contact WHERE ec.element_id=".$id." AND ec.statut=4 AND ct.element='project_task' AND ct.code='TASKEXECUTIVE' AND ct.source='internal' AND ec.fk_socpeople=".(int)$u->id);
            $links=array();while ($row=$this->db->fetch_object($res)) $links[]=(int)$row->rowid;
            // Retrying after a lost response is harmless: nothing left to remove.
            if (!$links) { $this->db->commit();return array('task_id'=>$id,'user_id'=>(int)$u->id,'already_unassigned'=>true); }
            $task=new Task($this->db);
            if ($task->fetch($id)<=0) throw new RestException(404,'Task not found');
            foreach ($links as $link) {
                $result=$this->asUser($u,function() use($task,$link){ return $task->delete_contact($link); });
                if ($result<=0) throw new RestException(500,'Could not unassign task');
            }
            $this->db->commit();
            return array('task_id'=>$id,'user_id'=>(int)$u->id,'already_unassigned'=>false);
        } catch (\Throwable $e) { $this->db->rollback();throw $e; }
    }
    /** Set progress to 100 % (status closed) for a task of an open project assigned to the current user.
     * The terminal never changes the project itself; Dolibarr may close it natively when
     * PROJECT_CLASSIFY_CLOSED_WHEN_ALL_TASKS_DONE is enabled and this was its last open task.
     * @access protected
     * @url POST tasks/{id}/complete
     * @param int $id Task identifier
     * @return array
     */
    public function complete($id) {
        $u=$this->actor(true);
        if (!$u->hasRight('projet','creer')) throw new RestException(403,'Project create/modify permission required');
        $id=(int)$id;if ($id<=0) throw new RestException(400,'Invalid task');
        $this->db->begin();
        try {
            $row=$this->lockedTask($id,$u);
            if (!$this->assignments($id,$u)['mine']) throw new RestException(409,'Task is not assigned to you');
            if ((int)$row->progress>=100) { $this->db->commit();return array('task_id'=>$id,'progress'=>100,'already_completed'=>true); }
            if ((int)$row->fk_statut!==1) throw new RestException(409,'Project is not open');
            $task=new Task($this->db);
            if ($task->fetch($id)<=0) throw new RestException(404,'Task not found');
            $task->progress=100;$task->status=Task::STATUS_CLOSED;
            $result=$this->asUser($u,function() use($task,$u){ return $task->update($u); });
            if ($result<=0) throw new RestException(500,'Could not complete task');
            $this->db->commit();
            return array('task_id'=>$id,'progress'=>100,'already_completed'=>false);
        } catch (\Throwable $e) { $this->db->rollback();throw $e; }
    }
}
