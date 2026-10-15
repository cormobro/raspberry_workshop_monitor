"""Clavier tactile natif, sans dépendance externe."""
import tkinter as tk
from tkinter import ttk

class VisibleGrab:
    """Acquire modality after mapping; cancel retries when the window is destroyed."""
    def __init__(self, window, focus=None):
        self.window=window;self.focus=focus;self.pending=None;self.cancelled=False
        window.bind('<Destroy>',self.on_destroy,add='+')
        self.pending=window.after_idle(self.attempt)
    def on_destroy(self,event):
        if event.widget is self.window:self.cancel()
    def cancel(self):
        self.cancelled=True
        if self.pending is not None:
            try:self.window.after_cancel(self.pending)
            except tk.TclError:pass
            self.pending=None
    def attempt(self):
        self.pending=None
        if self.cancelled:return
        try:
            if not self.window.winfo_exists():return
            if self.window.winfo_viewable():
                self.window.grab_set()
                if self.focus is not None and self.focus.winfo_exists():self.focus.focus_set()
                return
        except tk.TclError:
            # Mapping/unmapping may occur between the visibility check and grab.
            pass
        if not self.cancelled:
            try:self.pending=self.window.after(40,self.attempt)
            except tk.TclError:self.cancel()

def grab_when_visible(window,focus=None):
    return VisibleGrab(window,focus)

