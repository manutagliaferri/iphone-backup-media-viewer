"""
sidebar.py — Pannello laterale sinistro di BackupManager
Mostra le informazioni del dispositivo, statistiche e filtri rapidi.
"""

import tkinter as tk
from tkinter import ttk
from typing import Callable

C = {
    'bg':        '#111111',
    'bg2':       '#1c1c1e',
    'text':      '#ffffff',
    'text2':     '#8e8e93',
    'accent':    '#0a84ff',
    'sep':       '#2c2c2e',
    'active_bg': '#1a3a6e',
}


class Sidebar(tk.Frame):
    """Pannello laterale con info dispositivo e controlli filtro."""

    def __init__(self, parent, on_filter_change: Callable, **kwargs):
        super().__init__(parent, bg=C['bg'], width=210, **kwargs)
        self.pack_propagate(False)
        self.on_filter_change = on_filter_change
        self._active = 'all'
        self._filter_btns: dict = {}
        self._create_ui()

    # ── Costruzione UI ────────────────────────────────────────────────────────

    def _create_ui(self):
        # Logo
        logo = tk.Frame(self, bg=C['bg'])
        logo.pack(fill='x', padx=16, pady=(20, 12))

        tk.Label(logo, text='💾', font=('Helvetica Neue', 26),
                 bg=C['bg'], fg=C['text']).pack(side='left')
        tk.Label(logo, text='  BackupManager',
                 font=('Helvetica Neue', 13, 'bold'),
                 bg=C['bg'], fg=C['text']).pack(side='left')

        self._sep()

        # ── Sezione dispositivo
        dev = tk.Frame(self, bg=C['bg'])
        dev.pack(fill='x', padx=16, pady=10)

        self._v_name    = tk.StringVar(value='Nessun backup aperto')
        self._v_model   = tk.StringVar(value='')
        self._v_ios     = tk.StringVar(value='')
        self._v_backup  = tk.StringVar(value='')

        tk.Label(dev, textvariable=self._v_name,
                 font=('Helvetica Neue', 12, 'bold'),
                 fg=C['text'], bg=C['bg'],
                 wraplength=175, justify='left').pack(anchor='w')

        tk.Label(dev, textvariable=self._v_model,
                 font=('Helvetica Neue', 10),
                 fg=C['text2'], bg=C['bg'],
                 wraplength=175, justify='left').pack(anchor='w')

        tk.Label(dev, textvariable=self._v_ios,
                 font=('Helvetica Neue', 10),
                 fg=C['text2'], bg=C['bg']).pack(anchor='w')

        tk.Label(dev, textvariable=self._v_backup,
                 font=('Helvetica Neue', 10),
                 fg=C['text2'], bg=C['bg']).pack(anchor='w', pady=(2, 0))

        self._sep()

        # ── Statistiche
        stats = tk.Frame(self, bg=C['bg'])
        stats.pack(fill='x', padx=16, pady=8)

        tk.Label(stats, text='LIBRERIA',
                 font=('Helvetica Neue', 9, 'bold'),
                 fg=C['text2'], bg=C['bg']).pack(anchor='w', pady=(0, 6))

        self._v_photos = tk.StringVar(value='—')
        self._v_videos = tk.StringVar(value='—')
        self._v_size   = tk.StringVar(value='')

        self._stat_row(stats, '📷  Foto',  self._v_photos)
        self._stat_row(stats, '🎬  Video', self._v_videos)
        self._stat_row(stats, '📦  Totale', self._v_size)

        self._sep()

        # ── Filtri
        flt = tk.Frame(self, bg=C['bg'])
        flt.pack(fill='x', padx=8, pady=8)

        tk.Label(flt, text='FILTRI',
                 font=('Helvetica Neue', 9, 'bold'),
                 fg=C['text2'], bg=C['bg'],
                 padx=8).pack(anchor='w', pady=(0, 4))

        for fid, icon, label in [
            ('all',   '🔷', 'Tutto'),
            ('photo', '📷', 'Foto'),
            ('video', '🎬', 'Video'),
        ]:
            btn = self._filter_btn(flt, fid, f'{icon}  {label}')
            self._filter_btns[fid] = btn

        self._update_btns()

        self._sep()

        # ── Cache info
        self._v_cache = tk.StringVar(value='')
        tk.Label(self, textvariable=self._v_cache,
                 font=('Helvetica Neue', 9), fg=C['text2'],
                 bg=C['bg'], padx=16).pack(anchor='w', pady=4)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _sep(self):
        tk.Frame(self, bg=C['sep'], height=1).pack(fill='x', pady=2)

    def _stat_row(self, parent, label: str, var: tk.StringVar):
        row = tk.Frame(parent, bg=C['bg'])
        row.pack(fill='x', pady=2)
        tk.Label(row, text=label, font=('Helvetica Neue', 11),
                 fg=C['text'], bg=C['bg']).pack(side='left')
        tk.Label(row, textvariable=var, font=('Helvetica Neue', 11, 'bold'),
                 fg=C['accent'], bg=C['bg']).pack(side='right')

    def _filter_btn(self, parent, fid: str, text: str) -> tk.Label:
        lbl = tk.Label(parent, text=text,
                       font=('Helvetica Neue', 12),
                       fg=C['text'], bg=C['bg'],
                       anchor='w', padx=12, pady=7,
                       cursor='pointinghand')
        lbl.pack(fill='x', pady=1)
        lbl.bind('<Button-1>', lambda e, f=fid: self._select(f))
        lbl.bind('<Enter>',    lambda e, b=lbl, f=fid: self._hover_in(b, f))
        lbl.bind('<Leave>',    lambda e, b=lbl, f=fid: self._hover_out(b, f))
        return lbl

    def _select(self, fid: str):
        self._active = fid
        self._update_btns()
        self.on_filter_change(fid)

    def _hover_in(self, btn: tk.Label, fid: str):
        if fid != self._active:
            btn.configure(bg=C['bg2'])

    def _hover_out(self, btn: tk.Label, fid: str):
        btn.configure(bg=C['active_bg'] if fid == self._active else C['bg'])

    def _update_btns(self):
        for fid, btn in self._filter_btns.items():
            if fid == self._active:
                btn.configure(bg=C['active_bg'], fg=C['accent'])
            else:
                btn.configure(bg=C['bg'], fg=C['text'])

    # ── API pubblica ──────────────────────────────────────────────────────────

    def update_device_info(self, info, photo_count: int, video_count: int,
                           total_size_bytes: int = 0):
        self._v_name.set(info.device_name)
        self._v_model.set(info._get_model_name() if info.product_type else '')
        self._v_ios.set(f'iOS {info.ios_version}' if info.ios_version else '')

        if info.last_backup_date:
            self._v_backup.set('Backup: ' + info.last_backup_date.strftime('%d %b %Y'))
        else:
            self._v_backup.set('')

        self._v_photos.set(f'{photo_count:,}')
        self._v_videos.set(f'{video_count:,}')

        if total_size_bytes > 0:
            gb = total_size_bytes / 1024 ** 3
            self._v_size.set(f'{gb:.2f} GB')
        else:
            self._v_size.set(f'{photo_count + video_count:,} file')

    def set_cache_info(self, size_str: str):
        self._v_cache.set(f'Cache: {size_str}')

    def clear(self):
        self._v_name.set('Nessun backup aperto')
        self._v_model.set('')
        self._v_ios.set('')
        self._v_backup.set('')
        self._v_photos.set('—')
        self._v_videos.set('—')
        self._v_size.set('')
