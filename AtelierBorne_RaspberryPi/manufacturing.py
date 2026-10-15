"""Persistent workshop jobs; SQLite is the durable journal, Excel an editable view."""
import copy
import datetime as dt
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import uuid

STAGES=('Assemblage','Calibrage','Mise en boîte','Terminée')

def now(): return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec='seconds')
def data_dir():
    p=Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))/'atelierborne'/'fabrication'
    p.mkdir(parents=True,exist_ok=True);return p

def serial(value,required=True):
    value=str(value or '').strip()
    if not value and not required:return ''
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}',value):raise ValueError('Numéro de série vide ou invalide.')
    return value

def number(value,label,zero=False):
    try: n=float(str(value).replace(',','.'))
    except (ValueError,TypeError):raise ValueError(f'{label} : nombre requis.')
    if not math.isfinite(n) or (n<0 if zero else n<=0):raise ValueError(f'{label} : valeur invalide.')
    return n

def serial_keys(job):
    for line in job['order']['lines']:
        if line['role']=='toconsume' and int(line['tobatch']):
            q=float(line['qty'])
            if not q.is_integer() or q>100:raise ValueError('Quantité sérialisée non prise en charge.')
            for i in range(1,int(q)+1):yield line,f"serial_{line['id']}_{i}"

def cell_line(job):
    ident=job.get('cell_line_id')
    if ident is None:
        candidates=[l for l in job['order']['lines'] if l['role']=='toconsume' and float(l['qty'])==16 and any(t in (l.get('ref','')+' '+l.get('label','')).lower() for t in ('cell','cornex'))]
        return candidates[0] if len(candidates)==1 else None
    return next((l for l in job['order']['lines'] if str(l['id'])==str(ident)),None)

def align_cells(job):
    line=cell_line(job)
    if line and int(line['tobatch']):
        for i in range(1,17):job['fields'][f"serial_{line['id']}_{i}"]=job['fields'].get(f'cell_{i}_serial','')

def assembly_validation(job):
    f=job['fields'];serial(f.get('battery_serial'));seen=set()
    for line,key in serial_keys(job):
        s=serial(f.get(key));identity=(int(line['product_id']),s.casefold())
        if identity in seen:raise ValueError('Composant scanné deux fois : '+s)
        seen.add(identity)
    cell_serials=set()
    for i in range(1,17):
        cell_sn=serial(f.get(f'cell_{i}_serial'),False)
        if cell_sn and cell_sn.casefold() in cell_serials:raise ValueError('Numéro de cellule répété : '+cell_sn)
        if cell_sn:cell_serials.add(cell_sn.casefold())
        number(f.get(f'cell_{i}_voltage'),f'C{i} tension')
        number(f.get(f'cell_{i}_ir'),f'C{i} résistance',True)
        serial(f.get(f'cell_{i}_serial'),False)
    number(f.get('pack_voltage'),'Tension pack');number(f.get('pack_ir'),'Résistance pack',True)

def final_validation(job):
    assembly_validation(job);f=job['fields'];serial(f.get('seal'))
    number(f.get('capacity_ah'),'Capacité réelle Ah')
    if f.get('calibration_result')!='Conforme':raise ValueError('Le calibrage doit être conforme.')
    if job['stage']!='Mise en boîte':raise ValueError('Terminez les étapes assemblage et calibrage.')