class TouchKeyboard:
    def __init__(self, root):
        self.root=root;self.window=None;self.target=None;self.previous_grab=None
        self.pending_open=None;self.stopped=False;self.modal=None
        root.bind_all('<FocusIn>',self.request,add='+')
        root.bind_all('<ButtonRelease-1>',self.request,add='+')
        root.bind('<Destroy>',self.on_root_destroy,add='+')
    def on_root_destroy(self,event):
        if event.widget is self.root:self.shutdown()
    def shutdown(self):
        self.stopped=True
        self.close(restore=False)
    def cancel_open(self):
        if self.pending_open is not None:
            try:self.root.after_cancel(self.pending_open)
            except tk.TclError:pass
            self.pending_open=None
    def request(self,event):
        if self.stopped:return
        widget=event.widget
        if not isinstance(widget,(tk.Entry,ttk.Entry)) or getattr(widget,'_virtual_keyboard',False):return
        try:
            if str(widget.cget('state')) not in ('normal',''):return
        except tk.TclError:return
        self.cancel_open()
        def deferred_open():
            self.pending_open=None
            if not self.stopped:self.open(widget)
        self.pending_open=self.root.after_idle(deferred_open)
    def open(self,target):
        if self.stopped:return
        try:
            if not target.winfo_exists() or not target.winfo_viewable() or str(target.cget('state')) not in ('normal',''):return
        except tk.TclError:return
        if self.window is not None:
            if self.target==target:return
            self.close()
        self.target=target;self.upper=False;self.symbols=False;self.numeric=getattr(target,"_numeric",False)
        host=target.winfo_toplevel()
        anchor=getattr(host,'_keyboard_anchor',None)
        if anchor is None:return
        w=tk.Frame(host,bg='#dbe2ef',padx=10,pady=8);self.window=w
        height=min(420,max(260,int(host.winfo_height()*0.40)))
        w.configure(height=height);w.pack_propagate(False)
        w.pack(side='bottom',fill='x',before=anchor)
        self.value=tk.StringVar(value=target.get())
        self.preview=tk.Entry(w,textvariable=self.value,show=target.cget('show'),font=('DejaVu Sans',21))
        self.preview._virtual_keyboard=True;self.preview.pack(fill='x',pady=(0,6))
        self.preview.icursor('end');self.preview.focus_set()
        self.keys=tk.Frame(w,bg='#dbe2ef');self.keys.pack(fill='both',expand=True)
        controls=tk.Frame(w,bg='#dbe2ef');controls.pack(fill='x',pady=(6,0))
        for label,action in [('Maj',self.shift),('ABC / 123' if self.numeric else 'Symboles',self.toggle),('Espace',lambda:self.insert(' ')),('Effacer',self.backspace),('Suivant ›',self.next_field),('Terminé',self.close)]:
            tk.Button(controls,text=label,command=action,takefocus=0,font=('DejaVu Sans',18),pady=8).pack(side='left',expand=True,fill='x',padx=2)
        self.value.trace_add('write',self.sync)
        self.preview.bind('<Escape>',lambda e:self.close());self.preview.bind('<Return>',self.enter);self.preview.bind('<KP_Enter>',self.enter)
        self.render()
        # A modal grab captures taps on the action button underneath the
        # keyboard (notably "Se connecter"). The keyboard is visibly above
        # the app, and App.button closes it before executing the action.
        self.modal=None
        self.root.after_idle(self.reveal)
    def reveal(self):
        target=self.target
        if target is None:return
        try:
            self.root.update_idletasks()
            parent=target.master
            while parent is not None:
                canvas=getattr(parent,'_touch_canvas',None)
                if canvas:
                    top=target.winfo_rooty()-canvas.winfo_rooty()
                    if top<0 or top+target.winfo_height()>canvas.winfo_height():
                        region=canvas.bbox('all');total=max(1,region[3]-region[1])
                        canvas.yview_moveto(max(0,(canvas.canvasy(0)+top-30)/total))
                    break
                parent=getattr(parent,'master',None)
        except tk.TclError:pass
    def enter(self,event=None):
        """Entrée dans l'aperçu : un code de scan rapide est transmis à la borne, sinon fermeture."""
        hook=getattr(self.root,'_scan_hook',None);text=self.value.get() if self.window else ''
        target=self.target
        if hook and text and hook(text,dry_run=True):
            try:
                if target is not None and target.winfo_exists():target.delete(0,'end')
            except tk.TclError:pass
            self.close();self.root.focus_set();hook(text);return 'break'
        self.close();return 'break'
    def next_field(self):
        """Passe au champ suivant du même type : d'une mesure à la mesure suivante (les n° de série facultatifs sont sautés)."""
        target=self.target
        if target is None:return
        numeric=getattr(target,'_numeric',False)
        try:
            w=target.tk_focusNext()
            for _ in range(400):
                if w is None or w is target:break
                if isinstance(w,(tk.Entry,ttk.Entry)) and str(w.cget('state')) in ('normal','') and not getattr(w,'_keyboard_skip',False) and w is not self.preview and (not numeric or getattr(w,'_numeric',False)):
                    self.close();w.focus_set();self.open(w);return
                w=w.tk_focusNext()
        except tk.TclError:pass
        self.close()
    def sync(self,*args):
        try:
            if self.target and self.target.winfo_exists():
                self.target.delete(0,'end');self.target.insert(0,self.value.get())
        except tk.TclError:self.close()
    def insert(self,text):
        try:self.preview.delete('sel.first','sel.last')
        except tk.TclError:pass
        self.preview.insert('insert',text);self.preview.focus_set()
    def backspace(self):
        try:self.preview.delete('sel.first','sel.last')
        except tk.TclError:
            pos=self.preview.index('insert')
            if pos:self.preview.delete(pos-1,pos)
    def shift(self):self.upper=not self.upper;self.render()
    def toggle(self):
        if getattr(self.target,"_numeric",False):self.numeric=not self.numeric
        else:self.symbols=not self.symbols
        self.render()
    def render(self):
        for child in self.keys.winfo_children():child.destroy()
        rows=['1234567890','azertyuiop','qsdfghjklm','wxcvbnéèàç'] if not self.symbols else ['!@#$%&*()?',"-_=+[]{}<>" ,"/\\:;.,'\"`~",'€£^|éèêàùç']
        if self.numeric:rows=['789','456','123','0.,']
        for i in range(10):self.keys.columnconfigure(i,weight=0,minsize=0)
        for r,letters in enumerate(rows):
            self.keys.rowconfigure(r,weight=1)
            for c,char in enumerate(letters):
                self.keys.columnconfigure(c,weight=1,uniform='keys')
                value=char.upper() if self.upper else char
                tk.Button(self.keys,text=value,command=lambda v=value:self.insert(v),takefocus=0,font=('DejaVu Sans',22),relief='flat',bg='white').grid(row=r,column=c,padx=2,pady=2,sticky='nsew')
    def close(self,restore=True):
        self.cancel_open()
        if self.modal:self.modal.cancel();self.modal=None
        w=self.window;self.window=None;self.target=None
        if w:
            try:w.destroy()
            except tk.TclError:pass
        try:
            if restore and not self.stopped:
                if self.previous_grab and self.previous_grab.winfo_exists() and self.previous_grab.winfo_viewable():
                    self.previous_grab.grab_set();self.previous_grab.focus_set()
                elif self.root.winfo_exists():self.root.focus_set()
        except tk.TclError:pass
        self.previous_grab=None
