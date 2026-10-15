"""Scan rapide 0.6.3 : codes QR, délai d'annulation, cumul, n° de série, étiquettes PDF."""
import os
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from quick_scan import parse_code, code_for
from test_ui_061 import FakeDolibarr, widgets

PRODUCTS = {
    'CABLE-KIT': {'id': 104, 'ref': 'CABLE-KIT', 'label': 'Kit câbles', 'physical': True, 'tracking': 'none', 'qty': 14, 'batches': []},
    'BMS-16S': {'id': 5, 'ref': 'BMS-16S', 'label': 'BMS 16S', 'physical': True, 'tracking': 'serial', 'qty': 2,
                'batches': [{'batch': 'SGS582604130074', 'qty': 1}, {'batch': '0012', 'qty': 1}]},
}


class Fake(FakeDolibarr):
    def stock_by_ref(self, ref):
        if ref not in PRODUCTS:
            from dolibarr_client import ApiError
            raise ApiError('HTTP 404 — produit introuvable', 404)
        return dict(PRODUCTS[ref])

    def stock_move(self, payload):
        self.calls.append(('stock_move', payload))
        p = next(v for v in PRODUCTS.values() if v['id'] == payload['product_id'])
        after = p['qty'] + payload['qty'] if payload['direction'] == 'in' else p['qty'] - payload['qty']
        return {'movement_id': 90 + len(self.calls), 'ref': p['ref'], 'direction': payload['direction'], 'qty': payload['qty'],
                'batch': payload['batch'], 'before': p['qty'], 'after': after, 'operator': 'miora'}


class ParseTests(unittest.TestCase):
    def test_codes(self):
        self.assertEqual(parse_code('BCELL-ENTREE:CABLE-KIT'), ('in', 'CABLE-KIT'))
        self.assertEqual(parse_code(' bcell-sortie:Cable-Kit \n'), ('out', 'Cable-Kit'))
        self.assertEqual(parse_code(code_for('out', 'A:B')), ('out', 'A:B'))
        for bad in ('', 'BCELL-ENTREE:', 'SGS582604130074', 'BCELL-STOCK:+:X', 'BCELL)ENTREE.X'):
            self.assertIsNone(parse_code(bad))


class QuickScanUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.env = patch.dict(os.environ, {'XDG_DATA_HOME': cls.tmp.name + '/data', 'XDG_CONFIG_HOME': cls.tmp.name + '/config'})
        cls.env.start()

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        cls.tmp.cleanup()

    def setUp(self):
        import app
        self.appmod = app
        self.fake = Fake()
        self.root = tk.Tk()
        self.store = app.Store(Path(self.tmp.name) / f'demo{time.time_ns()}.sqlite3')
        self.app = app.App(self.root, self.store, fullscreen=False, client=self.fake)
        self.root.geometry('1920x1080+0+0')
        self.quick = self.app.quick

    def tearDown(self):
        self.app.shutdown()
        self.store.db.close()

    def pump(self, until=None, timeout=3.0):
        end = time.time() + timeout
        while time.time() < end:
            self.root.update()
            if until is not None and until():
                return
            time.sleep(0.02)
        if until is not None:
            self.fail('Condition non atteinte')

    def find(self, text, kind=tk.Button):
        for w in widgets(self.root):
            if isinstance(w, kind):
                try:
                    if w.cget('text') == text:
                        return w
                except tk.TclError:
                    pass

    def login(self):
        with patch.object(self.appmod, 'load_personal_client', return_value=self.fake):
            self.find('Miora').invoke()
            for k in '123456':
                self.find(k).invoke()
            self.find('Se connecter').invoke()
        self.pump(timeout=0.3)
        self.root.focus_set()
        self.pump(timeout=0.1)

    def scan(self, text):
        """Imite le scanner : frappes rapides puis Entrée, sans champ actif."""
        self.root.focus_force()
        self.root.update()
        for ch in text:
            self.quick.key(SimpleNamespace(keysym=ch, char=ch))
        self.quick.key(SimpleNamespace(keysym='Return', char='\r'))
        self.root.update()

    def moves(self):
        return [c[1] for c in self.fake.calls if c[0] == 'stock_move']

    def expire(self):
        self.quick.current['deadline'] = time.monotonic() - 1

    def test_requires_login(self):
        self.scan('BCELL-ENTREE:CABLE-KIT')
        self.assertIn('Connectez-vous', self.panel_text())

    def panel_text(self):
        return ' '.join(w.cget('text') for w in widgets(self.quick.panel) if isinstance(w, tk.Label))

    def test_repeat_scans_add_up_then_one_movement(self):
        self.login()
        self.scan('BCELL-ENTREE:CABLE-KIT')
        self.pump(lambda: self.quick.current is not None)
        self.scan('BCELL-ENTREE:CABLE-KIT')
        self.scan('BCELL-ENTREE:CABLE-KIT')
        self.assertEqual(self.quick.current['qty'], 3)
        self.assertIn('stock 14 → 17', self.panel_text())
        self.assertEqual(self.moves(), [])  # rien envoyé pendant le délai
        self.expire()
        self.pump(lambda: len(self.moves()) == 1)
        m = self.moves()[0]
        self.assertEqual((m['direction'], m['qty'], m['reason'], m['comment']), ('in', 3.0, 'autre', 'Scan rapide'))
        self.pump(lambda: '✓' in self.panel_text())
        sent = self.app.stock_ui.journal.get(m['operation_id'])
        self.assertEqual(sent['status'], 'done')

    def test_cancel_sends_nothing(self):
        self.login()
        self.scan('BCELL-SORTIE:CABLE-KIT')
        self.pump(lambda: self.quick.current is not None)
        self.find('Annuler (5)').invoke()
        self.pump(timeout=0.3)
        self.assertIsNone(self.quick.current)
        self.assertEqual(self.moves(), [])
        self.assertIn('rien n’a été envoyé', self.panel_text())

    def test_serial_product_asks_for_serial_then_consumes_it(self):
        self.login()
        self.scan('BCELL-SORTIE:BMS-16S')
        self.pump(lambda: self.quick.waiting_batch is not None)
        entry = [w for w in widgets(self.quick.panel) if isinstance(w, tk.Entry)][0]
        entry.insert(0, 'ABSENT-1')
        entry.event_generate('<Return>')
        self.pump(timeout=0.2)
        self.assertIn('n’est pas en stock', self.panel_text())
        self.assertIsNone(self.quick.current)
        self.scan('BCELL-SORTIE:BMS-16S')
        self.pump(lambda: self.quick.waiting_batch is not None)
        entry = [w for w in widgets(self.quick.panel) if isinstance(w, tk.Entry)][0]
        entry.insert(0, '0012')
        entry.event_generate('<Return>')
        self.pump(lambda: self.quick.current is not None)
        self.scan('BCELL-SORTIE:BMS-16S')  # pas de cumul sur une série : envoie le premier, redemande un n°
        self.pump(lambda: len(self.moves()) == 1)
        m = self.moves()[0]
        self.assertEqual((m['batch'], m['qty'], m['reason']), ('0012', 1.0, 'consommation'))

    def test_other_product_commits_previous_and_logout_flushes(self):
        self.login()
        self.scan('BCELL-ENTREE:CABLE-KIT')
        self.pump(lambda: self.quick.current is not None)
        self.scan('BCELL-SORTIE:BMS-16S')
        self.pump(lambda: len(self.moves()) == 1)
        self.assertEqual(self.moves()[0]['product_id'], 104)
        self.quick.cancel_batch_prompt()
        self.scan('BCELL-SORTIE:CABLE-KIT')
        self.pump(lambda: self.quick.current is not None)
        self.app.logout()
        self.pump(lambda: len(self.moves()) == 2)
        self.assertEqual(self.moves()[1]['direction'], 'out')

    def test_unknown_code_and_unknown_product(self):
        self.login()
        self.scan('&é"(-è')
        self.assertIn('Code non reconnu', self.panel_text())
        self.scan('BCELL-ENTREE:INCONNU')
        self.pump(lambda: 'introuvable' in self.panel_text())
        self.assertEqual(self.moves(), [])

    def test_code_scanned_into_search_field_is_taken_over(self):
        self.login()
        self.app.show(2)
        self.pump(timeout=0.5)
        search = [w for w in widgets(self.root) if isinstance(w, tk.Entry) and w.winfo_ismapped()][0]
        search.focus_force()
        self.pump(lambda: isinstance(self.root.focus_get(), tk.Entry), timeout=1)
        focused = self.root.focus_get()  # le clavier tactile s'ouvre et prend la saisie
        for ch in 'BCELL-ENTREE:CABLE-KIT':
            focused.insert('end', ch)
        focused.event_generate('<Return>')
        self.pump(lambda: self.quick.current is not None)
        self.assertEqual(search.get(), '')


if __name__ == '__main__':
    unittest.main()
