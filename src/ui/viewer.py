"""
viewer.py — Visualizzatore a schermo intero per foto e video
Foto: zoom con rotella, pan con drag, navigazione ←/→.
Video: player OpenCV con play/pause, scrubber, apertura QuickTime.
"""

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk, ImageOps
import threading
import time
import subprocess
import os
from typing import List, Optional

C = {
    'bg':         '#000000',
    'ctrl_bg':    '#1c1c1e',
    'ctrl_brd':   '#3a3a3c',
    'text':       '#ffffff',
    'text2':      '#8e8e93',
    'accent':     '#0a84ff',
    'btn':        '#3a3a3c',
    'btn_hov':    '#5a5a5e',
    'overlay_bg': '#1a1a1a',
}

try:
    import cv2
    CV2_OK = True
except ImportError:
    CV2_OK = False


class MediaViewer(tk.Toplevel):
    """Viewer a schermo intero per foto e video dal backup iPhone."""

    def __init__(self, parent, items: List, start: int = 0):
        super().__init__(parent)
        self.items   = items
        self.idx     = max(0, min(start, len(items) - 1))

        # Stato foto
        self._zoom       = 1.0
        self._pan_x      = 0
        self._pan_y      = 0
        self._drag_orig  = None
        self._pan_orig   = None
        self._photo_ref  = None   # PhotoImage corrente
        self._pil_img    = None   # PIL Image corrente (per zoom)

        # Stato video
        self._cap        = None
        self._playing    = False
        self._fps        = 24.0
        self._total_fr   = 0
        self._cur_fr     = 0
        self._vphoto     = None   # PhotoImage video
        self._seek_var   = tk.DoubleVar(value=0)

        self._init_window()
        self._build_ui()
        self._bind()
        self._show()

    # ── Setup finestra ─────────────────────────────────────────────────────────

    def _init_window(self):
        self.title('BackupManager — Visualizza')
        self.configure(bg=C['bg'])
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w, h = min(1440, sw - 80), min(900, sh - 80)
        self.geometry(f'{w}x{h}+{(sw-w)//2}+{(sh-h)//2}')
        self.resizable(True, True)

    # ── Costruzione UI ─────────────────────────────────────────────────────────

    def _build_ui(self):
        # Canvas principale
        self.canvas = tk.Canvas(self, bg=C['bg'], highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)

        # ── Barra info in alto (overlay)
        self._top = tk.Frame(self, bg=C['overlay_bg'])

        self._v_name = tk.StringVar()
        self._v_info = tk.StringVar()

        tk.Label(self._top, textvariable=self._v_name,
                 fg=C['text'], bg=C['overlay_bg'],
                 font=('Helvetica Neue', 14, 'bold'),
                 padx=16, pady=10).pack(side='left')
        tk.Label(self._top, textvariable=self._v_info,
                 fg=C['text2'], bg=C['overlay_bg'],
                 font=('Helvetica Neue', 12),
                 padx=16, pady=10).pack(side='right')

        self._top.place(x=0, y=0, relwidth=1)

        # ── Bottoni navigazione
        nav_cfg = dict(font=('Helvetica Neue', 52, 'bold'),
                       fg='white', bg=C['overlay_bg'],
                       padx=6, pady=16, cursor='pointinghand')

        self._prev = tk.Label(self, text='‹', **nav_cfg)
        self._next = tk.Label(self, text='›', **nav_cfg)
        self._prev.place(x=0, rely=.5, anchor='w')
        self._next.place(relx=1, rely=.5, anchor='e')

        self._prev.bind('<Button-1>', lambda e: self._nav(-1))
        self._next.bind('<Button-1>', lambda e: self._nav(+1))

        # ── Controlli video (nascosti di default)
        self._ctrl = tk.Frame(self, bg=C['ctrl_bg'], height=52)

        self._play_btn = tk.Label(
            self._ctrl, text='▶',
            font=('Helvetica Neue', 22),
            fg=C['text'], bg=C['ctrl_bg'],
            padx=12, pady=10, cursor='pointinghand',
        )
        self._play_btn.pack(side='left')
        self._play_btn.bind('<Button-1>', lambda e: self._toggle_play())

        self._v_time = tk.StringVar(value='0:00 / 0:00')
        tk.Label(self._ctrl, textvariable=self._v_time,
                 fg=C['text2'], bg=C['ctrl_bg'],
                 font=('Helvetica Neue', 12), padx=8).pack(side='left')

        self._scrub = ttk.Scale(
            self._ctrl, orient='horizontal',
            variable=self._seek_var,
            command=self._seek,
        )
        self._scrub.pack(side='left', fill='x', expand=True, padx=8)

        qt_btn = tk.Label(
            self._ctrl, text='🎬  Apri in QuickTime',
            fg=C['accent'], bg=C['ctrl_bg'],
            font=('Helvetica Neue', 12),
            padx=12, pady=10, cursor='pointinghand',
        )
        qt_btn.pack(side='right', padx=4)
        qt_btn.bind('<Button-1>', lambda e: self._open_qt())

    def _bind(self):
        self.bind('<Escape>',     lambda e: self.destroy())
        self.bind('<Left>',       lambda e: self._nav(-1))
        self.bind('<Right>',      lambda e: self._nav(+1))
        self.bind('<space>',      lambda e: self._toggle_play())

        self.canvas.bind('<MouseWheel>', self._wheel_zoom)
        self.canvas.bind('<Button-4>',   lambda e: self._zoom_step(1.15))
        self.canvas.bind('<Button-5>',   lambda e: self._zoom_step(0.87))

        self.canvas.bind('<ButtonPress-1>',   self._drag_start)
        self.canvas.bind('<B1-Motion>',       self._drag_move)
        self.canvas.bind('<ButtonRelease-1>', self._drag_end)

        self.canvas.bind('<Configure>', lambda e: self._redisplay())
        self.protocol('WM_DELETE_WINDOW', self.destroy)

    # ── Visualizzazione ────────────────────────────────────────────────────────

    def _show(self):
        """Mostra l'elemento corrente (foto o video)."""
        if not self.items:
            return
        self._stop_video()
        item = self.items[self.idx]

        self._v_name.set(item.filename)
        self._v_info.set(
            f'{self.idx + 1} / {len(self.items)}'
            f'  •  {item.size_str}'
            f'  •  {item.date_str}'
        )

        self._zoom  = 1.0
        self._pan_x = self._pan_y = 0
        self._pil_img = None

        if item.is_video:
            self._show_video(item)
        else:
            self._show_photo(item)

    # ── FOTO ──────────────────────────────────────────────────────────────────

    def _show_photo(self, item):
        self._ctrl.place_forget()
        self._nav_update()
        threading.Thread(target=self._load_photo, args=(item,), daemon=True).start()

    def _load_photo(self, item):
        """Carica foto in background."""
        img = None
        try:
            img = Image.open(item.physical_path)
            img = ImageOps.exif_transpose(img).convert('RGB')
        except Exception:
            try:
                import tempfile
                tmp = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
                tmp.close()
                subprocess.run(
                    ['sips', '-s', 'format', 'jpeg',
                     '-s', 'formatOptions', 'best',
                     item.physical_path, '--out', tmp.name],
                    capture_output=True, timeout=30
                )
                img = Image.open(tmp.name).convert('RGB')
                img.load()
                os.unlink(tmp.name)
            except Exception:
                pass

        if img:
            self.canvas.after(0, self._display_photo, img)

    def _display_photo(self, img: Image.Image):
        self._pil_img = img
        cw = self.canvas.winfo_width()  or 1200
        ch = self.canvas.winfo_height() or 800
        iw, ih = img.size
        scale = min(cw / iw, ch / ih) * self._zoom
        nw = max(1, int(iw * scale))
        nh = max(1, int(ih * scale))

        resized = img.resize((nw, nh), Image.LANCZOS)
        photo   = ImageTk.PhotoImage(resized)
        self._photo_ref = photo

        cx = cw // 2 + self._pan_x
        cy = ch // 2 + self._pan_y

        self.canvas.delete('all')
        self.canvas.create_image(cx, cy, image=photo, anchor='center', tags='photo')

    def _redisplay(self):
        if self._pil_img:
            self._display_photo(self._pil_img)

    # ── ZOOM / PAN ────────────────────────────────────────────────────────────

    def _wheel_zoom(self, event):
        self._zoom_step(1.15 if event.delta > 0 else 0.87)

    def _zoom_step(self, factor: float):
        self._zoom = max(0.05, min(20.0, self._zoom * factor))
        self._redisplay()

    def _drag_start(self, event):
        self._drag_orig = (event.x, event.y)
        self._pan_orig  = (self._pan_x, self._pan_y)
        self.canvas.configure(cursor='fleur')

    def _drag_move(self, event):
        if self._drag_orig and self._pan_orig:
            dx = event.x - self._drag_orig[0]
            dy = event.y - self._drag_orig[1]
            self._pan_x = self._pan_orig[0] + dx
            self._pan_y = self._pan_orig[1] + dy
            self._redisplay()

    def _drag_end(self, event):
        self._drag_orig = None
        self.canvas.configure(cursor='arrow')

    # ── VIDEO ─────────────────────────────────────────────────────────────────

    def _show_video(self, item):
        """Inizializza il player video."""
        if not CV2_OK:
            self.canvas.delete('all')
            cw = self.canvas.winfo_width()  or 1200
            ch = self.canvas.winfo_height() or 800
            self.canvas.create_text(
                cw // 2, ch // 2 - 20,
                text='⚠  opencv-python non installato\n\n'
                     'Installa con:  pip3 install opencv-python\n\n'
                     'Puoi comunque aprire il video in QuickTime ↓',
                fill=C['text2'],
                font=('Helvetica Neue', 15),
                anchor='center', justify='center',
            )
            self._ctrl.place(x=0, rely=1, y=-52, relwidth=1, height=52)
            return

        self._ctrl.place(x=0, rely=1, y=-52, relwidth=1, height=52)
        self._nav_update()

        self._cap = cv2.VideoCapture(item.physical_path)
        self._fps      = self._cap.get(cv2.CAP_PROP_FPS) or 24.0
        self._total_fr = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self._cur_fr   = 0

        self._scrub.configure(from_=0, to=max(1, self._total_fr - 1))
        self._show_frame(0)
        self.after(200, self._toggle_play)   # autoplay

    def _show_frame(self, n: int):
        if not self._cap:
            return
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, n)
        ret, frame = self._cap.read()
        if ret:
            self._render_frame(frame)

    def _render_frame(self, frame):
        """Converti frame OpenCV → PhotoImage e mostralo sul canvas."""
        rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img   = Image.fromarray(rgb)
        cw    = self.canvas.winfo_width()  or 1200
        ch    = max(1, (self.canvas.winfo_height() or 800) - 52)
        iw, ih = img.size
        scale = min(cw / iw, ch / ih)
        nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
        img   = img.resize((nw, nh), Image.BILINEAR)
        photo = ImageTk.PhotoImage(img)
        self._vphoto = photo   # mantieni ref

        self.canvas.delete('all')
        self.canvas.create_image(cw // 2, ch // 2, image=photo, anchor='center')

    def _toggle_play(self):
        if not CV2_OK or not self._cap:
            return
        if self._playing:
            self._playing = False
            self._play_btn.configure(text='▶')
        else:
            self._playing = True
            self._play_btn.configure(text='⏸')
            threading.Thread(target=self._play_loop, daemon=True).start()

    def _play_loop(self):
        delay = 1.0 / self._fps
        while self._playing and self._cap:
            t0 = time.time()
            ret, frame = self._cap.read()
            if not ret:
                # Fine video: torna all'inizio
                self._playing = False
                self.canvas.after(0, self._play_btn.configure, {'text': '▶'})
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                break

            self._cur_fr = int(self._cap.get(cv2.CAP_PROP_POS_FRAMES))

            # Prepara immagine nel thread
            rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img   = Image.fromarray(rgb)
            cw    = self.canvas.winfo_width()  or 1200
            ch    = max(1, (self.canvas.winfo_height() or 800) - 52)
            iw, ih = img.size
            scale = min(cw / iw, ch / ih)
            nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
            ready = img.resize((nw, nh), Image.BILINEAR)

            self.canvas.after(0, self._push_frame, ready)
            self.canvas.after(0, self._update_progress)

            elapsed = time.time() - t0
            sleep   = delay - elapsed
            if sleep > 0:
                time.sleep(sleep)

    def _push_frame(self, img: Image.Image):
        photo = ImageTk.PhotoImage(img)
        self._vphoto = photo
        cw = self.canvas.winfo_width()  or 1200
        ch = max(1, (self.canvas.winfo_height() or 800) - 52)
        self.canvas.delete('all')
        self.canvas.create_image(cw // 2, ch // 2, image=photo, anchor='center')

    def _update_progress(self):
        self._seek_var.set(self._cur_fr)
        cs = self._cur_fr / max(1, self._fps)
        ts = self._total_fr / max(1, self._fps)
        self._v_time.set(f'{self._fmt(cs)} / {self._fmt(ts)}')

    def _seek(self, val):
        if not self._playing and self._cap:
            n = int(float(val))
            self._show_frame(n)

    def _stop_video(self):
        self._playing = False
        if self._cap:
            self._cap.release()
            self._cap = None
        self._pil_img = None

    def _open_qt(self):
        if self.items and self.idx < len(self.items):
            subprocess.run(['open', '-a', 'QuickTime Player',
                            self.items[self.idx].physical_path])

    @staticmethod
    def _fmt(sec: float) -> str:
        m = int(sec) // 60
        s = int(sec) % 60
        return f'{m}:{s:02d}'

    # ── Navigazione ───────────────────────────────────────────────────────────

    def _nav(self, d: int):
        new = self.idx + d
        if 0 <= new < len(self.items):
            self.idx = new
            self._show()

    def _nav_update(self):
        self._prev.configure(fg='white' if self.idx > 0 else C['text2'])
        self._next.configure(fg='white' if self.idx < len(self.items) - 1 else C['text2'])

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def destroy(self):
        self._stop_video()
        super().destroy()
