"""
toolbar.py — Barra degli strumenti superiore di BackupManager
Contiene: Apri Backup, Ricerca, Ordinamento, Slider zoom, Esporta.
"""

import tkinter as tk
from tkinter import ttk
from typing import Callable

C = {
    'bg':          '#242424',
    'text':        '#ffffff',
    'text2':       '#8e8e93',
    'btn':         '#3a3a3c',
    'btn_hover':   '#4a4a4e',
    'search_bg':   '#3a3a3c',
    'export_bg':   '#0a84ff',
    'export_hov':  '#0070e0',
    'export_dis':  '#555555',
}


class Toolbar(tk.Frame):
    """Barra degli strumenti con tutti i controlli principali."""

    def __init__(self, parent,
                 on_open: Callable,
                 on_search: Callable,
                 on_sort: Callable,
                 on_export: Callable,
                 on_zoom: Callable,
                 **kwargs):
        super().__init__(parent, bg=C['bg'], height=54, **kwargs)
        self.pack_propagate(False)

        self._on_open   = on_open
        self._on_search = on_search
        self._on_sort   = on_sort
        self._on_export = on_export
        self._on_zoom   = on_zoom

        self._export_enabled = False
        self._zoom_var  = tk.IntVar(value=180)
        self._sort_var  = tk.StringVar(value='Data ↓')
        self._search_active = False

        self._create_ui()

    # ── Costruzione ───────────────────────────────────────────────────────────

    def _create_ui(self):
        # ── Sinistra: Apri Backup
        left = tk.Frame(self, bg=C['bg'])
        left.pack(side='left', padx=14, pady=10)

        self._open_btn = self._btn(left, '📁  Apri Backup', self._on_open,
                                   bg=C['btn'], hov=C['btn_hover'])
        self._open_btn.pack(side='left')

        # ── Centro: Ricerca
        center = tk.Frame(self, bg=C['bg'])
        center.pack(side='left', fill='x', expand=True, padx=8)

        search_box = tk.Frame(center, bg=C['search_bg'],
                               padx=8, pady=0)
        search_box.pack(fill='x', padx=60)

        tk.Label(search_box, text='🔍',
                 bg=C['search_bg'], fg=C['text2'],
                 font=('Helvetica Neue', 13)).pack(side='left', pady=7)

        self._search_var = tk.StringVar()

        self._search_entry = tk.Entry(
            search_box,
            textvariable=self._search_var,
            bg=C['search_bg'], fg=C['text2'],
            insertbackground=C['text'],
            relief='flat', bd=0,
            font=('Helvetica Neue', 12),
            width=30,
        )
        self._search_entry.pack(side='left', fill='x', expand=True, padx=6, pady=7)
        self._search_entry.insert(0, 'Cerca per nome file...')
        self._search_entry.bind('<FocusIn>',  self._focus_in)
        self._search_entry.bind('<FocusOut>', self._focus_out)

        # Pulsante clear
        self._clear_btn = tk.Label(
            search_box, text='✕',
            bg=C['search_bg'], fg=C['text2'],
            font=('Helvetica Neue', 11),
            cursor='pointinghand', pady=7, padx=4
        )
        self._clear_btn.bind('<Button-1>', lambda e: self._clear_search())
        # Aggancia trace DOPO che _clear_btn è stato creato
        self._search_var.trace_add('write', self._on_search_change)

        # ── Destra: Sort + Zoom + Esporta
        right = tk.Frame(self, bg=C['bg'])
        right.pack(side='right', padx=14, pady=10)

        # Esporta
        self._export_lbl = self._btn(
            right, '⬆  Esporta', self._do_export,
            bg=C['export_dis'], hov=C['export_hov'], bold=True
        )
        self._export_lbl.pack(side='right', padx=(8, 0))

        # Zoom slider
        zoom_f = tk.Frame(right, bg=C['bg'])
        zoom_f.pack(side='right', padx=10)

        tk.Label(zoom_f, text='⊟', bg=C['bg'], fg=C['text2'],
                 font=('Helvetica Neue', 13)).pack(side='left')
        tk.Scale(
            zoom_f, from_=80, to=280,
            orient='horizontal',
            variable=self._zoom_var,
            command=self._do_zoom,
            bg=C['bg'], fg=C['text'],
            troughcolor=C['btn'],
            highlightthickness=0,
            length=90, showvalue=False, relief='flat',
        ).pack(side='left')
        tk.Label(zoom_f, text='⊞', bg=C['bg'], fg=C['text2'],
                 font=('Helvetica Neue', 13)).pack(side='left')

        # Sort
        sort_f = tk.Frame(right, bg=C['bg'])
        sort_f.pack(side='right', padx=6)

        tk.Label(sort_f, text='Ordine:', bg=C['bg'],
                 fg=C['text2'], font=('Helvetica Neue', 11)).pack(side='left')

        self._sort_cb = ttk.Combobox(
            sort_f, textvariable=self._sort_var,
            values=['Data ↓', 'Data ↑', 'Nome A→Z', 'Dimensione ↓'],
            state='readonly', width=11,
            font=('Helvetica Neue', 11),
        )
        self._sort_cb.pack(side='left', padx=4)
        self._sort_cb.bind('<<ComboboxSelected>>', self._do_sort)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _btn(self, parent, text: str, cmd: Callable,
             bg: str, hov: str, bold: bool = False) -> tk.Label:
        font = ('Helvetica Neue', 12, 'bold') if bold else ('Helvetica Neue', 12)
        lbl  = tk.Label(parent, text=text, font=font,
                        fg='white', bg=bg,
                        padx=12, pady=6,
                        cursor='pointinghand', relief='flat')
        lbl.bind('<Button-1>', lambda e: cmd())
        lbl.bind('<Enter>', lambda e, b=lbl, h=hov: b.configure(bg=h))
        lbl.bind('<Leave>', lambda e, b=lbl, d=bg:  b.configure(bg=d))
        lbl._default_bg = bg
        return lbl

    # ── Azioni ────────────────────────────────────────────────────────────────

    def _focus_in(self, event):
        if self._search_entry.get() == 'Cerca per nome file...':
            self._search_entry.delete(0, 'end')
            self._search_entry.configure(fg=C['text'])
        self._search_active = True

    def _focus_out(self, event):
        self._search_active = False
        if not self._search_entry.get():
            self._search_entry.insert(0, 'Cerca per nome file...')
            self._search_entry.configure(fg=C['text2'])
            self._clear_btn.pack_forget()

    def _clear_search(self):
        self._search_entry.delete(0, 'end')
        self._search_entry.insert(0, 'Cerca per nome file...')
        self._search_entry.configure(fg=C['text2'])
        self._clear_btn.pack_forget()
        self._on_search('')

    def _on_search_change(self, *_):
        if not hasattr(self, '_clear_btn'):
            return
        q = self._search_var.get()
        if q and q != 'Cerca per nome file...':
            self._clear_btn.pack(side='right', pady=7)
            self._on_search(q)
        else:
            self._clear_btn.pack_forget()
            self._on_search('')

    def _do_zoom(self, val):
        self._on_zoom(int(float(val)))

    def _do_sort(self, event=None):
        self._on_sort(self._sort_var.get())

    def _do_export(self):
        if self._export_enabled:
            self._on_export()

    # ── API pubblica ──────────────────────────────────────────────────────────

    def set_export_enabled(self, enabled: bool):
        """Abilita/disabilita il pulsante Esporta."""
        self._export_enabled = enabled
        if enabled:
            self._export_lbl.configure(bg=C['export_bg'], cursor='pointinghand')
            self._export_lbl._default_bg = C['export_bg']
        else:
            self._export_lbl.configure(bg=C['export_dis'], cursor='arrow')
            self._export_lbl._default_bg = C['export_dis']
