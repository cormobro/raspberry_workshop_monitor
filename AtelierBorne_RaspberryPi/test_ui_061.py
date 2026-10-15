"""Essai graphique 0.6.1 sur serveur d'affichage virtuel (xvfb-run) avec un faux Dolibarr."""
import os
import subprocess
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

SHOTS = os.environ.get('ATELIER_SCREENSHOTS')


class FakeDolibarr:
    def __init__(self):
        self.calls = []
        self.tasks = [{'id': 4, 'ref': 'T4', 'label': 'Préparer les kits', 'progress': 20, 'project_title': 'Assemblage',
                       'project_status': 1, 'mine': True, 'assigned_count': 1}]

    def identity(self):
        return {'id': 3, 'login': 'miora', 'can_move_stock': True, 'version': '0.6.1'}

    def personal_projects(self):
        return [{'id': 1, 'ref': 'PJ1', 'title': 'Assemblage', 'public': 1}]

    def my_tasks(self):
        return self.tasks

    def complete(self, ident):
        self.calls.append(('complete', ident))
        return {'task_id': ident, 'progress': 100}

    def unassign(self, ident):
        self.calls.append(('unassign', ident))
        return {'task_id': ident}

    def products(self):
        return [{'id': '5', 'ref': 'BMS-16S', 'label': 'BMS 16S', 'type': '0', 'stock_reel': '2', 'stock_warehouse': {}},
                {'id': '9', 'ref': 'MO', 'label': 'Main d’œuvre', 'type': '1', 'stock_reel': '0', 'stock_warehouse': {}}]

    def stock_product(self, ident):
        return {'id': ident, 'ref': 'BMS-16S', 'label': 'BMS 16S', 'physical': True, 'tracking': 'serial', 'qty': 2,
                'batches': [{'batch': 'SGS582604130074', 'qty': 1}, {'batch': 'SGS582604130075', 'qty': 1}]}

    def stock_move(self, payload):
        self.calls.append(('stock_move', payload))
        return {'movement_id': 77, 'ref': 'BMS-16S', 'direction': payload['direction'], 'qty': 1,
                'batch': payload['batch'], 'before': 2, 'after': 1, 'operator': 'miora'}

    def paginate(self, route, params=None):
        assert route == 'atelierborne/manufacturing/boms'
        return [{'bom_ref': 'BOM2601-0003', 'product_ref': 'BAT-16S-314', 'product_label': 'Batterie 16S 314 Ah'},
                {'bom_ref': 'BOM2601-0004', 'product_ref': 'BAT-16S-280', 'product_label': 'Batterie 16S 280 Ah'}]


def widgets(root):
    stack = [root]
    while stack:
        w = stack.pop()
        yield w
        stack.extend(w.winfo_children())


