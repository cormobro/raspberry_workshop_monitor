"""Native tactile manufacturing workflow; no browser required."""
import copy
import html
import json
import re
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk
from touch_ui import TouchCombo, messagebox
from manufacturing import ManufacturingStore, now, serial_keys, assembly_validation, final_validation, data_dir, cell_line, STAGES
import theme
from manufacturing_excel import export_local, sync_nas, MergeConflict
from dolibarr_client import ApiError, config_path

MODEL_COLUMNS=3
CARD_SIZE=300
CARD_BORDER='#DCE3EC'
CARD_SELECTED='#2E6DB4'

def job_model_name(job):
    """Nom du produit fabriqué (module 0.6.2+), sinon sa référence."""
    order=job.get('order',{})
    return html.unescape(str(order.get('model_label') or order.get('model') or '')).strip()

def fmt_qty(value):
    try:n=float(value)
    except (TypeError,ValueError):return str(value)
    return str(int(n)) if n.is_integer() else f'{n:g}'

FIELD_LABELS={'battery_serial':'Numéro de batterie','comments':'Commentaires','pack_voltage':'Tension pack (V)','pack_ir':'Résistance pack (mΩ)',
    'capacity_ah':'Capacité réelle (Ah)','calibration_result':'Résultat du calibrage','seal':'Scellé de garantie','model':'Modèle','mo_ref':'Référence OF',
    'assembly_operator':'Opérateur assemblage','assembly_date':'Date assemblage','calibration_operator':'Opérateur calibrage','calibration_date':'Date calibrage',
    'validation_operator':'Validé par','validation_date':'Date de validation'}

def field_label(key):
    """Nom lisible d'un champ de fiche : cell_3_voltage → C3 tension (V)."""
    m=re.fullmatch(r'cell_(\d+)_(serial|voltage|ir)',key)
    if m:return 'C'+m.group(1)+' '+{'serial':'n° de série','voltage':'tension (V)','ir':'résistance (mΩ)'}[m.group(2)]
    m=re.fullmatch(r'serial_(\d+)_(\d+)',key)
    if m:return 'Composant (ligne '+m.group(1)+') n° '+m.group(2)
    return FIELD_LABELS.get(key,key)

def history_lines(rows):
    """[(date lisible, opérateur, ['C3 tension (V) : 3,21 → 3,24', …])] ; les copies internes de C1-C16 sont masquées."""
    out=[]
    for r in rows:
        old=json.loads(r['before_json'] or 'null') or {};new=json.loads(r['after_json'])
        of,nf=old.get('fields',{}),new.get('fields',{});changes=[]
        if old and old.get('stage')!=new.get('stage'):changes.append(f"Étape : {old.get('stage')} → {new.get('stage')}")
        for k,v in nf.items():
            if of.get(k,'')==v or (not old and v in ('',None)):continue
            if k.startswith('serial_') and any(k==f"serial_{l.get('id')}_{i}" for l in [cell_line(new) or {}] for i in range(1,17)):continue
            before=of.get(k,'')
            changes.append(f"{field_label(k)} : {before or '—'} → {v or '—'}" if old else f"{field_label(k)} : {v}")
        if not old:changes.insert(0,'Fiche créée')
        if changes:
            when=str(r['at']).replace('T',' ')[:16]
            out.append((when,r['actor'],changes))
    return out

def model_name(row):
    """Name shown to the operator: the manufactured product, never the BOM reference."""
    return html.unescape(str(row.get('product_label') or row.get('product_ref') or 'Produit sans nom')).strip()

def model_image_path(row):
    """Optional photo: <data>/atelierborne/modeles/<product_ref>.png (about 280 x 160 px)."""
    ref=re.sub(r'[^A-Za-z0-9._-]','_',str(row.get('product_ref') or ''))
    return data_dir().parent/'modeles'/(ref+'.png') if ref else None

def model_card(parent,row):
    card=tk.Frame(parent,bg='white',width=CARD_SIZE,height=CARD_SIZE,highlightthickness=4,highlightbackground=CARD_BORDER,cursor='hand2')
    card.pack_propagate(False)
    photo=tk.Frame(card,bg='#eef1f6',height=165);photo.pack(fill='x',padx=8,pady=(8,4));photo.pack_propagate(False)
    image=None;path=model_image_path(row)
    if path and path.exists():
        try:image=tk.PhotoImage(file=str(path))
        except tk.TclError:image=None
    if image is not None:
        label=tk.Label(photo,image=image,bg='#eef1f6');label.image=image
    else:
        label=tk.Label(photo,text='Photo à venir',fg='#8a94a6',bg='#eef1f6',font=('DejaVu Sans',15))
    label.pack(expand=True)
    tk.Label(card,text=model_name(row),bg='white',font=('DejaVu Sans',20,'bold'),wraplength=CARD_SIZE-24,justify='center').pack(fill='x',padx=8)
    tk.Label(card,text=str(row.get('product_ref') or ''),bg='white',fg='#5a6577',font=('DejaVu Sans',13)).pack(side='bottom',pady=(0,8))
    return card

