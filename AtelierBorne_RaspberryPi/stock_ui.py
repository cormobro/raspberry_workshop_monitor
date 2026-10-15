"""Écran Stocks raccordé à Dolibarr : consultation et entrées/sorties réelles."""
import html
import queue
import threading
import tkinter as tk
from dolibarr_client import ApiError, stock_quantity
from stock_ops import REASONS, DIRECTIONS, StockJournal, build_payload, fmt, transmit, record
from touch_ui import messagebox
import theme
BLUE = theme.PRIMARY

GREEN = theme.SUCCESS
ORANGE = theme.WARN
GREY = '#EEF2F7'


class StockUI:
    def __init__(self, app, journal=None):
        self.app = app
        self._journal = journal
        self.inflight = set()

    @property
    def journal(self):
        if self._journal is None:
            self._journal = StockJournal()
        return self._journal

    def background(self, action, done, alive=lambda: True):
        result = queue.Queue()

        def worker():
            try:
                result.put((True, action()))
            except ApiError as e:
                result.put((False, str(e)))
            except Exception:
                result.put((False, 'Erreur inattendue. Actualisez avant de réessayer.'))

        def poll():
            if not alive():
                return
            try:
                ok, value = result.get_nowait()
            except queue.Empty:
                self.app.root.after(100, poll)
                return
            done(ok, value)
        threading.Thread(target=worker, daemon=True).start()
        self.app.root.after(100, poll)

    # ---- liste -------------------------------------------------------------
    def screen(self):
        a = self.app
        a.label(a.body, 'Stocks', True)
        a.label(a.body, 'Stock de l’entrepôt atelier · entrées et sorties réelles avec votre compte' if a.personal else 'Stock physique total · consultation (compte partagé)', muted=True)
        bar = a.toolbar()
        a.button(bar, 'Actualiser', lambda: a.show(2), 'secondary').pack(side='left', padx=(0, 8))
        if a.personal:
            tk.Label(bar, text='Scan rapide : scannez l’étiquette « + » ou « − » d’une boîte, depuis n’importe quel écran.',
                     bg=bar.cget('bg'), fg=theme.MUTED, font=(theme.FONT, 15)).pack(side='left', padx=16)
        if a.personal:
            self.pending_banner(a.body)
        search_row = tk.Frame(a.body, bg=a.body.cget('bg'))
        search_row.pack(fill='x', pady=(0, 6))
        tk.Label(search_row, text='Rechercher', bg=search_row.cget('bg'), fg=theme.MUTED).pack(side='left', padx=(0, 10))
        search = tk.Entry(search_row)
        search.pack(side='left', fill='x', expand=True)
        client = a.client
        personal = a.personal

        def load():
            identity = None
            if personal:
                try:
                    identity = client.identity()
                except ApiError:
                    identity = None  # Module ancien ou non joignable : consultation seule.
            return identity, client.products()

        def render(result):
            identity, rows = result
            self.rows = rows
            can_move = bool(identity and identity.get('can_move_stock'))
            area = a.listing()
            if personal and not can_move:
                a.label(area, 'Mouvements indisponibles : droit Dolibarr « créer des mouvements de stock » ou module AtelierBorne 0.6.1 requis.').config(fg=theme.DANGER)

            def refresh(*args):
                for child in area.winfo_children():
                    if getattr(child, '_product_card', False):
                        child.destroy()
                term = search.get().casefold()
                count = 0
                for r in rows:
                    name = html.unescape(str(r.get('label') or ''))
                    ref = str(r.get('ref') or '')
                    if term not in (ref + ' ' + name).casefold():
                        continue
                    count += 1
                    f = a.card(area)
                    f._product_card = True
                    right = tk.Frame(f, bg='white')
                    right.pack(side='right')
                    left = tk.Frame(f, bg='white')
                    left.pack(side='left', fill='x', expand=True)
                    tk.Label(left, text=name or ref, bg='white', fg=theme.INK, font=(theme.FONT, 22, 'bold'), anchor='w').pack(fill='x')
                    tk.Label(left, text=ref, bg='white', fg=theme.MUTED, font=(theme.FONT, 16), anchor='w').pack(fill='x')
                    quantity = stock_quantity(r)
                    if quantity is not None:
                        tk.Label(right, text=format(quantity.normalize(), 'f'), bg='white', fg=theme.PRIMARY_DARK, font=(theme.FONT, 30, 'bold')).pack(side='left', padx=(0, 6))
                        tk.Label(right, text='en stock', bg='white', fg=theme.MUTED, font=(theme.FONT, 16)).pack(side='left', padx=(0, 24))
                    else:
                        tk.Label(right, text='Quantité indisponible (droit de lecture des stocks ?)', bg='white', fg=theme.MUTED, font=(theme.FONT, 15)).pack(side='left', padx=(0, 24))
                    if can_move and str(r.get('type', '0')) == '0':
                        a.button(right, 'Entrée / Sortie', lambda r=r: self.form(r)).pack(side='left')
                if not count:
                    note = a.label(area, 'Aucun produit correspondant.')
                    note._product_card = True
            value = tk.StringVar(value=search.get())
            search.config(textvariable=value)
            search._filter_var = value
            value.trace_add('write', refresh)
            refresh()
        a.remote_fetch(load, render)

    def pending_banner(self, parent):
        a = self.app
        ops = self.journal.pending(a.session.user)
        if not ops:
            return
        box = tk.Frame(parent, bg='#fff3d6', padx=16, pady=10, highlightthickness=1, highlightbackground='#F0D9A8')
        box.pack(fill='x', pady=6)
        tk.Label(box, text='Mouvement(s) sans confirmation de Dolibarr — réessayez : ils ne seront pas appliqués deux fois.',
                 bg='#fff3d6', anchor='w', wraplength=1500, justify='left').pack(fill='x')
        for op in ops:
            line = tk.Frame(box, bg='#fff3d6')
            line.pack(fill='x', pady=3)
            tk.Label(line, text=op['label'], bg='#fff3d6', anchor='w').pack(side='left', fill='x', expand=True)
            a.button(line, 'Réessayer', lambda op=op: self.retry(op)).pack(side='right')

    def retry(self, op):
        a = self.app
        actor = a.session.user
        if op['actor'] != actor:
            return
        client = a.client
        if op['id'] in self.inflight:
            return  # Double appui : l'envoi est déjà en cours.
        self.inflight.add(op['id'])

        def done(ok, value):
            self.inflight.discard(op['id'])
            status, detail = record(self.journal, op, *(value if ok else ('uncertain', value)))
            if a.session.user != actor:
                return
            if status == 'done':
                messagebox.showinfo('Mouvement confirmé', self.summary(detail), parent=a.root)
            elif status == 'rejected':
                messagebox.showerror('Mouvement refusé', 'Dolibarr a refusé ce mouvement ; rien n’a été appliqué.\n\n' + detail, parent=a.root)
            else:
                messagebox.showwarning('Toujours incertain', 'Pas de réponse fiable de Dolibarr. Réessayez plus tard.\n\n' + detail, parent=a.root)
            a.show(2)
        self.background(lambda: transmit(client, op), done)

    @staticmethod
    def summary(r):
        sens = DIRECTIONS.get(r.get('direction'), '')
        text = f"{sens} de {fmt(r.get('qty'))} · {r.get('ref', '')}"
        if r.get('batch'):
            text += f" · n° {r['batch']}"
        return text + f"\nStock : {fmt(r.get('before'))} → {fmt(r.get('after'))}\nPar {r.get('operator', '')}"

    # ---- formulaire ----------------------------------------------------------
    def form(self, row):
        a = self.app
        actor = a.session.user
        client = a.client
        title = str(row.get('ref') or '') + ' · ' + html.unescape(str(row.get('label') or ''))
        w = a.dialog(title)
        status = a.label(w, 'Lecture du stock dans Dolibarr…')

        def alive():
            return w.winfo_exists() and a.session.user == actor

        def loaded(ok, product):
            if not ok:
                status.config(text=product, fg=theme.DANGER)
                return
            status.destroy()
            self.render_form(w, product, actor, client)
        self.background(lambda: client.stock_product(int(row['id'])), loaded, alive)

    def render_form(self, w, product, actor, client):
        a = self.app
        tracking = product['tracking']
        state = {'direction': None, 'reason': None}
        current = a.label(w, 'Stock actuel : ' + fmt(product['qty']), True)
        a.label(w, {'serial': 'Suivi par numéro de série : une unité par numéro.',
                    'lot': 'Suivi par lot : numéro de lot obligatoire.',
                    'none': 'Suivi en quantité.'}[tracking])

        # Sens du mouvement : deux grands boutons.
        a.label(w, 'Mouvement')
        sens = tk.Frame(w, bg='white')
        sens.pack(fill='x', pady=4)
        buttons = {}

        def pick_direction(value):
            state['direction'] = value
            for key, b in buttons.items():
                colour = GREEN if key == 'in' else ORANGE
                b.config(bg=colour if key == value else GREY, fg='white' if key == value else '#172338')
            update_batches()
        for key, text in (('in', '＋ Entrée'), ('out', '－ Sortie')):
            b = tk.Button(sens, text=text, command=lambda k=key: pick_direction(k), font=('DejaVu Sans', 22, 'bold'),
                          bg=GREY, relief='flat', pady=22)
            b.pack(side='left', fill='x', expand=True, padx=4)
            buttons[key] = b

        qty = None
        if tracking != 'serial':
            a.label(w, 'Quantité')
            qty = tk.Entry(w)
            qty._numeric = True
            qty.insert(0, '1')
            qty.pack(fill='x')

        batch = None
        batch_list = None
        if tracking != 'none':
            a.label(w, 'Numéro de série (scanner)' if tracking == 'serial' else 'Numéro de lot (scanner)')
            line = tk.Frame(w, bg='white')
            line.pack(fill='x')
            batch = tk.Entry(line)
            batch._virtual_keyboard = True  # Le scanner tape comme un clavier.
            batch.pack(side='left', fill='x', expand=True)
            a.button(line, 'Clavier', lambda: a.keyboard.open(batch)).pack(side='right', padx=2)
            batch_list = tk.Frame(w, bg='white')
            batch_list.pack(fill='x', pady=4)

        def update_batches():
            if batch_list is None:
                return
            for child in batch_list.winfo_children():
                child.destroy()
            if state['direction'] != 'out':
                return
            present = product.get('batches', [])
            if not present:
                tk.Label(batch_list, text='Aucun numéro en stock.', bg='white').pack(anchor='w')
                return
            tk.Label(batch_list, text=f'En stock ({len(present)}) — touchez pour choisir :', bg='white').pack(anchor='w')
            grid = tk.Frame(batch_list, bg='white')
            grid.pack(fill='x')
            for i, b in enumerate(present[:60]):
                text = b['batch'] + ('' if tracking == 'serial' else f" ({fmt(b['qty'])})")
                tk.Button(grid, text=text, bg=GREY, relief='flat', pady=10, font=('DejaVu Sans', 15),
                          command=lambda v=b['batch']: (batch.delete(0, 'end'), batch.insert(0, v))
                          ).grid(row=i // 3, column=i % 3, sticky='ew', padx=3, pady=3)
                grid.columnconfigure(i % 3, weight=1, uniform='batches')
            if len(present) > 60:
                tk.Label(batch_list, text='Liste limitée à 60 : scannez le numéro.', bg='white').pack(anchor='w')

        a.label(w, 'Motif')
        reasons = tk.Frame(w, bg='white')
        reasons.pack(fill='x', pady=4)
        reason_buttons = {}

        def pick_reason(value):
            state['reason'] = value
            for key, b in reason_buttons.items():
                b.config(bg=BLUE if key == value else GREY, fg='white' if key == value else '#172338')
        for i, (key, text) in enumerate(REASONS):
            b = tk.Button(reasons, text=text, command=lambda k=key: pick_reason(k), bg=GREY, relief='flat', pady=16)
            b.grid(row=i // 3, column=i % 3, sticky='ew', padx=3, pady=3)
            reasons.columnconfigure(i % 3, weight=1, uniform='reasons')
            reason_buttons[key] = b
        a.label(w, 'Précision (obligatoire pour « Autre »)')
        comment = tk.Entry(w)
        comment.pack(fill='x')
        message = a.label(w, '')

        def submit():
            if a.session.user != actor:
                w.destroy()
                return
            try:
                payload = build_payload(product, state['direction'], qty.get() if qty else 1,
                                        batch.get() if batch else '', state['reason'], comment.get())
            except ValueError as e:
                message.config(text=str(e), fg=theme.DANGER)
                return
            sens = DIRECTIONS[payload['direction']]
            label = f"{sens} {fmt(payload['qty'])} · {product['ref']}" + (f" · n° {payload['batch']}" if payload['batch'] else '')
            if not messagebox.askyesno('Confirmer le mouvement', label + '\nMotif : ' + dict(REASONS)[payload['reason']] +
                                       (' — ' + payload['comment'] if payload['comment'] else '') +
                                       '\n\nLe stock Dolibarr sera modifié immédiatement.', parent=w):
                return
            try:
                op = self.journal.prepare(actor, payload, label)
            except ValueError as e:
                message.config(text=str(e), fg=theme.DANGER)
                return
            go.config(state='disabled')
            message.config(text='Envoi à Dolibarr…', fg='#172338')

            def done(ok, value):
                status, detail = record(self.journal, op, *(value if ok else ('uncertain', value)))
                if status == 'done':
                    messagebox.showinfo('Mouvement enregistré', self.summary(detail), parent=a.root)
                    if w.winfo_exists():
                        w.destroy()
                    if a.session.user == actor:
                        a.show(2)
                elif status == 'rejected':
                    if w.winfo_exists():
                        message.config(text='Refusé par Dolibarr, rien n’a été appliqué.\n' + detail, fg=theme.DANGER)
                        go.config(state='normal')
                else:
                    messagebox.showwarning('Réponse incertaine',
                                           'Dolibarr n’a pas confirmé le mouvement. Il est conservé sur le Pi : utilisez « Réessayer » dans Stocks. Il ne sera pas appliqué deux fois.\n\n' + detail,
                                           parent=a.root)
                    if w.winfo_exists():
                        w.destroy()
                    if a.session.user == actor:
                        a.show(2)
            self.background(lambda: transmit(client, op), done)
        go = a.button(w, 'Enregistrer le mouvement', submit)
        go.config(pady=20)
        go.pack(pady=14, fill='x')
