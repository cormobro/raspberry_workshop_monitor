"""Scan rapide : un QR « + » ou « − » collé sur la boîte ajoute ou retire une unité du stock.

Déroulement :
1. Le scanner (clavier USB) envoie BCELL-ENTREE:<réf> ou BCELL-SORTIE:<réf> suivi d'Entrée (le scanner décode le QR
   lui-même et le tape comme un clavier : aucune bibliothèque QR n'est nécessaire sur le Pi),
   alors qu'aucun champ de saisie n'a le focus.
2. Produit suivi par série ou lot : la borne demande le scan du numéro.
3. Le mouvement est affiché 5 s avec « Annuler ». Un nouveau scan du même code pendant ce
   délai ajoute une unité (+2, +3…) : un seul mouvement Dolibarr pour le tout.
4. À la fin du délai, le mouvement est enregistré dans le journal du Pi puis envoyé
   (même protection contre les doublons que l'écran Entrée / Sortie).
Annuler pendant les 5 s n'envoie rien à Dolibarr : aucun mouvement inverse n'est créé.
"""
import time
import tkinter as tk

PREFIXES = {'in': 'BCELL-ENTREE:', 'out': 'BCELL-SORTIE:'}
REASONS = {'in': ('autre', 'Scan rapide'), 'out': ('consommation', 'Scan rapide')}
HOLD_SECONDS = 5
KEY_GAP = 0.35  # un scanner tape bien plus vite ; au-delà, le tampon repart de zéro


def code_for(direction, ref):
    return PREFIXES[direction] + str(ref)


def parse_code(text):
    """('in'|'out', réf) ou None. Tolère la casse et les espaces autour."""
    text = str(text or '').strip()
    upper = text.upper()
    for direction, prefix in PREFIXES.items():
        if upper.startswith(prefix):
            ref = text[len(prefix):].strip()
            return (direction, ref) if ref else None
    return None


def label_for(direction, qty, product, batch=''):
    sign = '+' if direction == 'in' else '−'
    from stock_ops import fmt
    text = f"{sign}{fmt(qty)}  {product.get('label') or product.get('ref')}"
    return text + (f'  · n° {batch}' if batch else '')


