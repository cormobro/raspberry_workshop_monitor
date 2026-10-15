"""Mouvements de stock réels : préparation, journal local et reprise sans doublon.

Chaque mouvement reçoit un identifiant unique enregistré sur le Pi AVANT l'envoi.
Une réponse perdue se réessaie avec le même identifiant et le même contenu ; le
module Dolibarr renvoie alors le résultat déjà appliqué au lieu de rejouer le
mouvement. Seul l'opérateur qui l'a créé peut le réessayer.
"""
import json
import math
import os
from pathlib import Path
import sqlite3
import uuid
import datetime as dt
from manufacturing import serial

REASONS = (('reception', 'Réception fournisseur'), ('retour', 'Retour'), ('casse', 'Casse'),
           ('inventaire', 'Correction inventaire'), ('consommation', 'Consommation atelier'), ('autre', 'Autre'))
DIRECTIONS = {'in': 'Entrée', 'out': 'Sortie'}
# Refus certains : le serveur n'a rien appliqué. Tout autre échec reste « incertain ».
CERTAIN_REFUSALS = (400, 401, 403, 404, 409)


def now():
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec='seconds')


def data_dir():
    p = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'atelierborne'
    p.mkdir(parents=True, exist_ok=True)
    return p


def fmt(value):
    """Quantité lisible : 12 plutôt que 12.0."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(n)) if n.is_integer() else f'{n:g}'


def build_payload(product, direction, qty, batch, reason, comment):
    """Contrôles locaux avant envoi ; le serveur refait tous les contrôles."""
    if direction not in DIRECTIONS:
        raise ValueError('Choisissez Entrée ou Sortie.')
    if reason not in dict(REASONS):
        raise ValueError('Choisissez un motif.')
    comment = ' '.join(str(comment or '').split())
    if len(comment) > 200:
        raise ValueError('Précision du motif trop longue (200 caractères maximum).')
    if reason == 'autre' and len(comment) < 3:
        raise ValueError('Précisez le motif « Autre ».')
    if not product.get('physical', True):
        raise ValueError('Ce produit n’est pas un produit physique stocké.')
    tracking = product.get('tracking')
    if tracking == 'serial':
        quantity = 1.0
    else:
        try:
            quantity = float(str(qty).replace(',', '.'))
        except (TypeError, ValueError):
            raise ValueError('Quantité : nombre requis.')
        if not math.isfinite(quantity) or quantity <= 0 or quantity > 1000000:
            raise ValueError('Quantité invalide.')
    code = ''
    if tracking in ('serial', 'lot'):
        try:
            code = serial(batch)
        except ValueError:
            raise ValueError('Scannez le numéro de série.' if tracking == 'serial' else 'Scannez ou saisissez le numéro de lot.')
        present = {str(b.get('batch')): float(b.get('qty') or 0) for b in product.get('batches', [])}
        if direction == 'out' and present and code not in present:
            raise ValueError(f'Le numéro {code} n’est pas en stock dans l’entrepôt.')
        if direction == 'out' and code in present and present[code] + 1e-8 < quantity:
            raise ValueError(f'Quantité insuffisante pour le lot {code} : {fmt(present[code])} disponible(s).')
        if direction == 'in' and tracking == 'serial' and code in present:
            raise ValueError(f'Le numéro {code} est déjà en stock.')
    if direction == 'out' and float(product.get('qty') or 0) + 1e-8 < quantity:
        raise ValueError(f'Stock insuffisant : {fmt(product.get("qty") or 0)} disponible(s).')
    return {'product_id': int(product['id']), 'direction': direction, 'qty': quantity,
            'batch': code, 'reason': reason, 'comment': comment}


class StockJournal:
    def __init__(self, path=None):
        self.path = Path(path or data_dir() / 'stock.sqlite3')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS ops(id TEXT PRIMARY KEY,actor TEXT NOT NULL,label TEXT NOT NULL,created_at TEXT NOT NULL,
            payload TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',response TEXT,updated_at TEXT);
        ''')

    def prepare(self, actor, payload, label, allow_stack=False):
        """Enregistre le mouvement avant tout envoi. Refuse un second mouvement en attente sur le même produit
        (sauf scan rapide : chaque mouvement a son identifiant, le serveur les distingue)."""
        for op in ([] if allow_stack else self.pending(actor)):
            if op['payload']['product_id'] == payload['product_id']:
                raise ValueError('Un mouvement de ce produit attend encore sa confirmation. Réessayez-le d’abord.')
        op = str(uuid.uuid4())
        body = dict(payload, operation_id=op)
        with self.db:
            self.db.execute('INSERT INTO ops(id,actor,label,created_at,payload) VALUES(?,?,?,?,?)',
                            (op, actor, label, now(), json.dumps(body, ensure_ascii=False)))
        return self.get(op)

    def get(self, op):
        r = self.db.execute('SELECT * FROM ops WHERE id=?', (op,)).fetchone()
        if not r:
            raise ValueError('Mouvement inconnu.')
        d = dict(r)
        d['payload'] = json.loads(d['payload'])
        d['response'] = json.loads(d['response']) if d['response'] else None
        return d

    def pending(self, actor):
        rows = self.db.execute("SELECT id FROM ops WHERE status='pending' AND actor=? ORDER BY created_at", (actor,)).fetchall()
        return [self.get(r['id']) for r in rows]

    def _finish(self, op, status, response):
        with self.db:
            cur = self.db.execute("UPDATE ops SET status=?,response=?,updated_at=? WHERE id=? AND status='pending'",
                                  (status, json.dumps(response, ensure_ascii=False), now(), op))
        if cur.rowcount != 1:
            raise ValueError('Ce mouvement a déjà été traité.')

    def complete(self, op, response):
        self._finish(op, 'done', response)

    def reject(self, op, error):
        self._finish(op, 'rejected', {'error': str(error)})

    def history(self, limit=50):
        rows = self.db.execute('SELECT id FROM ops ORDER BY created_at DESC LIMIT ?', (limit,)).fetchall()
        return [self.get(r['id']) for r in rows]


def transmit(client, op):
    """Appel réseau seul (exécutable dans un fil secondaire) : ('done'|'rejected'|'uncertain', détail)."""
    from dolibarr_client import ApiError
    try:
        return 'done', client.stock_move(op['payload'])
    except ApiError as e:
        return ('rejected' if e.code in CERTAIN_REFUSALS else 'uncertain'), str(e)
    except Exception:
        return 'uncertain', 'Résultat incertain.'


def record(journal, op, status, detail):
    """Écriture du résultat dans le journal local, dans le fil qui possède la base SQLite."""
    if status == 'done':
        journal.complete(op['id'], detail)
    elif status == 'rejected':
        journal.reject(op['id'], detail)
    return status, detail


def send(client, journal, op):
    return record(journal, op, *transmit(client, op))
