#!/usr/bin/env python3
"""AtelierBorne — prototype Linux natif, démonstration ou lecture Dolibarr."""
import argparse
import html
import queue
import threading
from dolibarr_client import load_client, load_personal_client, stock_quantity, ApiError
from manufacturing_ui import ManufacturingUI
from stock_ui import StockUI
from quick_scan import QuickScan
from touch_keyboard import TouchKeyboard, grab_when_visible
from touch_ui import TouchCombo, TouchGestures, scroll_area, popup
import datetime as dt
import os
from pathlib import Path
import sqlite3
import tkinter as tk
from tkinter import ttk

import json
import time
import theme
BLUE = theme.PRIMARY
RED = theme.DANGER
BG = theme.BG
CARD = theme.CARD

IDLE_MINUTES = 5  # déconnexion automatique par défaut

def borne_settings():
    """Réglages facultatifs de la borne : ~/.config/atelierborne/borne.json, ex. {"inactivite_minutes": 5}."""
    path=Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'atelierborne'/'borne.json'
    try:
        data=json.loads(path.read_text(encoding='utf-8'))
        minutes=float(data.get('inactivite_minutes',IDLE_MINUTES))
        return {'inactivite_minutes':minutes if minutes>=0 else IDLE_MINUTES}
    except (OSError,ValueError,TypeError,AttributeError):return {'inactivite_minutes':IDLE_MINUTES}
try:
    from comptes_locaux import COMPTES
except ModuleNotFoundError as exc:
    if exc.name != 'comptes_locaux': raise
    from comptes_exemple import COMPTES
PEOPLE = tuple(COMPTES)

def float_or_zero(value):
    try:return float(value or 0)
    except (ValueError,TypeError):return 0.0

def progress_text(progress):
    try:
        value=float(progress)
        return f'{value:g} %' if 0<=value<=100 else 'non renseignée'
    except (ValueError,TypeError):return 'non renseignée'

