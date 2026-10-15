import tempfile
import unittest
from pathlib import Path
from app import Store

class DomainTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'demo.sqlite3';self.s=Store(self.path)
    def tearDown(self):self.s.db.close();self.temp.cleanup()
    def test_task_claim_and_owner(self):
        self.s.task(1,'Prendre','Miora')
        r=self.s.rows('SELECT * FROM tasks WHERE id=1')[0];self.assertEqual(r['progress'],0)
        with self.assertRaises(ValueError):self.s.task(1,'Prendre','Hery')
        with self.assertRaises(ValueError):self.s.task(1,'Terminer','Hery')
        self.s.task(1,'Démarrer','Miora');self.s.task(1,'Terminer','Miora')
        self.assertEqual(self.s.rows('SELECT progress FROM tasks WHERE id=1')[0][0],100)
    def test_stock_and_stale_count(self):
        self.s.movement('BOX-LV','Atelier','Sortie',2,'','Assemblage','Miora',12)
        with self.assertRaises(ValueError):self.s.movement('BOX-LV','Atelier','Sortie',20,'','Assemblage','Miora',10)
        with self.assertRaises(ValueError):self.s.movement('BOX-LV','Atelier','Inventaire',3,'','Comptage','Miora',12)
        self.assertEqual(self.s.rows("SELECT qty FROM stock WHERE product='BOX-LV' AND warehouse='Atelier'")[0][0],10)
    def test_unique_serial_and_atomic_failure(self):
        with self.assertRaises(ValueError):self.s.movement('BAT-LV','Atelier','Entrée',1,'bms-00041','Test','Miora',1)
        with self.assertRaises(ValueError):self.s.movement('BMS-16S','Magasin','Sortie',1,'BMS-00041','Test','Miora',0)
        self.s.movement('BMS-16S','Atelier','Sortie',1,'bms-00041','Test','Miora',2)
        with self.assertRaises(ValueError):self.s.movement('BMS-16S','Atelier','Entrée',1,'BMS-00041','Test','Miora',1)
        self.assertEqual(self.s.rows("SELECT qty FROM stock WHERE product='BMS-16S' AND warehouse='Atelier'")[0][0],1)
    def test_leave_validation(self):
        with self.assertRaises(ValueError):self.s.leave('Hery','2030-06-10','2030-06-09')
        self.s.leave('Hery','2030-06-10','2030-06-12')
        with self.assertRaises(ValueError):self.s.leave('Hery','2030-06-11','2030-06-14')
    def test_persistence(self):
        self.s.task(2,'Prendre','Lova');self.s.db.close();self.s=Store(self.path)
        self.assertEqual(self.s.rows('SELECT owner FROM tasks WHERE id=2')[0][0],'Lova')
        self.assertEqual(len(self.s.rows('SELECT * FROM tasks')),3)

class SessionTests(unittest.TestCase):
    def test_login_failure_logout(self):
        from app import Session
        session=Session()
        self.assertIsNone(session.user)
        self.assertFalse(session.login('Miora','incorrect'))
        self.assertIsNone(session.user)
        self.assertTrue(session.login('Miora','123456'))
        self.assertEqual(session.user,'Miora')
        session.logout();self.assertIsNone(session.user)
        self.assertFalse(session.login('inconnu','123456'))
    def test_failed_login_clears_previous_identity(self):
        from app import Session
        session=Session();session.login('Miora','123456')
        session.login('Hery','incorrect');self.assertIsNone(session.user)

if __name__=='__main__':unittest.main()
