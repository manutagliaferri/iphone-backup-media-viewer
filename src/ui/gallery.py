"""
gallery.py — Galleria foto/video a griglia per BackupManager
Griglia scrollabile con lazy-loading delle miniature via thread pool.
Selezione singola, multipla (Cmd+Click) e per range (Shift+Click).

Ottimizzazioni v2:
  - Hover: aggiorna solo le 2 tile interessate (no full re-render)
  - Viewport culling: carica thumbnail solo per le tile visibili
  - Resize debounce a 80ms
  - _fit_crop usa BILINEAR invece di LANCZOS per velocità
  - Cache memoria limitata a 800 voci (LRU)
"""

import tkinter as tk
from tkinter import ttk
from PIL import ImageTk
import math
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import List, Set, Optional, Callable

C = {
    'bg':       '#1c1c1e',
    'card':     '#2c2c2e',
    'card_hov': '#3a3a3c',
    'sel_bg':   '#0a2a4f',
    'sel_brd':  '#0a84ff',
    'ph':       '#3a3a3c',
    'empty':    '#48484a',
    'text':     '#ffffff',
    'text2':    '#8e8e93',
}
PAD   = 8
SEL_W = 3
_MEM_CACHE_MAX = 800   # max thumbnail in memoria


class GalleryView(tk.Frame):
    """
    Griglia scrollabile con thumbnail lazy-loaded.
    Usa tk.Canvas per alte prestazioni con librerie di migliaia di foto.
    """

    def __init__(self, parent, media_manager,
                 on_open: Callable,
                 on_selection_change: Callable,
                 **kwargs):
        super().__init__(parent, bg=C['bg'], **kwargs)

        self.mm      = media_manager
        self.on_open = on_open
        self.on_sel  = on_selection_change

        self._items:    List          = []
        self._filtered: List          = []
        self._sel:      Set[str]      = set()
        self._hover_id: Optional[str] = None
        self._refs:     OrderedDict   = OrderedDict()  # LRU cache PhotoImage
        self._pos:      dict          = {}              # file_id → (x,y,sz)
        self._thumb_sz  = 180
        self._executor  = ThreadPoolExecutor(max_workers=8, thread_name_prefix='thumb')
        self._pending:  dict          = {}
        self._resize_job            = None   # debounce Configure

        self._create_ui()
        self._bind()

    # ── Costruzione ───────────────────────────────────────────────────────────

    def _create_ui(self):
        self.vsb = ttk.Scrollbar(self, orient='vertical')
        self.vsb.pack(side='right', fill='y')

        self.canvas = tk.Canvas(
            self, bg=C['bg'],
            highlightthickness=0,
            yscrollcommand=self.vsb.set,
        )
        self.canvas.pack(side='left', fill='both', expand=True)
        self.vsb.configure(command=self.canvas.yview)

        self._load_lbl = tk.Label(
            self, text='⏳  Caricamento backup…',
            font=('Helvetica Neue', 16),
            fg=C['text2'], bg=C['bg']
        )

    def _bind(self):
        cv = self.canvas
        cv.bind('<Button-1>',        self._click)
        cv.bind('<Double-Button-1>', self._dblclick)
        cv.bind('<Configure>',       self._on_configure)
        cv.bind('<Motion>',          self._hover)
        cv.bind('<Leave>',           self._leave)
        cv.bind('<MouseWheel>',      self._scroll)
        cv.bind('<Button-4>',        lambda e: cv.yview_scroll(-1, 'units'))
        cv.bind('<Button-5>',        lambda e: cv.yview_scroll(1,  'units'))
        # Carica thumbnail quando lo scroll si ferma
        cv.bind('<ButtonRelease-4>', lambda e: self._queue_visible_thumbs())
        cv.bind('<ButtonRelease-5>', lambda e: self._queue_visible_thumbs())
        self.vsb.bind('<ButtonRelease-1>', lambda e: self._queue_visible_thumbs())

    # ── API pubblica ──────────────────────────────────────────────────────────

    def load_items(self, items: list):
        self._cancel_pending()
        self._items    = items
        self._filtered = items[:]
        self._sel.clear()
        self._refs.clear()
        self._pos.clear()
        self.on_sel(0)
        self._render()
        self.after(100, self._queue_visible_thumbs)

    def filter_items(self, mtype: str = 'all', search: str = ''):
        items = self._items
        if mtype == 'photo':
            items = [i for i in items if i.is_photo]
        elif mtype == 'video':
            items = [i for i in items if i.is_video]
        if search:
            lo = search.lower()
            items = [i for i in items if lo in i.filename.lower()]
        self._filtered = items
        self._sel = {s for s in self._sel
                     if any(it.file_id == s for it in self._filtered)}
        self._render()
        self.after(50, self._queue_visible_thumbs)

    def sort_items(self, key: str):
        from datetime import datetime as dt
        rev = key.endswith('↓')
        if 'Data' in key:
            self._filtered.sort(
                key=lambda x: x.date_modified or x.date_created or dt.min,
                reverse=rev)
        elif 'Nome' in key:
            self._filtered.sort(key=lambda x: x.filename.lower())
        elif 'Dimensione' in key:
            self._filtered.sort(key=lambda x: x.size, reverse=True)
        self._render()

    def set_thumbnail_size(self, sz: int):
        self._thumb_sz = sz
        self._refs.clear()
        self._cancel_pending()
        self._render()
        self.after(50, self._queue_visible_thumbs)

    def get_selected(self) -> list:
        return [i for i in self._filtered if i.file_id in self._sel]

    def select_all(self):
        self._sel = {i.file_id for i in self._filtered}
        self._render()
        self.on_sel(len(self._sel))

    def deselect_all(self):
        self._sel.clear()
        self._render()
        self.on_sel(0)

    def show_loading(self, visible: bool):
        if visible:
            self._load_lbl.place(relx=.5, rely=.5, anchor='center')
        else:
            self._load_lbl.place_forget()

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _layout(self):
        """Calcola colonne/tile data la larghezza attuale. Ritorna (cols, tile, xoff)."""
        w    = self.canvas.winfo_width() or 900
        tile = self._thumb_sz + PAD * 2
        cols = max(1, (w - PAD) // tile)
        gw   = cols * tile
        xoff = (w - gw) // 2 + PAD
        return cols, tile, xoff

    def _render(self):
        """Ridisegna l'intera galleria (chiamato solo su cambi strutturali)."""
        cv = self.canvas
        cv.delete('all')
        self._pos.clear()

        if not self._filtered:
            self._draw_empty()
            return

        cols, tile, xoff = self._layout()

        for idx, item in enumerate(self._filtered):
            col = idx % cols
            row = idx // cols
            x   = xoff + col * tile
            y   = PAD  + row * tile
            self._draw_tile(x, y, item)

        rows    = math.ceil(len(self._filtered) / cols)
        total_h = PAD + rows * tile + PAD
        w       = self.canvas.winfo_width() or 900
        cv.configure(scrollregion=(0, 0, w, total_h))

    def _draw_tile(self, x: int, y: int, item):
        cv  = self.canvas
        fid = item.file_id
        sz  = self._thumb_sz
        sel = fid in self._sel
        hov = fid == self._hover_id

        bg = C['sel_bg'] if sel else (C['card_hov'] if hov else C['card'])
        cv.create_rectangle(x, y, x + sz, y + sz,
                            fill=bg, outline='',
                            tags=(f't_{fid}', 'tile'))

        if fid in self._refs:
            cv.create_image(x + sz // 2, y + sz // 2,
                            image=self._refs[fid], anchor='center',
                            tags=(f'i_{fid}', 'img'))
        else:
            cv.create_rectangle(x + 2, y + 2, x + sz - 2, y + sz - 2,
                                fill=C['ph'], outline='',
                                tags=(f'p_{fid}', 'ph'))

        if sel:
            cv.create_rectangle(x + 1, y + 1, x + sz - 1, y + sz - 1,
                                fill='', outline=C['sel_brd'],
                                width=SEL_W,
                                tags=(f's_{fid}', 'sel'))

        if item.is_video:
            self._draw_badge(x, y, sz, fid)

        self._pos[fid] = (x, y, sz)

    def _draw_badge(self, x: int, y: int, sz: int, fid: str):
        cv = self.canvas
        bw, bh = 32, 18
        bx = x + 6
        by = y + sz - bh - 6
        cv.create_oval(bx, by, bx + bw, by + bh,
                       fill='#111111', outline='',
                       tags=(f'bd_{fid}', 'badge'))
        px, py = bx + 9, by + 4
        cv.create_polygon(px, py, px, py + 10, px + 12, py + 5,
                          fill='white', outline='',
                          tags=(f'pl_{fid}', 'play'))

    def _draw_empty(self):
        cv = self.canvas
        w  = cv.winfo_width()  or 900
        h  = cv.winfo_height() or 600
        cv.create_text(w // 2, h // 2 - 30,
                       text='📂', font=('Helvetica Neue', 56),
                       fill=C['empty'], anchor='center')
        cv.create_text(w // 2, h // 2 + 50,
                       text='Nessun contenuto trovato\n'
                            'Apri un backup iPhone con "📁 Apri Backup"',
                       font=('Helvetica Neue', 14),
                       fill=C['empty'], anchor='center', justify='center')

    # ── Hover ottimizzato (no full re-render) ─────────────────────────────────

    def _update_tile_bg(self, fid: Optional[str], sel: bool, hov: bool):
        """Aggiorna solo il colore di sfondo di una singola tile."""
        if fid is None or fid not in self._pos:
            return
        bg = C['sel_bg'] if sel else (C['card_hov'] if hov else C['card'])
        items = self.canvas.find_withtag(f't_{fid}')
        if items:
            self.canvas.itemconfigure(items[0], fill=bg)

    # ── Lazy loading thumbnail (solo viewport visibile) ────────────────────────

    def _visible_range(self):
        """Calcola gli indici degli elementi nella viewport visibile."""
        cv         = self.canvas
        top        = cv.canvasy(0)
        bottom     = cv.canvasy(cv.winfo_height() or 600)
        cols, tile, xoff = self._layout()
        # aggiunge 1 riga di margine sopra/sotto
        row_top    = max(0, int((top - PAD) // tile) - 1)
        row_bottom = int((bottom - PAD) // tile) + 2
        start      = row_top * cols
        end        = row_bottom * cols
        return start, end

    def _queue_visible_thumbs(self):
        """Mette in coda le thumbnail solo per le tile visibili + un buffer."""
        if not self._filtered:
            return
        start, end = self._visible_range()
        for item in self._filtered[start:end]:
            fid = item.file_id
            if fid not in self._refs and fid not in self._pending:
                fut = self._executor.submit(self._load_thumb, item)
                self._pending[fid] = fut

    def _load_thumb(self, item):
        """Thread: genera miniatura e schedula aggiornamento sul main thread."""
        try:
            sz  = (self._thumb_sz, self._thumb_sz)
            img = self.mm.get_thumbnail(item, sz)
            if img:
                photo = ImageTk.PhotoImage(img)
                self.canvas.after(0, self._apply_thumb, item.file_id, photo)
        except Exception:
            pass
        finally:
            self._pending.pop(item.file_id, None)

    def _apply_thumb(self, fid: str, photo):
        """Main thread: inserisce la thumbnail nella tile."""
        # LRU: rimuovi la voce più vecchia se sopra il limite
        if len(self._refs) >= _MEM_CACHE_MAX:
            self._refs.popitem(last=False)

        self._refs[fid] = photo

        if fid not in self._pos:
            return

        x, y, sz = self._pos[fid]
        cv = self.canvas

        cv.delete(f'p_{fid}')

        existing = cv.find_withtag(f'i_{fid}')
        if existing:
            cv.itemconfigure(existing[0], image=photo)
        else:
            cv.create_image(x + sz // 2, y + sz // 2,
                            image=photo, anchor='center',
                            tags=(f'i_{fid}', 'img'))

        for tag in (f's_{fid}', f'bd_{fid}', f'pl_{fid}'):
            cv.tag_raise(tag)

    def _cancel_pending(self):
        for fut in self._pending.values():
            fut.cancel()
        self._pending.clear()

    # ── Event handlers ─────────────────────────────────────────────────────────

    def _on_configure(self, event):
        """Debounce resize: ridisegna dopo 80ms di inattività."""
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(80, self._on_resize_done)

    def _on_resize_done(self):
        self._resize_job = None
        self._render()
        self.after(50, self._queue_visible_thumbs)

    def _at(self, x: int, y: int) -> Optional[str]:
        cx = self.canvas.canvasx(x)
        cy = self.canvas.canvasy(y)
        for fid, (fx, fy, fsz) in self._pos.items():
            if fx <= cx <= fx + fsz and fy <= cy <= fy + fsz:
                return fid
        return None

    def _click(self, event):
        fid = self._at(event.x, event.y)
        if fid is None:
            self._sel.clear()
        else:
            cmd = (event.state & 0x0008) or (event.state & 0x0004)
            sft = event.state & 0x0001
            if cmd:
                if fid in self._sel:
                    self._sel.discard(fid)
                else:
                    self._sel.add(fid)
            elif sft and self._sel:
                ids = [i.file_id for i in self._filtered]
                if fid in ids:
                    last = list(self._sel)[-1]
                    if last in ids:
                        a, b = sorted([ids.index(last), ids.index(fid)])
                        for i in ids[a:b + 1]:
                            self._sel.add(i)
            else:
                self._sel = {fid}
        self._render()
        self.on_sel(len(self._sel))

    def _dblclick(self, event):
        fid = self._at(event.x, event.y)
        if fid:
            item = next((i for i in self._filtered if i.file_id == fid), None)
            if item:
                self.on_open(item)

    def _hover(self, event):
        fid = self._at(event.x, event.y)
        if fid == self._hover_id:
            return
        prev = self._hover_id
        self._hover_id = fid
        # Aggiorna solo le 2 tile cambiate (non tutta la galleria)
        if prev:
            self._update_tile_bg(prev, prev in self._sel, False)
        if fid:
            self._update_tile_bg(fid, fid in self._sel, True)

    def _leave(self, event):
        if self._hover_id:
            prev = self._hover_id
            self._hover_id = None
            self._update_tile_bg(prev, prev in self._sel, False)

    def _scroll(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
        # Carica le thumbnail dello scroll con piccolo delay
        if hasattr(self, '_scroll_job'):
            self.after_cancel(self._scroll_job)
        self._scroll_job = self.after(150, self._queue_visible_thumbs)

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def destroy(self):
        self._cancel_pending()
        self._executor.shutdown(wait=False)
        super().destroy()
