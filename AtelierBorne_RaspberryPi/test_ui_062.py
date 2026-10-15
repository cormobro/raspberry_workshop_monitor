"""Essais 0.6.2 : connexion par tuiles, inactivité, mode borne, styles, historique lisible, champ suivant."""
import json
import os
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch
from test_ui_061 import FakeDolibarr, widgets


class Fake062(FakeDolibarr):
    def personal_projects(self):
        return [{'id': 1, 'ref': 'PJ1', 'title': 'Lot Cornex', 'public': 1, 'tasks_total': 8, 'tasks_done': 3, 'tasks_available': 2}]


class Base(unittest.TestCase):
    kiosk = False

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
        self.fake = Fake062()
        self.root = tk.Tk()
        self.store = app.Store(Path(self.tmp.name) / f'demo{time.time_ns()}.sqlite3')
        self.app = app.App(self.root, self.store, fullscreen=False, client=self.fake, kiosk=self.kiosk, idle_minutes=1)
        self.root.geometry('1920x1080+0+0')
        self.pump()

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
            self.fail('Condition graphique non atteinte')

    def find(self, text, kind=tk.Button):
        for w in widgets(self.root):
            if isinstance(w, kind):
                try:
                    if w.cget('text') == text:
                        return w
                except tk.TclError:
                    pass

    def login(self, code='123456'):
        with patch.object(self.appmod, 'load_personal_client', return_value=self.fake):
            self.find('Miora').invoke()
            for k in code:
                self.find(k).invoke()
            self.find('Se connecter').invoke()
            self.pump()


class LoginAndIdleTests(Base):
    def test_tile_and_pin_pad_login(self):
        self.find('Se connecter').invoke()
        self.assertIsNone(self.app.session.user)  # no name chosen
        self.login('999')
        self.assertIsNone(self.app.session.user)
        self.find('Effacer').invoke()
        self.login()
        self.assertEqual(self.app.session.user, 'Miora')

    def test_inactivity_warning_then_logout(self):
        self.login()
        self.app.last_activity = time.monotonic() - 50
        self.pump(lambda: self.app.idle_banner.winfo_ismapped())
        self.assertIn('Déconnexion automatique', self.app.idle_banner.cget('text'))
        self.app.activity()
        self.assertFalse(self.app.idle_banner.winfo_ismapped())
        self.app.last_activity = time.monotonic() - 61
        self.pump(lambda: self.app.session.user is None)
        self.pump(lambda: self.find('Session fermée automatiquement après 1 min sans activité. Brouillons enregistrés.', tk.Label) is not None)

    def test_no_idle_logout_during_network_operation(self):
        self.login()
        self.app.manufacturing.busy = True
        self.app.last_activity = time.monotonic() - 120
        self.pump(timeout=1.5)
        self.assertEqual(self.app.session.user, 'Miora')
        self.app.manufacturing.busy = False

    def test_connection_indicator(self):
        self.login()
        self.pump(lambda: 'joignable' in self.app.connection_label.cget('text'))

    def test_project_counters_and_window_hint(self):
        self.login()
        self.pump(lambda: self.find('2 à prendre', tk.Label) is not None)
        self.assertIsNotNone(self.find('  3 / 8 tâche(s) terminée(s)', tk.Label))
        self.assertIsNotNone(self.find('Mode fenêtre : Échap = fenêtre · F11 = plein écran · Ctrl+Maj+Q = quitter', tk.Label))

    def test_delete_buttons_use_danger_style(self):
        from manufacturing import ManufacturingStore
        s = ManufacturingStore()
        s.create({'id': 77, 'ref': 'MO-77', 'model': 'BAT', 'model_label': 'Batterie 16S', 'signature': 'x', 'lines': []}, 'Miora', 'B-77')
        s.db.close()
        self.login()
        self.app.show(4)
        self.pump()
        delete = self.find('Supprimer du Pi')
        self.assertEqual(delete._kind, 'danger')
        self.assertEqual(self.find('Ouvrir')._kind, 'primary')
        self.assertIsNotNone(self.find('   Batterie 16S', tk.Label))  # product name, not reference


class KioskTests(Base):
    kiosk = True

    def test_kiosk_hides_cursor_and_hint(self):
        self.assertEqual(str(self.root.cget('cursor')), 'none')
        self.assertIsNone(self.find('Mode fenêtre : Échap = fenêtre · F11 = plein écran · Ctrl+Maj+Q = quitter', tk.Label))
        self.assertEqual(self.root.bind('<Escape>'), '')


class IdleDefaultTests(unittest.TestCase):
    def test_default_is_five_minutes_and_config_overrides(self):
        import app
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'XDG_CONFIG_HOME': d}):
            self.assertEqual(app.borne_settings()['inactivite_minutes'], 5)
            Path(d, 'atelierborne').mkdir()
            Path(d, 'atelierborne', 'borne.json').write_text('{"inactivite_minutes": 3}')
            self.assertEqual(app.borne_settings()['inactivite_minutes'], 3)
            Path(d, 'atelierborne', 'borne.json').write_text('illisible')
            self.assertEqual(app.borne_settings()['inactivite_minutes'], 5)
            root = tk.Tk()
            try:
                Path(d, 'atelierborne', 'borne.json').unlink()
                with patch.dict(os.environ, {'XDG_DATA_HOME': d + '/data'}):
                    a = app.App(root, app.Store(Path(d) / 'demo.sqlite3'), fullscreen=False)
                    self.assertEqual(a.idle_limit, 300)
                    a.shutdown()
            except tk.TclError:
                pass


class HelperTests(unittest.TestCase):
    def test_field_labels(self):
        from manufacturing_ui import field_label
        self.assertEqual(field_label('cell_3_voltage'), 'C3 tension (V)')
        self.assertEqual(field_label('cell_16_ir'), 'C16 résistance (mΩ)')
        self.assertEqual(field_label('capacity_ah'), 'Capacité réelle (Ah)')

    def test_history_lines(self):
        from manufacturing_ui import history_lines
        before = {'stage': 'Assemblage', 'fields': {'cell_3_voltage': '3.21', 'seal': ''}, 'order': {'lines': []}}
        after = {'stage': 'Calibrage', 'fields': {'cell_3_voltage': '3.24', 'seal': ''}, 'order': {'lines': []}}
        rows = [{'at': '2026-10-14T09:12:30+03:00', 'actor': 'Felix', 'before_json': 'null', 'after_json': json.dumps(before)},
                {'at': '2026-10-14T09:15:00+03:00', 'actor': 'Toky', 'before_json': json.dumps(before), 'after_json': json.dumps(after)}]
        out = history_lines(rows)
        self.assertEqual(out[0][2][0], 'Fiche créée')
        self.assertEqual(out[1][:2], ('2026-10-14 09:15', 'Toky'))
        self.assertIn('Étape : Assemblage → Calibrage', out[1][2])
        self.assertIn('C3 tension (V) : 3.21 → 3.24', out[1][2])

    def test_keyboard_next_skips_optional_serials(self):
        from touch_keyboard import TouchKeyboard
        root = tk.Tk()
        try:
            root._keyboard_anchor = tk.Frame(root)
            root._keyboard_anchor.pack()
            serial1, volt1, ir1, serial2, volt2 = (tk.Entry(root) for _ in range(5))
            for e in (serial1, volt1, ir1, serial2, volt2):
                e.pack()
            for e in (volt1, ir1, volt2):
                e._numeric = True
            root.update()
            kb = TouchKeyboard(root)
            kb.open(ir1)
            root.update()
            kb.next_field()
            self.assertIs(kb.target, volt2)
            kb.shutdown()
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
