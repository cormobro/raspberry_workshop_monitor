import copy,json,tempfile,unittest
from pathlib import Path
from manufacturing import ManufacturingStore,assembly_validation,final_validation
from manufacturing_excel import three_way,export_local,sync_nas,MergeConflict,library

def order(ident=1):
    return {'id':ident,'ref':f'MO-{ident}','model':'MASON','signature':'abc','lines':[{'id':11,'product_id':101,'ref':'BMS','qty':1,'tobatch':2,'role':'toconsume'},{'id':12,'product_id':102,'ref':'CELL','qty':16,'tobatch':0,'role':'toconsume'}]}
def fill(job):
    f=job['fields'];f.update(battery_serial='BAT-1',serial_11_1='BMS-1',pack_voltage='52.3',pack_ir='5.2',capacity_ah='314',seal='SEAL-1',calibration_result='Conforme')
    for i in range(1,17):f[f'cell_{i}_voltage']='3.27';f[f'cell_{i}_ir']='0.2'
    return job

class ManufacturingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.s=ManufacturingStore(self.root/'data.sqlite3');self.j=self.s.create(order(),'HASMAN')
    def tearDown(self):self.s.db.close();self.tmp.cleanup()
    def test_resume_and_single_order(self):
        self.assertEqual(self.s.create(order(),'TOKY')['id'],self.j['id']);self.assertEqual(len(self.s.all()),1)
    def test_measurements_and_stages(self):
        with self.assertRaises(ValueError):self.s.transition(self.j['id'],'HASMAN')
        j=self.s.save(fill(self.j),'HASMAN');j=self.s.transition(j['id'],'HASMAN');self.assertEqual(j['stage'],'Calibrage')
        j=self.s.transition(j['id'],'MAXIME');self.assertEqual(j['stage'],'Mise en boîte');final_validation(j)
    def test_duplicate_serials_and_batteries(self):
        j=self.s.save(fill(self.j),'HASMAN');other=fill(self.s.create(order(2),'TOKY'))
        with self.assertRaises(ValueError):self.s.save(other,'TOKY')
        other['fields']['battery_serial']='BAT-2';other['fields']['seal']='SEAL-2'
        with self.assertRaises(ValueError):self.s.save(other,'TOKY')
    def test_repeated_cell_and_nan(self):
        j=fill(self.j);j['fields']['cell_1_serial']='CELL-1';j['fields']['cell_2_serial']='CELL-1'
        with self.assertRaises(ValueError):assembly_validation(j)
        j['fields']['cell_2_serial']='';j['fields']['pack_voltage']='nan'
        with self.assertRaises(ValueError):assembly_validation(j)
    def test_pending_survives_restart_and_freezes_data(self):
        op=self.s.enqueue(self.j['id'],'finalize',{'x':1});self.s.db.close();self.s=ManufacturingStore(self.root/'data.sqlite3')
        self.assertEqual(op,self.s.pending(self.j['id']))
        with self.assertRaises(ValueError):self.s.save(self.j,'HASMAN')
        self.assertEqual(op,self.s.enqueue(self.j['id'],'finalize',{'x':2}))
    def test_scrap_clears_only_rejected_component(self):
        j=self.s.save(fill(self.j),'HASMAN');op=self.s.enqueue(j['id'],'scrap',{'field_key':'serial_11_1'})
        j=self.s.complete(op,{'movement_id':32,'serial':'BMS-1'},'HASMAN');self.assertEqual(j['fields']['serial_11_1'],'');self.assertEqual(j['fields']['battery_serial'],'BAT-1');self.assertIsNone(self.s.pending(j['id']))
    def test_conflicting_local_revision(self):
        j=copy.deepcopy(self.j);self.s.save(j,'HASMAN')
        with self.assertRaises(ValueError):self.s.save(j,'TOKY')
    def test_future_cell_scan_drives_consumption(self):
        o=order(2);o['lines'][1]['tobatch']=2
        j=fill(self.s.create(o,'HASMAN'))
        for i in range(1,17):j['fields'][f'cell_{i}_serial']=f'CELL-{i:03}'
        j=self.s.save(j,'HASMAN')
        self.assertEqual(j['fields']['serial_12_7'],'CELL-007')
        from manufacturing_excel import mapping
        self.assertEqual(mapping(j)['serial_12_7'],mapping(j)['cell_7_serial'])
    def test_confirmed_rejection_allows_correction(self):
        op=self.s.enqueue(self.j['id'],'finalize',{'x':1});self.s.reject(op,'Stock insuffisant')
        self.assertIsNone(self.s.pending(self.j['id']));self.s.save(self.j,'HASMAN')
    def test_delete_local_draft_removes_history_without_erp(self):
        j=self.s.save(fill(self.j),'HASMAN')
        self.assertTrue(self.s.history(j['id']))
        deleted=self.s.delete_local(j['id'],'HASMAN')
        self.assertEqual(deleted['id'],j['id'])
        with self.assertRaises(ValueError):self.s.get(j['id'])
        self.assertEqual(self.s.history(j['id']),[])
    def test_delete_protects_completed_and_pending_jobs(self):
        j=self.s.save(fill(self.j),'HASMAN');j['stage']='Terminée';self.s.save(j,'HASMAN')
        with self.assertRaises(ValueError):self.s.delete_local(j['id'],'HASMAN')
        j=self.s.get(j['id']);j['stage']='Assemblage';self.s.save(j,'HASMAN');self.s.enqueue(j['id'],'finalize',{'x':1})
        with self.assertRaises(ValueError):self.s.delete_local(j['id'],'HASMAN')
    def test_merge_disjoint_and_conflict(self):
        merged,c=three_way({'j':{'a':1,'b':2}},{'j':{'a':3,'b':2}},{'j':{'a':1,'b':4}});self.assertEqual(merged['j'],{'a':3,'b':4});self.assertFalse(c)
        _,c=three_way({'j':{'a':1}},{'j':{'a':2}},{'j':{'a':3}});self.assertEqual(len(c),1)
    def test_excel_roundtrip_and_conflict_preservation(self):
        j=self.s.save(fill(self.j),'HASMAN');nas=self.root/'nas';nas.mkdir();(nas/'.atelierborne-nas').touch()
        p=sync_nas(self.s,'MASON',nas);op=library();w=op.load_workbook(p);sheet=w['BAT-1'];sheet['B17']='Une note NAS';w.save(p)
        sync_nas(self.s,'MASON',nas);self.assertEqual(self.s.get(j['id'])['fields']['comments'],'Une note NAS')
        w=op.load_workbook(p);w['BAT-1']['B17']='Correction NAS';w.save(p)
        j=self.s.get(j['id']);j['fields']['comments']='Correction Pi';self.s.save(j,'TOKY')
        before=p.read_bytes()
        with self.assertRaises(MergeConflict) as e:sync_nas(self.s,'MASON',nas)
        self.assertEqual(before,p.read_bytes())
        conflict=e.exception;choices={'fingerprint':conflict.fingerprint}
        for c in conflict.conflicts:choices[c['job']+'|'+c['field']]='nas'
        sync_nas(self.s,'MASON',nas,choices);self.assertEqual(self.s.get(j['id'])['fields']['comments'],'Correction NAS')
    def test_nas_not_mounted_and_excel_open(self):
        with self.assertRaises(ValueError):sync_nas(self.s,'MASON',self.root/'missing')
        nas=self.root/'nas';nas.mkdir();(nas/'.atelierborne-nas').touch();(nas/'~$MASON.xlsx').touch()
        with self.assertRaises(ValueError):sync_nas(self.s,'MASON',nas)
    def test_archive_sheets_preserved(self):
        self.s.save(fill(self.j),'HASMAN');nas=self.root/'nas';nas.mkdir();(nas/'.atelierborne-nas').touch()
        p=sync_nas(self.s,'MASON',nas);op=library();w=op.load_workbook(p);w.create_sheet('Archive')['A1']='Historique';w.save(p)
        sync_nas(self.s,'MASON',nas);self.assertEqual(op.load_workbook(p)['Archive']['A1'].value,'Historique')

if __name__=='__main__':unittest.main()