class Session:
    def __init__(self): self.user = None
    def login(self, name, password):
        self.user = None
        if name not in COMPTES or COMPTES[name] != password:
            return False
        self.user = name
        return True
    def logout(self): self.user = None


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY,title TEXT,project TEXT,owner TEXT,progress INTEGER);
        CREATE TABLE IF NOT EXISTS products(id TEXT PRIMARY KEY,name TEXT,serial INTEGER);
        CREATE TABLE IF NOT EXISTS stock(product TEXT,warehouse TEXT,qty INTEGER CHECK(qty>=0),PRIMARY KEY(product,warehouse));
        CREATE TABLE IF NOT EXISTS serials(code TEXT PRIMARY KEY,product TEXT,warehouse TEXT,active INTEGER);
        CREATE TABLE IF NOT EXISTS leaves(id INTEGER PRIMARY KEY,person TEXT,start TEXT,end TEXT,status TEXT);
        CREATE TABLE IF NOT EXISTS journal(id INTEGER PRIMARY KEY,at TEXT,person TEXT,action TEXT);
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
        ''')
        if not self.db.execute("SELECT 1 FROM meta WHERE key='seed'").fetchone():
            with self.db:
                self.db.executemany('INSERT INTO tasks VALUES(?,?,?,?,?)', [(1,'Préparer les kits du lot suivant','Assemblage',None,0),(2,'Compléter les fiches de contrôle','Qualité',None,0),(3,'Vérifier la réception des boîtiers','Stock','Hery',40)])
                self.db.executemany('INSERT INTO products VALUES(?,?,?)', [('CELL-314','Cellules LFP 314 Ah',0),('BMS-16S','BMS 16S',1),('BAT-LV','Batterie LV assemblée',1),('BOX-LV','Boîtiers LV',0)])
                for product, a, m in [('CELL-314',64,128),('BMS-16S',2,0),('BAT-LV',1,0),('BOX-LV',12,0)]:
                    self.db.executemany('INSERT INTO stock VALUES(?,?,?)',[(product,'Atelier',a),(product,'Magasin',m)])
                self.db.executemany('INSERT INTO serials VALUES(?,?,?,1)', [('BMS-00041','BMS-16S','Atelier'),('BMS-00042','BMS-16S','Atelier'),('BAT-00108','BAT-LV','Atelier')])
                today = dt.date.today()
                for person, offset in [('Miora',7),('Lova',15)]:
                    self.db.execute('INSERT INTO leaves(person,start,end,status) VALUES(?,?,?,?)',(person,str(today+dt.timedelta(days=offset)),str(today+dt.timedelta(days=offset+2)),'Validée (démo)'))
                self.db.execute("INSERT INTO meta VALUES('seed','1')")
    def rows(self, sql, args=()):
        return self.db.execute(sql,args).fetchall()
    def log(self, person, action):
        self.db.execute('INSERT INTO journal(at,person,action) VALUES(?,?,?)',(dt.datetime.now().isoformat(timespec='seconds'),person,action))
    def task(self, ident, action, person):
        if person not in PEOPLE or action not in ('Prendre','Démarrer','Terminer'): raise ValueError('Action ou opérateur inconnu.')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            row = self.rows('SELECT * FROM tasks WHERE id=?',(ident,))[0]
            if action == 'Prendre':
                if row['owner']: raise ValueError('Cette tâche est déjà prise.')
                self.db.execute('UPDATE tasks SET owner=? WHERE id=?',(person,ident))
            else:
                if row['owner'] != person: raise ValueError('Seule la personne qui a pris la tâche peut la modifier.')
                if row['progress'] == 100: raise ValueError('Cette tâche est déjà terminée.')
                progress = 1 if action == 'Démarrer' else 100
                self.db.execute('UPDATE tasks SET progress=? WHERE id=?',(progress,ident))
            self.log(person,f'Tâche {ident} : {action}')
    def movement(self, product, warehouse, mode, quantity, serial, reason, person, expected):
        if not reason.strip(): raise ValueError('Indiquez un motif.')
        try: quantity = int(quantity)
        except (ValueError, TypeError): raise ValueError('La quantité doit être un nombre entier.')
        if quantity < 0 or (mode != 'Inventaire' and quantity == 0): raise ValueError('Quantité incorrecte.')
        serial = serial.strip().upper()
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            p = self.rows('SELECT * FROM products WHERE id=?',(product,))
            stocks = self.rows('SELECT qty FROM stock WHERE product=? AND warehouse=?',(product,warehouse))
            if not p or not stocks: raise ValueError('Produit ou entrepôt inconnu.')
            old = stocks[0]['qty']
            if mode not in ('Entrée','Sortie','Inventaire'): raise ValueError('Mouvement inconnu.')
            if p[0]['serial']:
                if mode == 'Inventaire': raise ValueError('Pour un produit sérialisé, utilisez une entrée ou une sortie par numéro.')
                if quantity != 1 or not serial: raise ValueError('Un numéro de série et une quantité de 1 sont obligatoires.')
                if len(serial)>100: raise ValueError('Numéro trop long (100 caractères maximum).')
                existing = self.rows('SELECT * FROM serials WHERE code=?',(serial,))
                if mode == 'Entrée':
                    if existing: raise ValueError('Ce numéro existe déjà dans le registre, même après une sortie.')
                    self.db.execute('INSERT INTO serials VALUES(?,?,?,1)',(serial,product,warehouse))
                else:
                    if not existing or not existing[0]['active'] or existing[0]['product'] != product or existing[0]['warehouse'] != warehouse:
                        raise ValueError('Ce numéro ne se trouve pas dans ce stock.')
                    self.db.execute('UPDATE serials SET active=0 WHERE code=?',(serial,))
            if mode == 'Inventaire' and old != expected: raise ValueError('Le stock a changé. Fermez puis rouvrez ce formulaire.')
            new = quantity if mode == 'Inventaire' else old + (quantity if mode == 'Entrée' else -quantity)
            if new < 0: raise ValueError('Stock insuffisant.')
            self.db.execute('UPDATE stock SET qty=? WHERE product=? AND warehouse=?',(new,product,warehouse))
            self.log(person,f'{mode} {product} / {warehouse} : {old} → {new}; série {serial or "—"}; {reason.strip()}')
    def leave(self, person, start, end):
        try: a,b = dt.date.fromisoformat(start),dt.date.fromisoformat(end)
        except ValueError: raise ValueError('Dates invalides. Format : AAAA-MM-JJ.')
        if b<a: raise ValueError('La fin doit être après le début.')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            if self.rows('SELECT 1 FROM leaves WHERE person=? AND start<=? AND end>=?',(person,end,start)):
                raise ValueError('Ces dates recouvrent une demande existante.')
            self.db.execute('INSERT INTO leaves(person,start,end,status) VALUES(?,?,?,?)',(person,start,end,'En attente (démo)'))
            self.log(person,f'Demande de vacances : {start} au {end}')

class App:
    INACTIVITY_WARNING = 15  # secondes d'avertissement avant la déconnexion automatique
    def __init__(self, root, store, fullscreen=True, client=None, kiosk=False, idle_minutes=None):
        self.root, self.store = root, store
        self.client = client
        self.default_client = client
        self.personal = False
        self.api_identity = None
        self.kiosk = kiosk
        self.keyboard = TouchKeyboard(root)
        root._keyboard=self.keyboard
        self.gestures=TouchGestures(root)
        self.view_generation = 0
        self.session = Session()
        self.flash = ""
        self.login_message = ""
        self.tab = 1
        self.filter = 'À prendre'
        self.warehouse = 'Atelier'
        self.stopped = False
        self.idle_limit = (borne_settings().get('inactivite_minutes',IDLE_MINUTES) if idle_minutes is None else idle_minutes)*60
        self.last_activity = time.monotonic()
        self.connection = None  # (joignable, heure) de la dernière réponse Dolibarr
        root.title('AtelierBorne — Bcell')
        root.geometry('1920x1080')
        root.configure(bg=BG)
        root.tk.call('tk','scaling',1.333333)
        root.option_add('*Font', (theme.FONT,19))
        root.option_add('*Entry.borderWidth', 10)
        root.option_add('*Entry.relief', 'flat')
        root.option_add('*Entry.highlightThickness', 1)
        root.option_add('*Entry.highlightBackground', theme.BORDER)
        root.option_add('*Entry.highlightColor', theme.BRAND)
        root.option_add('*Entry.background', '#FBFCFE')
        root.option_add('*Label.foreground', theme.INK)
        if kiosk:root.option_add('*cursor','none');root.configure(cursor='none')
        icon=theme.image('icone.png',root)
        if icon is not None:
            try:root.iconphoto(True,icon)
            except tk.TclError:pass
        style=ttk.Style(root)
        style.configure('TCombobox',font=(theme.FONT,19),padding=12,arrowsize=30)
        root.attributes('-fullscreen', fullscreen)
        if not kiosk:
            # Mode borne : pas de sortie du plein écran au doigt ou au clavier.
            root.bind('<Escape>', lambda e: root.attributes('-fullscreen',False))
            root.bind('<F11>', lambda e: root.attributes('-fullscreen',not root.attributes('-fullscreen')))
        root.bind('<Control-Shift-Q>',lambda e:self.shutdown())
        root.bind('<Control-Shift-q>',lambda e:self.shutdown())
        root.protocol('WM_DELETE_WINDOW',self.shutdown)
        root.bind_all('<ButtonPress>',self.activity,add='+')
        root.bind_all('<KeyPress>',self.key_activity,add='+')
        header = tk.Frame(root,bg='white',padx=10,pady=8); header.pack(fill='x')
        self.header=header
        logo=theme.image('logo_header.png',root)
        if logo is not None:tk.Label(header,image=logo,bg='white').pack(side='left',padx=(4,18))
        else:tk.Label(header,text='BCELL',font=(theme.FONT,23,'bold'),bg='white').pack(side='left',padx=(2,8))
        self.logout_button = theme.button(header,'Déconnexion',self.logout,'danger_solid',size=17,padx=18,pady=14)
        nav = tk.Frame(header,bg='white'); self.nav = nav
        self.tabs=[]
        for i,title in enumerate(('Vacances','Projets / Tâches','Stocks','Tests / Réglages','Fabrication')):
            b=tk.Button(nav,text=title,command=lambda i=i:self.show(i),pady=15,padx=4,font=(theme.FONT,17),relief='flat',bd=0,bg='white',fg=theme.INK,activebackground=theme.PRIMARY_SOFT,highlightthickness=0)
            b.grid(row=0,column=i,sticky='nsew',padx=3)
            nav.columnconfigure(i,weight=1,uniform='tabs')
            self.tabs.append(b)
        tk.Frame(root,bg=theme.BORDER,height=1).pack(fill='x')
        bar=tk.Frame(root,bg=BG);bar.pack(fill='x',padx=18,pady=(6,0));self.status_bar=bar
        self.identity = tk.Label(bar,text='',bg=BG,fg=theme.MUTED,font=(theme.FONT,15),anchor='w')
        self.identity.pack(side='left')
        self.connection_label = tk.Label(bar,text='',bg=BG,fg=theme.MUTED,font=(theme.FONT,15))
        self.connection_label.pack(side='right')
        self.idle_banner = tk.Label(root,text='',bg=theme.WARN_SOFT,fg='#6B4300',font=(theme.FONT,18,'bold'),pady=10)
        self.body=tk.Frame(root,bg=BG,padx=18,pady=8); self.body.pack(fill='both',expand=True)
        root._keyboard_anchor=self.body
        if not fullscreen and not kiosk:
            tk.Label(root,text='Mode fenêtre : Échap = fenêtre · F11 = plein écran · Ctrl+Maj+Q = quitter',bg=BG,fg=theme.MUTED,font=(theme.FONT,13)).pack(pady=4)
        self.manufacturing=ManufacturingUI(self)
        self.stock_ui=StockUI(self)
        self.quick=QuickScan(self)
        self.login_screen()
        root.after(1000,self.idle_tick)
        root.after(2000,self.connection_tick)
    # ---- inactivité ----------------------------------------------------------
    def activity(self,event=None):
        self.last_activity=time.monotonic()
        if self.idle_banner.winfo_ismapped():self.idle_banner.pack_forget()
    def key_activity(self,event):
        self.activity(event)
        if hasattr(self,'quick'):self.quick.key(event)
    def busy(self):
        quick=getattr(self,'quick',None)
        return bool(getattr(self.manufacturing,'busy',False) or getattr(self.stock_ui,'inflight',None) or (quick and (quick.current or quick.waiting_batch)))
    def idle_tick(self):
        if self.stopped:return
        try:
            if self.session.user and self.idle_limit>0:
                idle=time.monotonic()-self.last_activity
                if self.busy():self.last_activity=time.monotonic()  # jamais pendant un envoi à Dolibarr
                elif idle>=self.idle_limit:
                    minutes=self.idle_limit/60
                    self.logout(f'Session fermée automatiquement après {minutes:g} min sans activité. Brouillons enregistrés.')
                elif idle>=self.idle_limit-self.INACTIVITY_WARNING:
                    self.idle_banner.config(text=f'Déconnexion automatique dans {int(self.idle_limit-idle)+1} s — touchez l’écran pour rester connecté')
                    if not self.idle_banner.winfo_ismapped():self.idle_banner.pack(fill='x',before=self.body)
        finally:
            if not self.stopped:self.root.after(1000,self.idle_tick)
    # ---- état de la connexion Dolibarr ----------------------------------------
    def set_connection(self,reachable):
        self.connection=(reachable,dt.datetime.now().strftime('%H:%M'))
        self.render_connection()
    def render_connection(self):
        if not self.client:
            self.connection_label.config(text='● Mode démonstration',fg=theme.MUTED);return
        if self.connection is None:
            self.connection_label.config(text='● Dolibarr : vérification…',fg=theme.MUTED);return
        ok,at=self.connection
        self.connection_label.config(text=f'● Dolibarr joignable · {at}' if ok else f'● Dolibarr injoignable · {at}',fg=theme.SUCCESS if ok else theme.DANGER)
    def check_connection(self):
        """Interroge Dolibarr en arrière-plan ; une réponse HTTP, même refusée, prouve que le serveur est joignable."""
        client=self.client
        if not client or not self.session.user or self.stopped:return
        result=queue.Queue()
        def worker():
            try:client.identity();result.put(True)
            except ApiError as e:result.put(e.code is not None)
            except Exception:result.put(False)
        def poll():
            if self.stopped or self.client is not client:return
            try:self.set_connection(result.get_nowait())
            except queue.Empty:self.root.after(200,poll)
        threading.Thread(target=worker,daemon=True).start();self.root.after(200,poll)
    def connection_tick(self):
        if self.stopped:return
        self.check_connection()
        self.root.after(60000,self.connection_tick)
    def shutdown(self):
        if hasattr(self,"manufacturing"):self.manufacturing.flush()
        if hasattr(self,'quick'):self.quick.flush()  # non confirmé à l’arrêt : reste « à réessayer » dans Stocks
        self.stopped=True
        self.view_generation+=1
        self.keyboard.shutdown()
        self.root.destroy()
    # ---- connexion -------------------------------------------------------------
    def login_screen(self):
        self.keyboard.close()
        self.nav.pack_forget()
        self.logout_button.pack_forget()
        self.status_bar.pack_forget()
        self.idle_banner.pack_forget()
        self.identity.config(text="")
        for w in self.body.winfo_children(): w.destroy()
        page=tk.Frame(self.body,bg=BG);page.pack(fill='both',expand=True,pady=10)
        left=tk.Frame(page,bg=BG);left.pack(side='left',fill='both',expand=True,padx=(10,30))
        right=tk.Frame(page,bg=CARD,padx=30,pady=24,highlightthickness=1,highlightbackground=theme.BORDER);right.pack(side='right',anchor='n',padx=(0,10),pady=(20,0))
        logo=theme.image('logo_login.png',self.root)
        if logo is not None:tk.Label(left,image=logo,bg=BG).pack(anchor='w',pady=(10,24))
        self.label(left,"Connexion à l’atelier",True)
        self.label(left,"Touchez votre nom, puis saisissez votre code.",muted=True)
        if self.login_message:
            tk.Label(left,text=self.login_message,bg=theme.WARN_SOFT,fg='#6B4300',font=(theme.FONT,17),anchor='w',justify='left',wraplength=1000,padx=14,pady=10).pack(fill='x',pady=8)
            self.login_message=''
        tiles=tk.Frame(left,bg=BG);tiles.pack(anchor='w',pady=10)
        chosen={'name':None,'button':None}
        who=tk.Label(right,text='Choisissez votre nom',bg=CARD,fg=theme.MUTED,font=(theme.FONT,22,'bold'));who.pack(anchor='w')
        pin=tk.Entry(right,show="•",font=(theme.FONT,30),width=12,justify='center');pin._virtual_keyboard=True
        pin.pack(fill='x',pady=14)
        status=tk.Label(right,text='',bg=CARD,fg=theme.DANGER,font=(theme.FONT,16),wraplength=420,justify='left');status.pack(anchor='w')
        def pick(name,button):
            if chosen['button'] is not None and chosen['button'].winfo_exists():
                chosen['button'].config(bg=CARD,fg=theme.INK,highlightbackground=theme.BORDER)
            button.config(bg=theme.PRIMARY,fg='white',highlightbackground=theme.PRIMARY)
            chosen.update(name=name,button=button);who.config(text=name,fg=theme.INK)
            pin.delete(0,'end');status.config(text='');pin.focus_set()
        for i,name in enumerate(PEOPLE):
            b=tk.Button(tiles,text=name,font=(theme.FONT,22,'bold'),width=11,height=2,relief='flat',bd=0,bg=CARD,fg=theme.INK,activebackground=theme.PRIMARY_SOFT,highlightthickness=2,highlightbackground=theme.BORDER,cursor='hand2')
            b.config(command=lambda n=name,b=b:pick(n,b))
            b.grid(row=i//4,column=i%4,padx=8,pady=8)
        def connect():
            if not chosen['name']:
                status.config(text='Touchez d’abord votre nom.');return
            if not self.session.login(chosen['name'],pin.get()):
                pin.delete(0,"end"); status.config(text="Code incorrect."); return
            try:
                personal=load_personal_client(self.session.user) if self.default_client else None
            except ApiError as e:
                self.session.logout();status.config(text=str(e));return
            self.personal=personal is not None
            self.client=personal or self.default_client
            self.api_identity=None;self.connection=None
            self.identity.config(text=self.session.user+(' · compte Dolibarr personnel' if self.personal else ' · compte partagé, consultation' if self.client else ' · démonstration locale'))
            self.keyboard.close()
            self.logout_button.pack(side='right',padx=(10,0))
            self.nav.pack(side='left',fill='x',expand=True)
            self.status_bar.pack(fill='x',padx=18,pady=(6,0),before=self.body)
            self.render_connection();self.activity()
            self.show(1)
            self.root.after(10,self.check_connection)
        pad=tk.Frame(right,bg=CARD);pad.pack(pady=6)
        keys=['1','2','3','4','5','6','7','8','9','Effacer','0','⌫']
        def press(k):
            if k=='Effacer':pin.delete(0,'end')
            elif k=='⌫':pin.delete(len(pin.get())-1,'end') if pin.get() else None
            else:pin.insert('end',k)
        for i,k in enumerate(keys):
            tk.Button(pad,text=k,command=lambda k=k:press(k),font=(theme.FONT,26 if k not in ('Effacer',) else 17,'bold'),width=4 if k!='Effacer' else 7,height=1,pady=14,relief='flat',bd=0,bg='#EEF2F7',fg=theme.INK,activebackground=theme.PRIMARY_SOFT,highlightthickness=0).grid(row=i//3,column=i%3,padx=6,pady=6,sticky='nsew')
        self.button(right,"Se connecter",connect).pack(fill='x',pady=(14,6))
        self.button(right,"Code avec lettres : clavier complet",lambda:self.keyboard.open(pin),'secondary',size=15).pack(fill='x')
        pin.bind("<Return>",lambda e:connect())
        if len(PEOPLE)==1:tiles.winfo_children()[0].invoke()
    def logout(self,message=''):
        if hasattr(self,'quick'):self.quick.flush()
        if hasattr(self,"manufacturing"):
            self.manufacturing.flush();self.manufacturing.current=None;self.manufacturing.vars={}
        self.view_generation += 1
        self.keyboard.close()
        self.session.logout()
        self.client=self.default_client;self.personal=False;self.api_identity=None;self.connection=None
        for w in self.root.winfo_children():
            if isinstance(w,tk.Toplevel): w.destroy()
        self.filter="À prendre"; self.warehouse="Atelier"; self.flash=""
        self.login_message=message if isinstance(message,str) else ''
        self.login_screen()
    # ---- composants ------------------------------------------------------------
    def button(self,parent,text,command,kind='primary',**kw):
        def invoke():
            # A visible touch keyboard owns the modal grab. Release it before
            # any action button so dialog confirmations remain tappable.
            self.keyboard.close()
            return command()
        return theme.button(parent,text,invoke,kind,**kw)
    def label(self,parent,text,large=False,muted=False):
        wrap=1650 if parent.winfo_toplevel() is self.root else 980
        font=(theme.FONT,27,'bold') if large else (theme.FONT,19)
        w=tk.Label(parent,text=text,bg=parent.cget('bg'),fg=theme.MUTED if muted else theme.INK,anchor='w',justify='left',wraplength=wrap,font=font)
        w.pack(fill='x',pady=(8,4) if large else 4); return w
    def toolbar(self,parent=None):
        f=tk.Frame(parent or self.body,bg=(parent or self.body).cget('bg'));f.pack(fill='x',pady=(2,8));return f
    def listing(self):
        return scroll_area(self.body)
    def card(self,parent):
        f=tk.Frame(parent,bg=CARD,padx=20,pady=14,highlightthickness=1,highlightbackground=theme.BORDER);f.pack(fill='x',pady=6,padx=(0,6));return f
    def dialog(self,title):
        self.keyboard.close()
        host=popup(self.root,title);area=host._keyboard_anchor
        self.label(area,title,True)
        self.button(area,'Fermer',host._close,'secondary').pack(side='bottom',anchor='e',pady=8,padx=8)
        content=scroll_area(area)
        # Existing callers use destroy/geometry on the dialog's content.
        original_destroy=content.destroy
        def destroy():
            content.destroy=original_destroy
            host._close()
        content.destroy=destroy
        content.geometry=lambda *args:None
        return content
    def notify(self,title,text):
        w=self.dialog(title);self.label(w,text);return w
    def authenticated(self,callback):
        if self.session.user is None:
            self.login_screen()
            return
        callback(self.session.user)
    def perform(self,call,dialog=None):
        try:call()
        except (ValueError,sqlite3.Error) as e:self.notify('Action impossible',str(e));return False
        if dialog:self.keyboard.close();dialog.destroy()
        self.show(self.tab);return True
    def show(self,index):
        if hasattr(self,"manufacturing") and self.manufacturing.current:
            if not self.manufacturing.save():return
            self.manufacturing.current=None;self.manufacturing.vars={}
        self.keyboard.close()
        if self.session.user is None:
            self.login_screen(); return
        self.view_generation += 1
        self.tab=index
        for i,b in enumerate(self.tabs):b.config(bg=theme.PRIMARY if i==index else 'white',fg='white' if i==index else theme.INK,font=(theme.FONT,17,'bold' if i==index else 'normal'))
        for w in self.body.winfo_children():w.destroy()
        if index == 4 or (index == 3 and self.client):
            self.manufacturing.home(tests=index==3);return
        if self.client:
            if index == 1:self.remote_projects()
            elif index == 2:self.stock_ui.screen()
            elif index == 0:
                self.label(self.body,'Vacances' if index == 0 else 'Stocks',True)
                self.label(self.body,'Connexion de cette rubrique en préparation. Aucune donnée fictive n’est affichée en mode Dolibarr.')
                if index == 0:self.label(self.body,'Vos soldes existants seront lus depuis Dolibarr après raccordement du service de congés et des utilisateurs.')
            else:self.technical()
        else:(self.vacances,self.tasks,self.stocks,self.technical)[index]()
    def remote_fetch(self, action, render):
        generation=self.view_generation
        user=self.session.user
        status=self.label(self.body,'Chargement depuis Dolibarr…')
        results=queue.Queue()
        def worker():
            try:results.put((True,action()))
            except ApiError as e:results.put((False,str(e)))
            except Exception:results.put((False,'Erreur inattendue lors de la lecture. Aucune donnée locale de démonstration ne sera substituée.'))
        def poll():
            if self.view_generation != generation or self.session.user != user:return
            try:ok,result=results.get_nowait()
            except queue.Empty:self.root.after(100,poll);return
            if ok:
                self.set_connection(True)
                status.config(text='Mis à jour à '+dt.datetime.now().strftime('%H:%M'),fg=theme.MUTED,font=(theme.FONT,15))
                render(result)
            else:
                status.config(text=result,fg=theme.DANGER)
                if result.startswith('Connexion impossible'):self.set_connection(False)
        threading.Thread(target=worker,daemon=True).start()
        self.root.after(100,poll)
    def remote_projects(self):
        self.label(self.body,'Projets',True)
        self.label(self.body,'Projets partagés et projets dont vous êtes membre' if self.personal else 'Projets partagés · consultation seule',muted=True)
        bar=self.toolbar()
        if self.personal:
            self.button(bar,'Tâches à prendre',self.remote_available).pack(side='left',padx=(0,8))
            self.button(bar,'Mes tâches en cours',self.remote_mine).pack(side='left',padx=(0,8))
        self.button(bar,'Actualiser',lambda:self.show(1),'secondary').pack(side='left')
        if not self.personal:self.label(self.body,'Associez votre compte Dolibarr pour voir vos projets privés et prendre une tâche.',muted=True)
        def render(rows):
            area=self.listing()
            if not rows:self.label(area,'Aucun projet renvoyé par ce compte. Vérifiez ses droits et les restrictions aux tiers/commerciaux si des projets existent.')
            for r in rows:
                f=self.card(area)
                title=html.unescape(str(r.get('title') or r.get('label') or r.get('ref') or r['id']))
                right=tk.Frame(f,bg=CARD);right.pack(side='right',padx=(12,0))
                left=tk.Frame(f,bg=CARD);left.pack(side='left',fill='x',expand=True)
                self.label(left,title,True)
                self.label(left,str(r.get('ref') or '')+' · '+('Partagé' if str(r.get('public'))=='1' else 'Personnel'),muted=True)
                if r.get('tasks_total') is not None:
                    total=int(float_or_zero(r.get('tasks_total')));done=int(float_or_zero(r.get('tasks_done')))
                    line=tk.Frame(left,bg=CARD);line.pack(anchor='w',pady=(4,0))
                    theme.progress_bar(line,done,total,width=360).pack(side='left')
                    tk.Label(line,text=f'  {done} / {total} tâche(s) terminée(s)',bg=CARD,fg=theme.MUTED,font=(theme.FONT,15)).pack(side='left')
                    free=int(float_or_zero(r.get('tasks_available')))
                    if free:theme.pill(right,f'{free} à prendre',theme.PRIMARY_SOFT,theme.PRIMARY_DARK).pack(anchor='e',pady=(0,8))
                self.button(right,'Voir les tâches',lambda r=r,title=title:self.remote_tasks(r['id'],title)).pack(anchor='e')
        client=self.client
        self.remote_fetch(client.personal_projects if self.personal else lambda:[r for r in client.projects() if str(r.get('public'))=='1'],render)
    def task_card(self,area,r,refresh,subtitle):
        f=self.card(area)
        right=tk.Frame(f,bg=CARD);right.pack(side='right',padx=(12,0))
        left=tk.Frame(f,bg=CARD);left.pack(side='left',fill='x',expand=True)
        self.label(left,html.unescape(str(r.get('label') or r.get('title') or r.get('ref') or 'Tâche')),True)
        self.label(left,subtitle,muted=True)
        line=tk.Frame(left,bg=CARD);line.pack(anchor='w',pady=(4,0))
        value=max(0.0,min(100.0,float_or_zero(r.get('progress'))))
        theme.progress_bar(line,value,100,width=300).pack(side='left')
        tk.Label(line,text='  '+progress_text(r.get('progress')),bg=CARD,fg=theme.MUTED,font=(theme.FONT,15)).pack(side='left')
        if self.personal:self.task_assignment(right,r,refresh)
        return f
    def remote_tasks(self,ident,title):
        if not self.session.user:self.login_screen();return
        self.view_generation+=1
        for w in self.body.winfo_children():w.destroy()
        self.label(self.body,title,True)
        actions=self.toolbar()
        self.button(actions,'‹ Projets',lambda:self.show(1),'secondary').pack(side='left',padx=(0,8))
        self.button(actions,'Actualiser',lambda:self.remote_tasks(ident,title),'secondary').pack(side='left')
        def render(rows):
            area=self.listing()
            if not rows:self.label(area,'Aucune tâche renvoyée pour ce projet.')
            for r in rows:self.task_card(area,r,lambda:self.remote_tasks(ident,title),str(r.get('ref') or ''))
            if not self.personal:self.label(area,'Prise de tâche disponible après association personnelle et installation du module.',muted=True)
        client=self.client
        self.remote_fetch(lambda:client.personal_tasks(ident) if self.personal else client.tasks(ident),render)
    def remote_mine(self):
        self.keyboard.close();self.view_generation+=1
        for w in self.body.winfo_children():w.destroy()
        self.label(self.body,'Mes tâches en cours',True)
        line=self.toolbar()
        self.button(line,'‹ Projets',lambda:self.show(1),'secondary').pack(side='left',padx=(0,8))
        self.button(line,'Actualiser',self.remote_mine,'secondary').pack(side='left')
        client=self.client
        def render(rows):
            area=self.listing()
            if not rows:self.label(area,'Aucune tâche en cours à votre nom.')
            for r in rows:self.task_card(area,r,self.remote_mine,html.unescape(str(r.get('project_title') or '')))
        self.remote_fetch(client.my_tasks,render)
    def remote_available(self):
        self.keyboard.close();self.view_generation+=1
        for w in self.body.winfo_children():w.destroy()
        self.label(self.body,'Tâches à prendre',True)
        line=self.toolbar()
        self.button(line,'‹ Projets',lambda:self.show(1),'secondary').pack(side='left',padx=(0,8))
        self.button(line,'Actualiser',self.remote_available,'secondary').pack(side='left')
        client=self.client
        def render(rows):
            area=self.listing()
            if not rows:self.label(area,'Aucune tâche disponible dans vos projets accessibles.')
            for r in rows:self.task_card(area,r,self.remote_available,html.unescape(str(r.get('project_title') or '')))
        self.remote_fetch(client.available_tasks,render)
    def task_assignment(self,parent,row,refresh):
        if row.get('mine'):
            done=float_or_zero(row.get('progress'))>=100
            theme.pill(parent,'Prise par vous'+(' · terminée' if done else ''),theme.PRIMARY_SOFT,theme.PRIMARY_DARK).pack(anchor='e',pady=(0,8))
            actions=tk.Frame(parent,bg=parent.cget('bg'));actions.pack(anchor='e')
            self.button(actions,'Me désassigner',lambda:self.confirm_task(row,refresh,'unassign'),'secondary').pack(side='left',padx=4)
            if not done and str(row.get('project_status',1))=='1':
                self.button(actions,'Terminer / 100 %',lambda:self.confirm_task(row,refresh,'complete')).pack(side='left',padx=4)
            return
        if int(row.get('assigned_count',0))>0:theme.pill(parent,'Déjà attribuée','#ECEFF3',theme.MUTED).pack(anchor='e');return
        try:available=float(row.get('progress') or 0)<100 and int(row.get('project_status',0))==1
        except (ValueError,TypeError):available=False
        if not available:theme.pill(parent,'Non disponible','#ECEFF3',theme.MUTED).pack(anchor='e');return
        self.button(parent,'Prendre',lambda:self.confirm_claim(row,refresh)).pack(anchor='e')
    def confirm_claim(self,row,refresh):self.confirm_task(row,refresh,'claim')
    TASK_ACTIONS={
        'claim':('Prendre cette tâche','La tâche sera affectée à votre compte Dolibarr personnel.','Confirmer la prise','Affectation en cours…'),
        'unassign':('Me désassigner','Vous serez retiré des exécutants de cette tâche. Les autres contacts et la progression sont conservés.','Confirmer la désassignation','Désassignation en cours…'),
        'complete':('Terminer la tâche','La progression de la tâche passera à 100 % dans Dolibarr. Le projet n’est pas modifié.','Confirmer : terminée à 100 %','Enregistrement en cours…'),
    }
    def confirm_task(self,row,refresh,action):
        client=self.client;actor=self.session.user
        title,explanation,confirm,progress=self.TASK_ACTIONS[action]
        call=getattr(client,action)
        w=self.dialog(title)
        self.label(w,html.unescape(str(row.get('label') or row.get('ref') or 'Tâche')))
        self.label(w,explanation)
        status=self.label(w,'')
        def send():
            if self.session.user != actor:w.destroy();return
            button.config(state='disabled');status.config(text=progress)
            result=queue.Queue()
            def worker():
                try:result.put((True,call(row['id'])))
                except ApiError as e:result.put((False,str(e)))
                except Exception:result.put((False,'Résultat incertain. Actualisez la liste avant de réessayer.'))
            def poll():
                if not w.winfo_exists():return
                try:ok,data=result.get_nowait()
                except queue.Empty:self.root.after(100,poll);return
                if ok:w.destroy();refresh()
                else:status.config(text=str(data));button.config(state='normal')
            threading.Thread(target=worker,daemon=True).start();self.root.after(100,poll)
        button=self.button(w,confirm,send);button.pack(pady=14,fill='x')
    def tasks(self):
        self.label(self.body,'Projets / Tâches',True)
        line=tk.Frame(self.body,bg=BG);line.pack(fill='x')
        for value in ('À prendre','Prises en charge','Terminées'):
            def select(v=value):self.filter=v;self.show(1)
            self.button(line,('✓ ' if self.filter==value else '')+value,select).pack(side='left',padx=3)
        area=self.listing();count=0
        for r in self.store.rows('SELECT * FROM tasks ORDER BY id'):
            category='Terminées' if r['progress']==100 else 'Prises en charge' if r['owner'] else 'À prendre'
            if category!=self.filter:continue
            count+=1;f=self.card(area);self.label(f,r['title'],True)
            self.label(f,f"{r['project']} · {r['owner'] or 'Non attribuée'} · {r['progress']} %")
            if r['progress']<100:
                action='Prendre' if not r['owner'] else 'Démarrer' if r['progress']==0 else 'Terminer'
                self.button(f,action,lambda r=r,a=action:self.authenticated(lambda p:self.perform(lambda:self.store.task(r['id'],a,p)))).pack(anchor='e')
        if not count:self.label(area,'Aucune tâche dans cette liste.')
    def vacances(self):
        self.label(self.body,'Vacances',True)
        if self.flash:
            self.label(self.body,self.flash).config(fg='#16703a')
            self.flash=''
        self.button(self.body,'Demander des vacances',lambda:self.authenticated(self.leave_form)).pack(anchor='w')
        area=self.listing()
        self.label(area,'Mes demandes · '+self.session.user,True)
        mine=self.store.rows('SELECT * FROM leaves WHERE person=? ORDER BY start DESC,id DESC',(self.session.user,))
        if not mine: self.label(area,'Aucune demande pour le moment.')
        for r in mine:
            f=self.card(area)
            self.label(f,f"Du {r['start']} au {r['end']} · {r['status']}")
        self.label(area,'Planning des absences validées',True)
        for r in self.store.rows("SELECT * FROM leaves WHERE status='Validée (démo)' ORDER BY start"):
            f=self.card(area);self.label(f,r['person'],True);self.label(f,f"Du {r['start']} au {r['end']} · {r['status']}")
    def leave_form(self,person):
        w=self.dialog(f'Vacances · {person}')
        self.label(w,'Nouvelle demande — dates au format AAAA-MM-JJ')
        entries=[]
        for name in ('Début','Fin'):
            self.label(w,name);e=tk.Entry(w);e.insert(0,str(dt.date.today()));e.pack(fill='x');entries.append(e)
        status=self.label(w,'')
        def submit():
            if self.session.user != person:
                w.destroy();self.login_screen();return
            try:self.store.leave(person,entries[0].get(),entries[1].get())
            except (ValueError,sqlite3.Error) as e:
                status.config(text=str(e),fg='#a02020');return
            self.flash='Demande enregistrée · en attente de validation (démo).'
            self.keyboard.close();w.destroy();self.show(0)
        self.button(w,'Enregistrer la demande (démo)',submit).pack(pady=12)
    def stocks(self):
        line=tk.Frame(self.body,bg=BG);line.pack(fill='x')
        self.label(line,'Stocks',True)
        warehouses=TouchCombo(line,values=('Atelier','Magasin'),state='readonly');warehouses.set(self.warehouse);warehouses.pack(anchor='w')
        def changed(e):self.warehouse=warehouses.get();self.show(2)
        warehouses.bind('<<ComboboxSelected>>',changed)
        area=self.listing()
        for r in self.store.rows('SELECT p.*,s.qty FROM products p JOIN stock s ON s.product=p.id WHERE s.warehouse=? ORDER BY p.id',(self.warehouse,)):
            f=self.card(area);self.label(f,f"{r['name']} : {r['qty']}",True)
            self.label(f,r['id']+(' · numéros de série uniques' if r['serial'] else ' · suivi en quantité'))
            buttons=tk.Frame(f,bg='white');buttons.pack(fill='x')
            self.button(buttons,'Modifier',lambda r=r:self.authenticated(lambda p:self.stock_form(r,p))).pack(side='right')
            if r['serial']:
                self.button(buttons,'Numéros de série',lambda r=r:self.serial_list(r)).pack(side='left')
    def serial_list(self,r):
        rows=self.store.rows('SELECT code FROM serials WHERE product=? AND warehouse=? AND active=1 ORDER BY code',(r['id'],self.warehouse))
        w=self.dialog('Numéros présents · '+r['id']);box=tk.Text(w,height=10,font=('DejaVu Sans',15));box.pack(fill='both',expand=True)
        box.insert('1.0','\n'.join(x['code'] for x in rows) or 'Aucun numéro présent.');box.config(state='disabled')
    def stock_form(self,r,person):
        warehouse=self.warehouse
        w=self.dialog(f"{r['id']} · {warehouse} · {person}");w.geometry('620x590')
        self.label(w,f"Stock affiché : {r['qty']} · modification locale de démonstration")
        mode=TouchCombo(w,values=('Entrée','Sortie') if r['serial'] else ('Entrée','Sortie','Inventaire'),state='readonly');mode.set('Entrée');mode.pack(fill='x',pady=8)
        self.label(w,'Quantité (Inventaire = quantité totale comptée)')
        qty=tk.Entry(w);qty.insert(0,'1');qty.pack(fill='x')
        if r['serial']:qty.config(state='readonly')
        self.label(w,'Numéro de série' if r['serial'] else 'Numéro de série : non requis')
        serial=tk.Entry(w);serial.pack(fill='x')
        if not r['serial']:serial.config(state='disabled')
        self.label(w,'Motif obligatoire');reason=tk.Entry(w);reason.pack(fill='x')
        self.button(w,'Enregistrer (démo)',lambda:self.perform(lambda:self.store.movement(r['id'],warehouse,mode.get(),qty.get(),serial.get(),reason.get(),person,r['qty']),w)).pack(pady=15)
    def technical(self):
        self.label(self.body,'Tests + Pré-configuration calibrage',True)
        self.label(self.body,'Emplacements prévus pour la future intégration des équipements.')
        area=self.listing()
        for title,description in [('Tests','Sélectionner à terme un appareil et une procédure validée.'),('Pré-configuration','Préparer à terme les paramètres autorisés pour un modèle.'),('Calibrage','À définir selon le matériel et la procédure du fabricant.')]:
            f=self.card(area);self.label(f,title,True);self.label(f,description)
            self.button(f,'État de l’intégration',lambda title=title:self.notify(title,'Non connecté.\nAucune mesure, aucun test ni réglage matériel ne sont exécutés dans ce prototype.')).pack(anchor='e')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--windowed',action='store_true');parser.add_argument('--demo',action='store_true')
    parser.add_argument('--borne',action='store_true',help='mode borne : plein écran, curseur masqué, sans sortie au clavier');args=parser.parse_args()
    try:client=None if args.demo else load_client()
    except ApiError as e:raise SystemExit(str(e))
    directory=Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))/'atelierborne'
    directory.mkdir(parents=True,exist_ok=True)
    store=Store(directory/'demo.sqlite3')
    try:root=tk.Tk()
    except tk.TclError as e:
        raise SystemExit('Impossible d’ouvrir la session graphique. Lancez ce programme depuis un terminal OUVERT DANS VNC.\n'+str(e))
    App(root,store,args.borne or not args.windowed,client,kiosk=args.borne)
    try:root.mainloop()
    finally:store.db.close()
if __name__=='__main__':main()