def bind_tap(widget,callback):
    """Tap on the card or anything inside it. A scroll drag is swallowed by TouchGestures first."""
    widget.bind('<ButtonRelease-1>',callback)
    for child in widget.winfo_children():bind_tap(child,callback)

class ManufacturingUI:
    def __init__(self,app):
        self.app=app;self.store=ManufacturingStore();self.current=None;self.vars={};self.autosave=None;self.busy=False
    def flush(self):
        if self.autosave:
            self.app.root.after_cancel(self.autosave);self.autosave=None
        if self.current and self.vars:
            self.save(silent=True)
    def field_values(self):return {k:v.get().strip() for k,v in self.vars.items()}
    def save(self,silent=False):
        if not self.current or self.busy:return True
        try:
            job=self.store.get(self.current)
            values=self.field_values()
            if all(str(job['fields'].get(k,''))==v for k,v in values.items()):return True
            job['fields'].update(values);self.store.save(job,self.app.session.user or 'local')
            if hasattr(self,'status') and self.status.winfo_exists():self.status.config(text='Brouillon enregistré sur le Pi · '+now()[11:19],fg=theme.SUCCESS)
            return True
        except Exception as e:
            if hasattr(self,'status') and self.status.winfo_exists():self.status.config(text=str(e),fg=theme.DANGER)
            if not silent:messagebox.showerror('Enregistrement',str(e),parent=self.app.root)
            return False
    def changed(self,*args):
        if self.autosave:self.app.root.after_cancel(self.autosave)
        self.autosave=self.app.root.after(400,self.save_scheduled)
    def save_scheduled(self):self.autosave=None;self.save(silent=True)
    def reset(self):
        if not self.save():return False
        self.app.keyboard.close();self.current=None;self.vars={}
        for w in self.app.body.winfo_children():w.destroy()
        return True
    def run(self,action,done,failed=None):
        if self.busy:return
        self.busy=True
        self.app.keyboard.close()
        disabled=[]
        def disable_tree(w):
            for child in w.winfo_children():
                try:
                    state=child.cget('state');child.configure(state='disabled');disabled.append((child,state))
                except tk.TclError:pass
                disable_tree(child)
        disable_tree(self.app.body)
        for b in self.app.tabs:b.config(state='disabled')
        self.app.logout_button.config(state='disabled')
        result=queue.Queue()
        def worker():
            try:result.put((True,action()))
            except Exception as e:result.put((False,e))
        def poll():
            try:ok,value=result.get_nowait()
            except queue.Empty:self.app.root.after(100,poll);return
            self.busy=False
            for widget,state in disabled:
                if widget.winfo_exists():widget.configure(state=state)
            for b in self.app.tabs:b.config(state='normal')
            self.app.logout_button.config(state='normal')
            if ok:
                try:done(value)
                except Exception as e:messagebox.showerror('Fabrication',str(e),parent=self.app.root)
            else:
                if failed:failed(value)
                messagebox.showerror('Fabrication',str(value),parent=self.app.root)
        threading.Thread(target=worker,daemon=True).start();self.app.root.after(100,poll)
    def request(self,route,payload=None):
        client=self.app.client
        if not client or not self.app.personal:raise ValueError('Associez votre compte personnel Dolibarr pour la fabrication.')
        return client._request('atelierborne/manufacturing/'+route,method='POST' if payload is not None else 'GET',payload=payload)
    def home(self,tests=False):
        if not self.reset():return
        a=self.app;a.label(a.body,'Calibrage / Mise en boîte' if tests else 'Fabrication',True)
        a.label(a.body,'Scans et mesures enregistrés sur le Pi. Le stock Dolibarr change uniquement à la validation finale.',muted=True)
        bar=a.toolbar()
        if not tests:
            a.button(bar,'＋ Nouvel OF',self.new_order).pack(side='left',padx=(0,8))
            a.button(bar,'OF Dolibarr',self.orders,'secondary').pack(side='left',padx=(0,8))
        a.button(bar,'Excel / NAS',self.exports,'secondary').pack(side='left')
        if self.store.pending('__create__'):a.button(a.body,'Reprendre la création d’OF en attente',lambda:self.submit(self.store.pending('__create__'))).pack(anchor='w',pady=4)
        frame=a.listing();jobs=[j for j in self.store.all() if not tests or j['stage'] in ('Calibrage','Mise en boîte')]
        if not jobs:a.label(frame,'Aucune batterie à calibrer ou mettre en boîte.' if tests else 'Aucune fabrication commencée. Touchez « Nouvel OF » pour commencer.',muted=True)
        for j in jobs:
            f=a.card(frame)
            right=tk.Frame(f,bg='white');right.pack(side='right')
            left=tk.Frame(f,bg='white');left.pack(side='left',fill='x',expand=True)
            serial=j['fields'].get('battery_serial')
            tk.Label(left,text=serial or 'Numéro de batterie à scanner',bg='white',fg=theme.INK if serial else theme.WARN,font=(theme.FONT,24,'bold'),anchor='w').pack(fill='x')
            info=tk.Frame(left,bg='white');info.pack(fill='x',pady=(6,0))
            theme.stage_pill(info,j['stage']).pack(side='left')
            tk.Label(info,text='   '+job_model_name(j),bg='white',fg=theme.MUTED,font=(theme.FONT,17)).pack(side='left')
            if self.store.pending(j['id']):theme.pill(info,'Opération ERP en attente',theme.WARN_SOFT,'#6B4300').pack(side='left',padx=10)
            if j['stage']!='Terminée' and not self.store.pending(j['id']):
                a.button(right,'Supprimer du Pi',lambda jid=j['id']:self.delete_local(jid,tests),'danger').pack(side='left',padx=6)
            a.button(right,'Ouvrir',lambda jid=j['id']:self.edit(jid)).pack(side='left',padx=6)
    def new_order(self):
        a=self.app;w=a.dialog('Créer un OF pour une batterie')
        a.label(w,'Touchez le modèle de batterie à fabriquer.')
        grid=tk.Frame(w,bg='white');grid.pack(fill='x',pady=6)
        selected={'bom_ref':'','name':'','card':None}
        footer=tk.Frame(w,bg='white');footer.pack(fill='x',pady=12)
        choice=a.label(footer,'Aucun modèle sélectionné.')
        def select(row,card):
            if selected['card'] is not None and selected['card'].winfo_exists():selected['card'].config(highlightbackground=CARD_BORDER)
            card.config(highlightbackground=CARD_SELECTED)
            selected.update(bom_ref=str(row.get('bom_ref') or ''),name=model_name(row),card=card)
            choice.config(text='Modèle choisi : '+selected['name'])
            go.config(state='normal')
        def loaded(rows):
            if not w.winfo_exists():return
            for child in grid.winfo_children():child.destroy()
            if not rows:a.label(grid,'Aucune nomenclature de fabrication active disponible.');return
            for i,row in enumerate(rows):
                card=model_card(grid,row)
                card.grid(row=i//MODEL_COLUMNS,column=i%MODEL_COLUMNS,padx=10,pady=10,sticky='n')
                bind_tap(card,lambda e,r=row,c=card:select(r,c))
            for col in range(MODEL_COLUMNS):grid.columnconfigure(col,weight=1)
        self.run(lambda:self.app.client.paginate('atelierborne/manufacturing/boms') if self.app.client and self.app.personal else self.request('boms'),loaded)
        def create():
            if not selected['bom_ref']:
                messagebox.showwarning('Modèle','Touchez d’abord une carte de modèle.',parent=self.app.root);return
            op=self.store.enqueue('__create__','create',{'bom_ref':selected['bom_ref']});a.keyboard.close();w.destroy();self.submit(op)
        go=a.button(footer,'Créer l’OF',create);go.pack(fill='x',pady=6);go.config(state='disabled')
    def orders(self):
        if not self.reset():return
        a=self.app;a.label(a.body,'OF ouverts dans Dolibarr',True)
        a.label(a.body,'Une batterie par OF. « Préparer » ouvre ou crée la fiche sur le Pi.',muted=True)
        bar=a.toolbar();a.button(bar,'‹ Fabrication',self.home,'secondary').pack(side='left')
        def done(rows):
            frame=a.listing()
            if not rows:a.label(frame,'Aucun OF ouvert pour une quantité de 1.',muted=True)
            local={str(j['order'].get('id')):j for j in self.store.all()}
            for r in rows:
                lj=local.get(str(r['id']));serial=(lj or {}).get('fields',{}).get('battery_serial','') if lj else ''
                product=html.unescape(str(r.get('product_label') or r.get('product_ref') or r.get('label') or 'Produit fabriqué'))
                f=a.card(frame)
                right=tk.Frame(f,bg='white');right.pack(side='right')
                left=tk.Frame(f,bg='white');left.pack(side='left',fill='x',expand=True)
                tk.Label(left,text=serial or 'Numéro de batterie à scanner',bg='white',fg=theme.INK if serial else theme.WARN,font=(theme.FONT,24,'bold'),anchor='w').pack(fill='x')
                tk.Label(left,text=product+'   ·   '+str(r.get('ref') or ''),bg='white',fg=theme.MUTED,font=(theme.FONT,17),anchor='w').pack(fill='x',pady=(6,0))
                if int(r.get('status',-1)) in (0,1,2):
                    a.button(right,'Supprimer dans Dolibarr',lambda ident=r['id'],ref=r['ref']:self.delete_remote(ident,ref),'danger').pack(side='left',padx=6)
                a.button(right,'Préparer',lambda ident=r['id']:self.load_order(ident)).pack(side='left',padx=6)
        self.run(lambda:a.client.paginate('atelierborne/manufacturing/orders') if a.client and a.personal else self.request('orders'),done)
    def load_order(self,ident):
        actor=self.app.session.user
        self.run(lambda:self.request('orders/'+str(ident)),lambda order:self.edit(self.store.create(order,actor)['id']))
    def submit(self,op):
        actor=self.app.session.user
        def done(response):
            job=self.store.complete(op,response,actor)
            self.current=None;self.vars={};self.edit(job['id'])
            try:export_local(self.store,job['order']['model'])
            except Exception as e:messagebox.showwarning('Export Excel en attente',str(e),parent=self.app.root)
        def failed(error):
            if isinstance(error,ApiError) and error.code in (400,401,403,404,409):
                self.store.reject(op,error)
                if op['job']!='__create__':
                    self.current=None;self.vars={};self.edit(op['job'])
        self.run(lambda:self.request(op['kind'],op['payload']),done,failed)
    def next_entry(self,event):
        w=event.widget.tk_focusNext();start=w
        while w is not event.widget:
            if isinstance(w,(tk.Entry,ttk.Entry)) and str(w.cget('state'))=='normal':
                w.focus_set();return 'break'
            w=w.tk_focusNext()
            if w is start:break
        return 'break'
    def input(self,parent,label,key,value='',width=24,scan=False,readonly=False):
        a=self.app;row=tk.Frame(parent,bg='white');row.pack(fill='x',pady=4)
        tk.Label(row,text=label,bg='white',fg=theme.MUTED,anchor='w',width=22,font=(theme.FONT,18)).pack(side='left')
        var=tk.StringVar(value=str(value if value is not None else ''));self.vars[key]=var
        ent=tk.Entry(row,textvariable=var,width=width,font=(theme.FONT,20),state='readonly' if readonly else 'normal');ent.pack(side='left',fill='x',expand=True)
        ent._numeric=key in ('pack_voltage','pack_ir','capacity_ah')
        if scan:ent._virtual_keyboard=True  # Scanner acts as a keyboard; avoid stealing focus.
        ent.bind('<Return>',self.next_entry)
        if scan and not readonly:a.button(row,'Clavier',lambda:self.app.keyboard.open(ent),'secondary',size=16,pady=10).pack(side='right',padx=(8,0))
        var.trace_add('write',self.changed);return ent
    def stepper(self,parent,stage):
        row=tk.Frame(parent,bg=parent.cget('bg'));row.pack(fill='x',pady=(0,6))
        reached=True
        for i,name in enumerate(STAGES):
            current=name==stage
            bg,fg=(theme.PRIMARY,'white') if current else ((theme.PRIMARY_SOFT,theme.PRIMARY_DARK) if reached else ('#ECEFF3','#8A94A6'))
            tk.Label(row,text=f'{i+1}. {name}',bg=bg,fg=fg,font=(theme.FONT,16,'bold' if current else 'normal'),padx=18,pady=8).pack(side='left')
            if i<len(STAGES)-1:tk.Label(row,text='›',bg=row.cget('bg'),fg='#8A94A6',font=(theme.FONT,22)).pack(side='left',padx=6)
            if current:reached=False
    def section(self,parent,title,note=None):
        card=self.app.card(parent)
        tk.Label(card,text=title,bg='white',fg=theme.INK,font=(theme.FONT,21,'bold'),anchor='w').pack(fill='x')
        if note:tk.Label(card,text=note,bg='white',fg=theme.MUTED,font=(theme.FONT,16),anchor='w',justify='left',wraplength=1600).pack(fill='x',pady=(2,6))
        return card
    def edit(self,jid):
        if not self.reset():return
        self.current=jid;a=self.app;j=self.store.get(jid);f=j['fields'];pending=self.store.pending(jid);ro=bool(pending)
        head=tk.Frame(a.body,bg=a.body.cget('bg'));head.pack(fill='x')
        tk.Label(head,text=f.get('battery_serial') or 'Numéro de batterie à scanner',bg=head.cget('bg'),fg=theme.INK,font=(theme.FONT,27,'bold')).pack(side='left')
        tk.Label(head,text='   '+job_model_name(j),bg=head.cget('bg'),fg=theme.MUTED,font=(theme.FONT,19)).pack(side='left')
        self.stepper(a.body,j['stage'])
        bar=a.toolbar()
        a.button(bar,'‹ Liste',self.home,'secondary').pack(side='left',padx=(0,8))
        a.button(bar,'Enregistrer / Excel',self.save_export,'secondary').pack(side='left',padx=(0,8))
        a.button(bar,'Historique',lambda:self.history(jid),'secondary').pack(side='left',padx=(0,8))
        if pending:a.button(bar,'Réessayer l’opération ERP',lambda:self.submit(pending)).pack(side='right')
        elif j['stage'] in ('Assemblage','Calibrage'):a.button(bar,'Étape terminée ›',self.advance).pack(side='right')
        elif j['stage']=='Mise en boîte':a.button(bar,'Valider la fabrication',self.finalize).pack(side='right')
        else:a.button(bar,'Publier la correction ERP',self.correction).pack(side='right')
        if j['stage']!='Terminée' and not pending:
            a.button(bar,'Supprimer du Pi',self.delete_local,'danger').pack(side='right',padx=8)
        self.status=a.label(a.body,'Brouillon sur le Pi · aucun mouvement de stock avant la validation finale' if j['stage']!='Terminée' else 'Fabrication enregistrée dans Dolibarr. Les corrections documentaires ne changent pas le stock.',muted=True)
        body=a.listing()
        top=self.section(body,'Batterie')
        self.input(top,'Numéro de batterie','battery_serial',f.get('battery_serial',''),scan=True,readonly=ro)
        self.input(top,'Commentaires','comments',f.get('comments',''),readonly=ro)
        cl=cell_line(j)
        for line in j['order']['lines']:
            if line['role']!='toconsume':continue
            card=self.section(body,html.unescape(str(line.get('label') or line['ref'])),f"{line['ref']} · quantité {fmt_qty(line['qty'])}")
            if cl and line['id']==cl['id'] and int(line['tobatch']):
                tk.Label(card,text='Scannez les numéros directement aux positions C1 à C16 ci-dessous.',bg='white',fg=theme.MUTED).pack(anchor='w')
            elif int(line['tobatch']):
                for l,key in serial_keys(j):
                    if l['id']!=line['id']:continue
                    self.input(card,'N° de série '+key.rsplit('_',1)[-1],key,f.get(key,''),scan=True,readonly=ro)
                    actions=tk.Frame(card,bg='white');actions.pack(fill='x',pady=(2,0))
                    a.button(actions,'Vérifier en stock',lambda line=line,key=key:self.check_serial(line,key),'secondary',size=16,pady=10).pack(side='left')
                    if j['stage']!='Terminée' and not pending:a.button(actions,'Défectueux → rebut',lambda line=line,key=key:self.scrap(line,key),'danger',size=16,pady=10).pack(side='left',padx=8)
            else:
                tk.Label(card,text='Consommation automatique de la quantité prévue à la validation finale.',bg='white',fg=theme.MUTED).pack(anchor='w')
                if j['stage']!='Terminée' and not pending:a.button(card,'Une unité défectueuse → rebut',lambda line=line:self.scrap(line,None),'danger',size=16,pady=10).pack(anchor='w',pady=(4,0))
        cells=self.section(body,'Cellules','C1 côté négatif du pack · touche « Suivant › » du clavier pour enchaîner les mesures')
        halves=tk.Frame(cells,bg='white');halves.pack(fill='x')
        for half,(first,last) in enumerate(((1,8),(9,16))):
            grid=tk.Frame(halves,bg='white');grid.grid(row=0,column=half,sticky='new',padx=(0,30) if half==0 else (0,0))
            halves.columnconfigure(half,weight=1,uniform='halves')
            for col,label in enumerate(('','N° série (facultatif)','Tension V','Résist. mΩ')):
                tk.Label(grid,text=label,bg='white',fg=theme.MUTED,font=(theme.FONT,15,'bold')).grid(row=0,column=col,padx=3,pady=(2,4),sticky='w')
            grid.columnconfigure(1,weight=3);grid.columnconfigure(2,weight=1);grid.columnconfigure(3,weight=1)
            for r,i in enumerate(range(first,last+1),1):
                tk.Label(grid,text=f'C{i}',bg='white',fg=theme.PRIMARY_DARK,font=(theme.FONT,18,'bold'),width=3).grid(row=r,column=0,pady=3)
                for col,name in enumerate(('serial','voltage','ir'),1):
                    key=f'cell_{i}_{name}';var=tk.StringVar(value=str(f.get(key,'')));self.vars[key]=var
                    ent=tk.Entry(grid,textvariable=var,width=16 if col==1 else 7,font=(theme.FONT,18),state='readonly' if pending else 'normal')
                    ent.grid(row=r,column=col,padx=3,pady=3,sticky='ew')
                    ent._numeric=col in (2,3)
                    if col==1:ent._virtual_keyboard=True
                    ent.bind('<Return>',self.next_entry);var.trace_add('write',self.changed)
        if cl and int(cl['tobatch']) and not pending:
            line=tk.Frame(cells,bg='white');line.pack(anchor='w',pady=(10,0))
            tk.Label(line,text='Cellule défectueuse en position ',bg='white').pack(side='left')
            pos=TouchCombo(line,values=[str(i) for i in range(1,17)],state='readonly',width=4);pos.set('1');pos.pack(side='left')
            a.button(line,'→ rebut',lambda:self.scrap_cell(cl,int(pos.get())),'danger',size=16,pady=10).pack(side='left',padx=8)
        pack=self.section(body,'Pack et calibrage')
        self.input(pack,'Tension pack (V)','pack_voltage',f.get('pack_voltage',''),readonly=ro)
        self.input(pack,'Résistance pack (mΩ)','pack_ir',f.get('pack_ir',''),readonly=ro)
        self.input(pack,'Capacité réelle (Ah)','capacity_ah',f.get('capacity_ah',''),readonly=ro)
        if j['stage']!='Assemblage':
            row=tk.Frame(pack,bg='white');row.pack(fill='x',pady=(8,4))
            tk.Label(row,text='Résultat du calibrage',bg='white',fg=theme.MUTED,anchor='w',width=22,font=(theme.FONT,18)).pack(side='left')
            var=tk.StringVar(value=f.get('calibration_result',''));self.vars['calibration_result']=var
            choices={}
            def paint(*_):
                for value,b in choices.items():
                    on=var.get()==value;colour=theme.SUCCESS if value=='Conforme' else theme.DANGER
                    b.config(bg=colour if on else 'white',fg='white' if on else colour,highlightbackground=colour)
            for value in ('Conforme','Non conforme'):
                b=tk.Button(row,text=value,command=lambda v=value:var.set(v),font=(theme.FONT,19,'bold'),relief='flat',bd=0,highlightthickness=2,padx=26,pady=12,state='disabled' if pending else 'normal')
                b.pack(side='left',padx=(0,10));choices[value]=b
            var.trace_add('write',paint);var.trace_add('write',self.changed);paint()
        if j['stage'] in ('Mise en boîte','Terminée'):
            self.input(pack,'Scellé de garantie','seal',f.get('seal',''),scan=True,readonly=ro)
        if j['stage']!='Terminée' and not pending:a.button(body,'Recharger les composants de l’OF',self.refresh_order,'secondary').pack(anchor='w',pady=8)
    def refresh_order(self):
        if not self.save():return
        j=self.store.get(self.current)
        def done(order):
            if order['signature']==j['order']['signature']:
                messagebox.showinfo('OF','La nomenclature de cet OF est inchangée.',parent=self.app.root);return
            if not messagebox.askyesno('OF modifié','Remplacer la liste des composants ? Les numéros des composants devront être revérifiés. Les anciennes saisies restent dans l’historique.',parent=self.app.root):return
            j['order']=order;j['stage']='Assemblage'
            for k in list(j['fields']):
                if k.startswith('serial_'):del j['fields'][k]
            self.store.save(j,self.app.session.user);self.current=None;self.vars={};self.edit(j['id'])
        self.run(lambda:self.request('orders/'+str(j['order']['id'])),done)
    def save_export(self):
        if not self.save():return
        try:
            j=self.store.get(self.current);p=export_local(self.store,j['order']['model']);self.status.config(text='Excel enregistré : '+str(p))
        except Exception as e:messagebox.showerror('Excel',str(e),parent=self.app.root)
    def delete_local(self,jid=None,tests=False):
        if jid is not None:
            self.current=jid
        if not self.current:
            return
        try:j=self.store.get(self.current)
        except ValueError:return
        if self.store.pending(j['id']):
            messagebox.showwarning('Suppression impossible','Une opération ERP est en attente pour cette fiche. Réessayez-la ou résolvez-la avant suppression.',parent=self.app.root);return
        if not messagebox.askyesno('Supprimer du Pi',f"Supprimer la fiche locale de {j['fields'].get('battery_serial') or j['order']['ref']} ?\n\nCela ne modifie pas Dolibarr et ne change aucun stock.",parent=self.app.root):return
        model=j['order']['model']
        self.store.delete_local(j['id'],self.app.session.user or 'local')
        self.current=None;self.vars={}
        try:export_local(self.store,model)
        except Exception as e:messagebox.showwarning('Excel local',str(e),parent=self.app.root)
        self.home(tests=bool(tests))
    def delete_remote(self,mo_id,ref):
        if not messagebox.askyesno('Supprimer dans Dolibarr',f'Supprimer l’OF {ref} non terminé dans Dolibarr ?\n\nLa suppression est refusée si un mouvement de stock existe.',parent=self.app.root):return
        import uuid
        payload={'operation_id':str(uuid.uuid4()),'mo_id':int(mo_id)}
        def done(response):
            # Remove only the matching unfinished local draft, if one exists.
            for job in self.store.all():
                if int(job['order'].get('id',0))==int(mo_id) and job.get('stage')!='Terminée' and not self.store.pending(job['id']):
                    self.store.delete_local(job['id'],self.app.session.user or 'local')
                    try:export_local(self.store,job['order']['model'])
                    except Exception:pass
            messagebox.showinfo('OF supprimé','L’OF non terminé a été supprimé de Dolibarr.',parent=self.app.root)
            self.orders()
        self.run(lambda:self.request('delete',payload),done)
    def advance(self):
        if not self.save():return
        try:
            j=self.store.get(self.current)
            if not messagebox.askyesno('Terminer l’étape',f"Confirmer la fin de l’étape {j['stage']} ?",parent=self.app.root):return
            self.store.transition(j['id'],self.app.session.user);self.current=None;self.vars={};self.edit(j['id']);self.save_export()
        except Exception as e:messagebox.showerror('Étape incomplète',str(e),parent=self.app.root)
    def finalize(self):
        if not self.save():return
        try:
            payload=self.store.final_payload(self.current)
            if not messagebox.askyesno('Valider la fabrication','Consommer les composants, créer UNE batterie en stock et terminer l’OF dans Dolibarr ?',parent=self.app.root):return
            op=self.store.enqueue(self.current,'finalize',payload);self.submit(op)
        except Exception as e:messagebox.showerror('Validation',str(e),parent=self.app.root)
    def correction(self):
        if not self.save():return
        j=self.store.get(self.current)
        if not messagebox.askyesno('Correction documentaire','Ajouter cette version aux notes de l’OF ? Les numéros des mouvements de stock restent inchangés.',parent=self.app.root):return
        self.submit(self.store.enqueue(j['id'],'correction',{'document_id':j['id'],'mo_id':j['order']['id'],'fields':j['fields']}))
    def check_serial(self,line,key):
        from urllib.parse import urlencode
        value=self.vars[key].get().strip()
        self.run(lambda:self.request('serial?'+urlencode({'product_id':line['product_id'],'serial':value})),lambda r:messagebox.showinfo('Stock','Numéro disponible en stock.',parent=self.app.root))
    def scrap_cell(self,line,position):
        if not self.save():return
        # Reuse the regular stock operation, but clear the position field too.
        self.scrap(line,f'cell_{position}_serial')
    def scrap(self,line,key):
        if not self.save():return
        a=self.app;j=self.store.get(self.current);w=a.dialog('Déclarer une unité défectueuse')
        a.label(w,line['ref']+' · '+(j['fields'].get(key,'') if key else '1 unité'))
        a.label(w,'Motif obligatoire');reason=tk.Entry(w);reason.pack(fill='x')
        a.label(w,'Une unité sera retirée du stock immédiatement. Elle ne sera pas consommée lors de la validation finale.')
        def go():
            if not messagebox.askyesno('Rebut','Confirmer la sortie définitive d’une unité ?',parent=w):return
            op=self.store.enqueue(j['id'],'scrap',{'mo_id':j['order']['id'],'line_id':line['id'],'serial':j['fields'].get(key,'') if key else '', 'field_key':key,'reason':reason.get()});a.keyboard.close();w.destroy();self.submit(op)
        a.button(w,'Sortir du stock',go,'danger_solid').pack(pady=14,fill='x')
    def history(self,jid):
        w=self.app.dialog('Historique de la fiche')
        rows=history_lines(self.store.history(jid))
        if not rows:self.app.label(w,'Aucune modification enregistrée.',muted=True)
        for when,actor,changes in reversed(rows):
            card=tk.Frame(w,bg='#F7F9FC',padx=14,pady=8,highlightthickness=1,highlightbackground=theme.BORDER);card.pack(fill='x',pady=4,padx=4)
            tk.Label(card,text=f'{when} · {actor}',bg='#F7F9FC',fg=theme.MUTED,font=(theme.FONT,15,'bold'),anchor='w').pack(fill='x')
            for text in changes[:40]:tk.Label(card,text=text,bg='#F7F9FC',fg=theme.INK,font=(theme.FONT,16),anchor='w',justify='left',wraplength=960).pack(fill='x')
            if len(changes)>40:tk.Label(card,text=f'… et {len(changes)-40} autre(s) valeur(s)',bg='#F7F9FC',fg=theme.MUTED,font=(theme.FONT,15)).pack(anchor='w')
    def exports(self):
        if not self.reset():return
        a=self.app;a.label(a.body,'Excel local et NAS',True);bar=a.toolbar();a.button(bar,'‹ Fabrication',self.home,'secondary').pack(side='left')
        a.label(a.body,'Fermez le classeur sur les autres postes avant synchronisation. Les anciennes fiches non gérées par la borne sont conservées.')
        models=sorted({j['order']['model'] for j in self.store.all()})
        frame=a.listing()
        for model in models:
            card=a.card(frame);a.label(card,model)
            a.button(card,'Exporter sur le Pi',lambda m=model:self.export_one(m),'secondary').pack(side='left',padx=(0,8))
            a.button(card,'Synchroniser NAS',lambda m=model:self.sync(m)).pack(side='left',padx=3)
        a.label(a.body,'Dossier local : '+str(data_dir()/'excel'))
    def export_one(self,model):
        try:messagebox.showinfo('Excel',str(export_local(self.store,model)),parent=self.app.root)
        except Exception as e:messagebox.showerror('Excel',str(e),parent=self.app.root)
    def sync(self,model,resolutions=None):
        try:
            path=config_path().with_name('fabrication.json')
            conf=json.loads(path.read_text()) if path.exists() else {}
            if not conf.get('nas_directory'):raise ValueError('Configurez le dossier NAS avec configurer_fabrication.py lorsque son chemin sera connu.')
            out=sync_nas(self.store,model,conf['nas_directory'],resolutions)
            messagebox.showinfo('NAS','Synchronisé : '+str(out)+'\nLes corrections des batteries terminées peuvent être publiées depuis leur fiche.',parent=self.app.root)
        except MergeConflict as e:self.conflicts(model,e)
        except Exception as e:messagebox.showerror('NAS',str(e),parent=self.app.root)
    def conflicts(self,model,error):
        a=self.app
        if not self.reset():return
        a.label(a.body,'Conflits Excel — choisissez chaque valeur',True)
        decisions={'fingerprint':error.fingerprint};frame=a.listing()
        for c in error.conflicts:
            card=a.card(frame);j=self.store.get(c['job']);a.label(card,j['fields'].get('battery_serial','')+' · '+c['field'])
            var=tk.StringVar(value='')
            for key,title in [('pi','Pi'),('nas','NAS')]:
                tk.Radiobutton(card,text=title+' : '+str(c[key]),variable=var,value=key,bg='white',command=lambda c=c,v=var:decisions.update({c['job']+'|'+c['field']:v.get()})).pack(anchor='w')
        a.button(a.body,'Appliquer les choix',lambda:self.sync(model,decisions)).pack(side='bottom')
