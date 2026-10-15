"""Charte visuelle Bcell pour la borne : couleurs, boutons, pastilles, images."""
from pathlib import Path
import tkinter as tk

BRAND = '#5C9CD3'        # bleu du logo Bcell
PRIMARY = '#2E6DB4'      # bleu foncé lisible avec texte blanc (contraste > 4,5)
PRIMARY_DARK = '#21528A'
PRIMARY_SOFT = '#E8F1FA'
INK = '#14202E'
MUTED = '#5A6577'
BG = '#F3F6FA'
CARD = '#FFFFFF'
BORDER = '#DCE3EC'
DANGER = '#C62828'
DANGER_DARK = '#9F1F1F'
DANGER_SOFT = '#FDECEC'
SUCCESS = '#1F7A3D'
WARN = '#B85C00'
WARN_SOFT = '#FFF3D6'
FONT = 'DejaVu Sans'

STAGES = {
    'Assemblage': ('#E8F1FA', '#21528A'),
    'Calibrage': ('#FFF3D6', '#7A4E00'),
    'Mise en boîte': ('#E6F4EA', '#1F6B37'),
    'Terminée': ('#ECEFF3', '#3C4656'),
}

ASSETS = Path(__file__).resolve().parent / 'assets'
def image(name, master):
    """PhotoImage d'un fichier de assets/, gardée en cache sur la fenêtre principale (None si absent)."""
    root = master.winfo_toplevel() if hasattr(master, 'winfo_toplevel') else master
    cache = getattr(root, '_bcell_images', None)
    if cache is None:
        cache = root._bcell_images = {}
    if name not in cache:
        try:
            cache[name] = tk.PhotoImage(master=root, file=str(ASSETS / name))
        except (tk.TclError, RuntimeError):
            cache[name] = None
    return cache[name]


def button(parent, text, command, kind='primary', size=19, **kw):
    """primary : action principale · secondary : navigation · danger : suppression/sortie définitive."""
    styles = {
        'primary': dict(bg=PRIMARY, fg='white', activebackground=PRIMARY_DARK, activeforeground='white',
                        highlightthickness=0),
        'secondary': dict(bg=CARD, fg=PRIMARY, activebackground=PRIMARY_SOFT, activeforeground=PRIMARY_DARK,
                          highlightthickness=2, highlightbackground=PRIMARY, highlightcolor=PRIMARY),
        'danger': dict(bg=CARD, fg=DANGER, activebackground=DANGER_SOFT, activeforeground=DANGER_DARK,
                       highlightthickness=2, highlightbackground=DANGER, highlightcolor=DANGER),
        'danger_solid': dict(bg=DANGER, fg='white', activebackground=DANGER_DARK, activeforeground='white',
                             highlightthickness=0),
    }[kind]
    options = dict(text=text, command=command, relief='flat', bd=0, padx=22, pady=16,
                   font=(FONT, size, 'bold' if kind in ('primary', 'danger_solid') else 'normal'),
                   disabledforeground='#9aa7b8', cursor='hand2')
    options.update(styles)
    options.update(kw)
    b = tk.Button(parent, **options)
    b._kind = kind
    return b


def pill(parent, text, bg, fg, size=15):
    return tk.Label(parent, text=text, bg=bg, fg=fg, font=(FONT, size, 'bold'), padx=14, pady=5)


def stage_pill(parent, stage):
    bg, fg = STAGES.get(stage, ('#ECEFF3', INK))
    return pill(parent, stage, bg, fg)


def progress_bar(parent, done, total, width=320, height=14):
    """Barre de progression plate ; total 0 = barre vide grise."""
    c = tk.Canvas(parent, width=width, height=height, bg=parent.cget('bg'), highlightthickness=0)
    c.create_rectangle(0, 0, width, height, fill='#E3E8F0', outline='')
    if total:
        c.create_rectangle(0, 0, int(width * max(0, min(1, done / total))), height, fill=BRAND, outline='')
    return c