class UiTests(unittest.TestCase):
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
        self.fake = FakeDolibarr()
        self.root = tk.Tk()
        self.store = app.Store(Path(self.tmp.name) / f'demo{time.time_ns()}.sqlite3')
        self.app = app.App(self.root, self.store, fullscreen=False, client=self.fake)
        self.root.geometry('1920x1080+0+0')
        with patch.object(app, 'load_personal_client', return_value=self.fake):
            self.find('Miora').invoke()
            entries = [w for w in widgets(self.root) if isinstance(w, tk.Entry) and w.cget('show') == '•']
            entries[0].insert(0, '123456')
            self.press('Se connecter')
        self.pump()

    def tearDown(self):
        self.app.shutdown()
        self.store.db.close()

    def pump(self, until=None, timeout=3.0):
        end = time.time() + timeout
        while time.time() < end:
            self.root.update()
            if until is None or until():
                if until is None:
                    time.sleep(0.05)
                    self.root.update()
                return True
            time.sleep(0.02)
        if until is not None:
            self.fail('Condition graphique non atteinte')

    def find(self, text, kind=tk.Button):
        for w in widgets(self.root):
            if isinstance(w, kind):
                try:
                    if w.cget('text') == text:
                        return w
                except tk.TclError:
                    pass
        return None

    def press(self, text):
        b = self.find(text)
        self.assertIsNotNone(b, text)
        b.invoke()
        self.pump()

    def shot(self, name):
        if SHOTS:
            self.pump()
            Path(SHOTS).mkdir(parents=True, exist_ok=True)
            subprocess.run(['import', '-window', 'root', str(Path(SHOTS) / name)], check=False)

    def test_red_logout_and_identity(self):
        b = self.app.logout_button
        self.assertEqual(b.cget('bg').lower(), '#c62828')
        self.assertEqual(b.cget('fg'), 'white')
        self.assertTrue(b.winfo_ismapped())

    def test_my_tasks_complete_and_unassign(self):
        self.press('Mes tâches en cours')
        self.pump(lambda: self.find('Terminer / 100 %'))
        self.assertIsNotNone(self.find('Me désassigner'))
        self.shot('1_mes_taches.png')
        self.press('Terminer / 100 %')
        self.shot('2_confirmer_100.png')
        self.press('Confirmer : terminée à 100 %')
        self.pump(lambda: ('complete', 4) in self.fake.calls)
        self.press('Me désassigner')
        self.press('Confirmer la désassignation')
        self.pump(lambda: ('unassign', 4) in self.fake.calls)

    def test_stock_exit_with_serial(self):
        import stock_ui
        self.app.show(2)
        self.pump(lambda: self.find('Entrée / Sortie'))
        cards = [w for w in widgets(self.root) if isinstance(w, tk.Button) and w.cget('text') == 'Entrée / Sortie']
        self.assertEqual(len(cards), 1)  # service product has no movement button
        self.shot('3_stocks.png')
        cards[0].invoke()
        self.pump(lambda: self.find('Enregistrer le mouvement'))
        self.press('－ Sortie')
        self.press('SGS582604130075')
        self.press('Casse')
        self.shot('4_sortie_stock.png')
        with patch.object(stock_ui.messagebox, 'askyesno', return_value=True), \
                patch.object(stock_ui.messagebox, 'showinfo', return_value=True):
            self.press('Enregistrer le mouvement')
            self.pump(lambda: any(c[0] == 'stock_move' for c in self.fake.calls))
            self.pump(lambda: self.app.stock_ui.journal.pending('Miora') == [])
        payload = [c[1] for c in self.fake.calls if c[0] == 'stock_move'][0]
        self.assertEqual((payload['direction'], payload['batch'], payload['qty'], payload['reason']),
                         ('out', 'SGS582604130075', 1.0, 'casse'))
        self.assertEqual(len(payload['operation_id']), 36)

    def test_model_cards(self):
        import manufacturing_ui
        self.app.show(4)
        self.press('＋ Nouvel OF')
        self.pump(lambda: self.find('Batterie 16S 280 Ah', tk.Label))
        go = self.find('Créer l’OF')
        self.assertEqual(str(go.cget('state')), 'disabled')
        self.assertIsNone(self.find('BOM2601-0003', tk.Label))  # BOM reference not shown to the operator
        label = self.find('Batterie 16S 280 Ah', tk.Label)
        card = label.master
        self.assertEqual((card.winfo_width(), card.winfo_height()), (manufacturing_ui.CARD_SIZE, manufacturing_ui.CARD_SIZE))
        label.event_generate('<ButtonPress-1>', x=5, y=5)
        label.event_generate('<ButtonRelease-1>', x=5, y=5)
        self.pump()
        self.assertEqual(str(go.cget('state')), 'normal')
        self.assertEqual(card.cget('highlightbackground'), manufacturing_ui.CARD_SELECTED)
        self.shot('5_cartes_modeles.png')
        with patch.object(self.app.manufacturing, 'submit') as submit:
            go.invoke()
            self.pump()
        self.assertEqual(submit.call_args[0][0]['payload']['bom_ref'], 'BOM2601-0004')


if __name__ == '__main__':
    unittest.main()