class QuickScan:
    def __init__(self, app):
        self.app = app
        self.buffer = ''
        self.last_key = 0.0
        self.current = None      # mouvement en attente pendant le délai d'annulation
        self.waiting_batch = None  # (produit, sens) en attente du scan du n° de série / lot
        self.after_id = None
        self.hide_id = None
        self.panel = tk.Frame(app.root, bg='#E6F4EA', padx=24, pady=16)
        app.root._scan_hook = self.hook

    def hook(self, text, dry_run=False):
        """Pour le clavier tactile : True si le texte est une étiquette de scan rapide."""
        if not parse_code(text):
            return False
        if not dry_run:
            self.handle(text)
        return True

    # ---- capture clavier ----------------------------------------------------------
    def key(self, event):
        focus = self.app.root.focus_get()
        if isinstance(focus, tk.Entry):
            # Un champ reçoit le scan normalement ; si c'est une étiquette de scan rapide
            # (scannée dans la recherche par exemple), on la reprend et on vide le champ.
            if event.keysym in ('Return', 'KP_Enter') and str(focus.cget('state')) == 'normal' and parse_code(focus.get()):
                text = focus.get()
                focus.delete(0, 'end')
                self.app.root.focus_set()
                self.handle(text)
            return
        now = time.monotonic()
        if event.keysym in ('Return', 'KP_Enter'):
            text, self.buffer = self.buffer, ''
            if len(text) >= 3:
                self.handle(text)
            return
        if now - self.last_key > KEY_GAP:
            self.buffer = ''
        self.last_key = now
        if event.char and event.char.isprintable():
            self.buffer += event.char

    # ---- traitement d'un code -------------------------------------------------------
    def handle(self, text):
        a = self.app
        parsed = parse_code(text)
        if not parsed:
            self.show_message(f'Code non reconnu : {text[:60]}\nSi des caractères sont faux, réglez le scanner en clavier « Français ».', 'error')
            return
        if a.session.user is None:
            self.show_message('Connectez-vous pour utiliser le scan rapide.', 'error')
            return
        if not (a.client and a.personal):
            self.show_message('Scan rapide : associez votre compte Dolibarr personnel.', 'error')
            return
        direction, ref = parsed
        cur = self.current
        if cur and cur['product']['ref'] == ref and cur['direction'] == direction and cur['product']['tracking'] == 'none':
            cur['qty'] += 1
            cur['deadline'] = time.monotonic() + HOLD_SECONDS
            self.render_hold()
            return
        if cur:
            self.commit()
        self.cancel_batch_prompt()
        client = a.client
        actor = a.session.user
        self.show_message('Recherche du produit ' + ref + '…', 'info', keep=True)

        def loaded(ok, product):
            if a.session.user != actor:
                return
            if not ok:
                self.show_message(str(product), 'error')
                return
            if not product.get('physical', True):
                self.show_message(f"{product.get('label') or ref} n’est pas un produit stocké.", 'error')
                return
            if product['tracking'] != 'none':
                self.ask_batch(product, direction)
            else:
                self.start_hold(product, direction, '')
        a.stock_ui.background(lambda: client.stock_by_ref(ref), loaded)

    def ask_batch(self, product, direction):
        self.waiting_batch = (product, direction)
        kind = 'n° de série' if product['tracking'] == 'serial' else 'n° de lot'
        p = self.reset_panel('#E8F1FA')
        tk.Label(p, text=('＋ ' if direction == 'in' else '－ ') + str(product.get('label') or product['ref']), bg=p.cget('bg'),
                 font=('DejaVu Sans', 24, 'bold')).pack(side='left', padx=(0, 20))
        tk.Label(p, text=f'Scannez le {kind} :', bg=p.cget('bg'), font=('DejaVu Sans', 19)).pack(side='left')
        entry = tk.Entry(p, font=('DejaVu Sans', 22), width=24)
        entry._virtual_keyboard = True
        entry.pack(side='left', padx=12)
        cancel = self.app.button(p, 'Annuler', self.cancel_batch_prompt, 'secondary')
        cancel.pack(side='right')

        def done(event=None):
            batch = entry.get().strip()
            if not batch:
                return 'break'
            self.waiting_batch = None
            self.start_hold(product, direction, batch)
            return 'break'
        entry.bind('<Return>', done)
        entry.bind('<KP_Enter>', done)
        entry.focus_set()

    def cancel_batch_prompt(self):
        if self.waiting_batch:
            self.waiting_batch = None
            self.hide()

    # ---- délai d'annulation ------------------------------------------------------------
    def start_hold(self, product, direction, batch):
        from stock_ops import build_payload
        reason, comment = REASONS[direction]
        try:
            build_payload(product, direction, 1, batch, reason, comment)  # contrôle immédiat (série présente, stock…)
        except ValueError as e:
            self.show_message(str(e), 'error')
            return
        self.current = {'product': product, 'direction': direction, 'qty': 1, 'batch': batch,
                        'deadline': time.monotonic() + HOLD_SECONDS, 'actor': self.app.session.user, 'client': self.app.client}
        self.app.root.focus_set()  # le prochain scan revient au scan rapide
        self.render_hold()
        self.tick()

    def tick(self):
        if self.after_id:
            try:
                self.app.root.after_cancel(self.after_id)
            except tk.TclError:
                pass
            self.after_id = None
        cur = self.current
        if not cur:
            return
        if time.monotonic() >= cur['deadline']:
            self.commit()
            return
        self.render_hold()
        self.after_id = self.app.root.after(250, self.tick)

    def render_hold(self):
        cur = self.current
        if not cur:
            return
        from stock_ops import fmt
        incoming = cur['direction'] == 'in'
        before = float(cur['product'].get('qty') or 0)
        after = before + cur['qty'] if incoming else before - cur['qty']
        p = self.reset_panel('#E6F4EA' if incoming else '#FDECEC')
        colour = '#1F7A3D' if incoming else '#C62828'
        tk.Label(p, text=label_for(cur['direction'], cur['qty'], cur['product'], cur['batch']), bg=p.cget('bg'), fg=colour,
                 font=('DejaVu Sans', 26, 'bold')).pack(side='left')
        tk.Label(p, text=f'   stock {fmt(before)} → {fmt(after)}', bg=p.cget('bg'), font=('DejaVu Sans', 20)).pack(side='left')
        left = max(0, int(cur['deadline'] - time.monotonic() + 0.999))
        self.app.button(p, f'Annuler ({left})', self.cancel, 'danger_solid', size=21).pack(side='right')
        if cur['product']['tracking'] == 'none':
            tk.Label(p, text='Rescannez pour ajouter une unité' if incoming else 'Rescannez pour retirer une unité de plus', bg=p.cget('bg'), fg='#5A6577',
                     font=('DejaVu Sans', 15)).pack(side='right', padx=20)

    def cancel(self):
        if self.current:
            self.current = None
            self.show_message('Annulé — rien n’a été envoyé à Dolibarr.', 'info')

    # ---- envoi ------------------------------------------------------------------------
    def commit(self):
        """Envoie le mouvement en attente (fin du délai, autre produit scanné, déconnexion)."""
        cur, self.current = self.current, None
        if self.after_id:
            try:
                self.app.root.after_cancel(self.after_id)
            except tk.TclError:
                pass
            self.after_id = None
        if not cur:
            return
        from stock_ops import build_payload, transmit, record
        a = self.app
        reason, comment = REASONS[cur['direction']]
        try:
            payload = build_payload(cur['product'], cur['direction'], cur['qty'], cur['batch'], reason, comment)
            op = a.stock_ui.journal.prepare(cur['actor'], payload, label_for(cur['direction'], cur['qty'], cur['product'], cur['batch']),
                                            allow_stack=True)
        except ValueError as e:
            self.show_message(str(e), 'error')
            return
        a.stock_ui.inflight.add(op['id'])
        self.show_message('Envoi à Dolibarr… ' + op['label'], 'info', keep=True)
        client = cur['client']

        def done(ok, value):
            a.stock_ui.inflight.discard(op['id'])
            status, detail = record(a.stock_ui.journal, op, *(value if ok else ('uncertain', value)))
            if status == 'done':
                from stock_ops import fmt
                self.show_message(f"✓ {op['label']} · stock Dolibarr : {fmt(detail.get('after'))}", 'success')
                if a.session.user == cur['actor'] and a.tab == 2 and not self.waiting_batch and not self.current:
                    a.show(2)
            elif status == 'rejected':
                self.show_message('Refusé par Dolibarr, rien n’a été appliqué : ' + str(detail), 'error')
            else:
                self.show_message('Réponse incertaine : mouvement conservé sur le Pi, « Réessayer » dans Stocks. ' + str(detail), 'warn')
        a.stock_ui.background(lambda: transmit(client, op), done)

    def flush(self):
        self.cancel_batch_prompt()
        self.commit()

    # ---- bandeau ------------------------------------------------------------------------
    def reset_panel(self, bg):
        if self.hide_id:
            try:
                self.app.root.after_cancel(self.hide_id)
            except tk.TclError:
                pass
            self.hide_id = None
        for w in self.panel.winfo_children():
            w.destroy()
        self.panel.config(bg=bg)
        if not self.panel.winfo_ismapped():
            self.panel.pack(side='bottom', fill='x', before=self.app.body)
        return self.panel

    def show_message(self, text, kind='info', keep=False):
        colours = {'info': ('#E8F1FA', '#21528A'), 'success': ('#E6F4EA', '#1F7A3D'),
                   'error': ('#FDECEC', '#9F1F1F'), 'warn': ('#FFF3D6', '#6B4300')}
        bg, fg = colours[kind]
        p = self.reset_panel(bg)
        tk.Label(p, text=text, bg=bg, fg=fg, font=('DejaVu Sans', 20, 'bold'), anchor='w', justify='left',
                 wraplength=1800).pack(fill='x')
        if not keep:
            self.hide_id = self.app.root.after(4000 if kind in ('info', 'success') else 8000, self.hide)

    def hide(self):
        self.hide_id = None
        if self.current or self.waiting_batch:
            return
        if self.panel.winfo_ismapped():
            self.panel.pack_forget()