class ManufacturingStore:
    def __init__(self,path=None):
        self.path=Path(path or data_dir()/'fabrication.sqlite3');self.path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.path);self.db.row_factory=sqlite3.Row
        self.db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,mo_id INTEGER UNIQUE,body TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,job TEXT,at TEXT,actor TEXT,before_json TEXT,after_json TEXT);
        CREATE TABLE IF NOT EXISTS pending(id TEXT PRIMARY KEY,job TEXT,kind TEXT,payload TEXT,response TEXT);
        CREATE TABLE IF NOT EXISTS syncbase(model TEXT PRIMARY KEY,body TEXT NOT NULL);
        ''')
    def all(self):return [json.loads(r['body']) for r in self.db.execute('SELECT body FROM jobs ORDER BY rowid DESC')]
    def get(self,jid):
        r=self.db.execute('SELECT body FROM jobs WHERE id=?',(jid,)).fetchone()
        if not r:raise ValueError('Fabrication inconnue.')
        return json.loads(r['body'])
    def delete_local(self,jid,actor):
        """Remove only an unfinished local draft; never calls Dolibarr."""
        job=self.get(jid)
        if job.get('stage')=='Terminée':
            raise ValueError('Une fabrication terminée ne peut pas être supprimée localement.')
        if self.pending(jid):
            raise ValueError('Une opération ERP est en attente. Réessayez-la ou résolvez-la avant suppression.')
        with self.db:
            self.db.execute('DELETE FROM audit WHERE job=?',(jid,))
            self.db.execute('DELETE FROM jobs WHERE id=?',(jid,))
        return job
    def create(self,order,actor,battery=''):
        for job in self.all():
            if int(job['order']['id'])==int(order['id']):return job
        job={'id':str(uuid.uuid4()),'order':order,'stage':'Assemblage','revision':0,'created_at':now(),'fields':{'battery_serial':battery,'assembly_operator':actor,'model':order['model'],'mo_ref':order['ref'],'comments':''}}
        self.save(job,actor);return self.get(job['id'])
    def save(self,job,actor):
        job=copy.deepcopy(job)
        align_cells(job)
        if self.pending(job['id']):raise ValueError('Une opération ERP attend sa réponse. Réessayez cette opération avant de modifier la fiche.')
        rows=self.db.execute('SELECT body,revision FROM jobs WHERE id=?',(job['id'],)).fetchone()
        if rows and int(job.get('revision',0))!=rows['revision']:raise ValueError('La fiche a changé. Rouvrez-la.')
        self._duplicates(job)
        old=json.loads(rows['body']) if rows else None
        job['revision']=(rows['revision'] if rows else 0)+1;job['updated_at']=now()
        with self.db:
            self.db.execute('INSERT INTO jobs VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body,revision=excluded.revision',(job['id'],int(job['order']['id']),json.dumps(job,ensure_ascii=False),job['revision']))
            self.db.execute('INSERT INTO audit(job,at,actor,before_json,after_json) VALUES(?,?,?,?,?)',(job['id'],now(),actor,json.dumps(old,ensure_ascii=False),json.dumps(job,ensure_ascii=False)))
        return job
    def _duplicates(self,job):
        f=job['fields'];battery=f.get('battery_serial','');current=set((str(l['product_id']),str(f.get(k)).casefold()) for l,k in serial_keys(job) if f.get(k))
        for other in self.all():
            if other['id']==job['id']:continue
            if battery and other['fields'].get('battery_serial')==battery:raise ValueError('Numéro de batterie déjà utilisé sur la borne.')
            used=set((str(l['product_id']),str(other['fields'].get(k)).casefold()) for l,k in serial_keys(other) if other['fields'].get(k))
            mine_cells={str(f.get(f'cell_{i}_serial','')).casefold() for i in range(1,17)}-{''}
            other_cells={str(other['fields'].get(f'cell_{i}_serial','')).casefold() for i in range(1,17)}-{''}
            if mine_cells & other_cells:raise ValueError('Une cellule est déjà affectée à une autre batterie.')
            if current & used:raise ValueError('Un composant est déjà affecté à une autre batterie sur la borne.')
            if f.get('seal') and f.get('seal')==other['fields'].get('seal'):raise ValueError('Numéro de scellé déjà utilisé.')
    def transition(self,jid,actor):
        job=self.get(jid);f=job['fields']
        if job['stage']=='Assemblage':
            assembly_validation(job);job['stage']='Calibrage';f['assembly_operator']=actor;f['assembly_date']=now()
        elif job['stage']=='Calibrage':
            number(f.get('capacity_ah'),'Capacité réelle Ah')
            if f.get('calibration_result')!='Conforme':raise ValueError('Calibrage non conforme : corrigez la batterie avant de poursuivre.')
            job['stage']='Mise en boîte';f['calibration_operator']=actor;f['calibration_date']=now()
        else:raise ValueError('Utilisez la validation finale pour terminer la batterie.')
        return self.save(job,actor)
    def enqueue(self,jid,kind,payload):
        found=self.pending(jid)
        if found:
            if found['kind']!=kind:raise ValueError('Une autre opération ERP est en attente.')
            return found
        payload=copy.deepcopy(payload);op=str(uuid.uuid4());payload['operation_id']=op
        with self.db:self.db.execute('INSERT INTO pending(id,job,kind,payload) VALUES(?,?,?,?)',(op,jid,kind,json.dumps(payload,ensure_ascii=False)))
        return self.pending(jid)
    def reject(self,op,error):
        with self.db:self.db.execute('UPDATE pending SET response=? WHERE id=?',(json.dumps({'rejected':str(error)}),op['id']))
    def pending(self,jid):
        r=self.db.execute('SELECT * FROM pending WHERE job=? AND response IS NULL',(jid,)).fetchone()
        if not r:return None
        d=dict(r);d['payload']=json.loads(d['payload']);return d
    def complete(self,op,response,actor):
        # Job update and acknowledgement share one local transaction.
        with self.db:
            self.db.execute('UPDATE pending SET response=? WHERE id=?',(json.dumps(response),op['id']))
            if op['kind']=='create':return self.create(response,actor)
            job=self.get(op['job'])
            if op['kind']=='finalize':
                job['stage']='Terminée';job['receipt']=response;job['fields']['validation_operator']=response['validated_by'];job['fields']['validation_date']=response['validated_at'];job['fields']['mo_ref']=response['mo_ref']
            elif op['kind']=='scrap':
                key=op['payload'].get('field_key')
                if key:job['fields'][key]=''
                job.setdefault('scrap',[]).append(response)
            elif op['kind']=='correction':job['last_correction_revision']=job['revision']+1
            return self.save(job,actor)
    def final_payload(self,jid):
        job=self.get(jid);final_validation(job)
        return {'document_id':job['id'],'mo_id':int(job['order']['id']),'signature':job['order']['signature'],'cell_line_id':cell_line(job)['id'] if cell_line(job) else 0,'fields':job['fields']}
    def base(self,model):
        r=self.db.execute('SELECT body FROM syncbase WHERE model=?',(model,)).fetchone();return json.loads(r[0]) if r else {}
    def set_base(self,model,body):
        with self.db:self.db.execute('INSERT INTO syncbase VALUES(?,?) ON CONFLICT(model) DO UPDATE SET body=excluded.body',(model,json.dumps(body)))
    def history(self,jid):return [dict(r) for r in self.db.execute('SELECT at,actor,before_json,after_json FROM audit WHERE job=? ORDER BY id',(jid,))]
