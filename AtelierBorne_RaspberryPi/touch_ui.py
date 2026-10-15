"""Touch controls for the 13.3-inch workshop terminal."""
import tkinter as tk
from tkinter import ttk
from touch_keyboard import grab_when_visible

BLUE='#2E6DB4'

def scroll_area(parent):
    outer=tk.Frame(parent,bg=parent.cget('bg'));outer.pack(fill='both',expand=True)
    canvas=tk.Canvas(outer,bg=parent.cget('bg'),highlightthickness=0,yscrollincrement=20)
    bar=tk.Scrollbar(outer,orient='vertical',command=canvas.yview,width=40)
    bar.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
    content=tk.Frame(canvas,bg=parent.cget('bg'));item=canvas.create_window(0,0,window=content,anchor='nw')
    canvas.configure(yscrollcommand=bar.set)
    content.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.bind('<Configure>',lambda e:canvas.itemconfigure(item,width=e.width))
    content._touch_canvas=canvas
    return content

class TouchGestures:
    def __init__(self,root):
        self.root=root;self.start=None;self.tag='WorkshopTouch'
        root.bind_all('<Map>',self.install,add='+')
        root.bind_class(self.tag,'<ButtonPress-1>',self.press)
        root.bind_class(self.tag,'<B1-Motion>',self.move)
        root.bind_class(self.tag,'<ButtonRelease-1>',self.release)
        root.bind_class(self.tag,'<MouseWheel>',self.wheel)
        root.bind_class(self.tag,'<Button-4>',lambda e:self.wheel(e,-1))
        root.bind_class(self.tag,'<Button-5>',lambda e:self.wheel(e,1))
    def install(self,e):
        w=e.widget
        if isinstance(w,tk.Misc) and self.tag not in w.bindtags():w.bindtags((self.tag,)+w.bindtags())
    def canvas(self,w):
        while w is not None:
            if hasattr(w,'_touch_canvas'):return w._touch_canvas
            w=getattr(w,'master',None)
    def press(self,e):
        c=self.canvas(e.widget);self.start=(c,e.y_root,e.y_root,False,e.widget) if c else None
    def move(self,e):
        if not self.start:return
        c,first,last,drag,w=self.start
        if abs(e.y_root-first)>12:drag=True
        if drag:
            delta=last-e.y_root;c.yview_scroll(int(delta/20),'units')
            if abs(delta)>=20:last=e.y_root
            self.start=(c,first,last,drag,w)
            return 'break'
    def release(self,e):
        s=self.start;self.start=None
        if s and s[3]:
            try:
                if isinstance(s[4],tk.Button):s[4].configure(relief='flat')
            except tk.TclError:pass
            return 'break'
    def wheel(self,e,direction=None):
        c=self.canvas(e.widget)
        if c:c.yview_scroll(direction or (-3 if e.delta>0 else 3),'units');return 'break'

def popup(root,title):
    w=tk.Toplevel(root);w.title(title);w.transient(root);w.configure(bg='white')
    width=min(1100,root.winfo_width()-40);height=max(400,root.winfo_height()-60)
    w.geometry(f'{width}x{height}+{root.winfo_rootx()+(root.winfo_width()-width)//2}+{root.winfo_rooty()+30}')
    w._keyboard_anchor=tk.Frame(w,bg='white');w._keyboard_anchor.pack(fill='both',expand=True)
    previous=root.grab_current()
    def close():
        keyboard=getattr(root,'_keyboard',None)
        if keyboard and keyboard.target and keyboard.target.winfo_toplevel()==w:keyboard.close()
        w.destroy()
        try:
            if previous and previous.winfo_exists():previous.grab_set()
        except tk.TclError:pass
    w._close=close;w.protocol('WM_DELETE_WINDOW',close);w.bind('<Escape>',lambda e:close())
    grab_when_visible(w)
    return w

class TouchCombo(ttk.Combobox):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.bind('<Button-1>',self.choose)
        self.bind('<space>',self.choose)
    def choose(self,event=None):
        if 'disabled' in self.state():return 'break'
        root=self._root();keyboard=getattr(root,'_keyboard',None)
        if keyboard:keyboard.close()
        w=popup(root,'Sélectionner');area=w._keyboard_anchor
        tk.Label(area,text='Sélectionner',bg='white',font=('DejaVu Sans',24,'bold')).pack(pady=10)
        tk.Button(area,text='Annuler',command=w._close,pady=14,relief='flat',bd=0,bg='white',fg=BLUE,highlightthickness=2,highlightbackground=BLUE).pack(side='bottom',fill='x',padx=10,pady=10)
        search=tk.StringVar();entry=tk.Entry(area,textvariable=search);entry.pack(fill='x',padx=16,pady=8)
        content=scroll_area(area);values=list(self.cget('values'))
        def pick(value):
            self.set(value);self.event_generate('<<ComboboxSelected>>');w._close()
        def render(*_):
            for child in content.winfo_children():child.destroy()
            for value in values:
                if search.get().casefold() in str(value).casefold():
                    tk.Button(content,text=value,anchor='w',wraplength=950,command=lambda v=value:pick(v),pady=14,padx=16,bg='#F3F6FA',relief='flat',bd=0,activebackground='#E8F1FA').pack(fill='x',padx=10,pady=4)
        search.trace_add('write',render);render()
        return 'break'

class TouchMessages:
    def askyesno(self,title,message,parent=None):return self.show(title,message,parent,True)
    def showinfo(self,title,message,parent=None):return self.show(title,message,parent,False)
    showwarning=showinfo
    showerror=showinfo
    def show(self,title,message,parent,question):
        root=parent._root();keyboard=getattr(root,'_keyboard',None)
        if keyboard:keyboard.close()
        w=popup(root,title);area=w._keyboard_anchor;result=[False]
        tk.Label(area,text=title,bg='white',font=('DejaVu Sans',24,'bold')).pack(pady=20)
        actions=tk.Frame(area,bg='white');actions.pack(side='bottom',fill='x',padx=20,pady=20)
        def finish(value):result[0]=value;w._close()
        if question:tk.Button(actions,text='Annuler',command=lambda:finish(False),pady=18,relief='flat',bd=0,bg='white',fg=BLUE,highlightthickness=2,highlightbackground=BLUE,font=('DejaVu Sans',19)).pack(side='left',fill='x',expand=True,padx=8)
        tk.Button(actions,text='Confirmer' if question else 'Fermer',command=lambda:finish(True),pady=18,relief='flat',bd=0,bg=BLUE,fg='white',activebackground='#21528A',activeforeground='white',font=('DejaVu Sans',19,'bold')).pack(side='left',fill='x',expand=True,padx=8)
        content=scroll_area(area)
        tk.Label(content,text=message,bg='white',wraplength=950,justify='left').pack(fill='x',padx=24,pady=15)
        root.wait_window(w);return result[0]

messagebox=TouchMessages()
