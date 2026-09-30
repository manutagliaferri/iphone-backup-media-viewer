"""
main.py — Entry point di BackupManager
Finestra principale con toolbar, sidebar e galleria.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os
import sys

# Aggiunge src/ al path così tutti i moduli si trovano
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backup_reader import BackupReader
from media_manager import MediaManager
from ui.gallery    import GalleryView
from ui.viewer     import MediaViewer
from ui.sidebar    import Sidebar
from ui.toolbar    import Toolbar
from utils.export_utils import ExportManager

APP_VERSION = '1.0.0'

C = {
    'bg':      '#1c1c1e',
    'sep':     '#3a3a3c',
    'status':  '#242424',
    'text2':   '#8e8e93',
}


class BackupManagerApp:
    """Applicazione principale BackupManager."""

    def __init__(self, root: tk.Tk):
        self.root = root

        # Stato applicazione
        self.backup_reader: BackupReader = None
        self.media_manager = MediaManager()
        self.export_manager = ExportManager()
        self.all_items = []
        self._filter = 'all'
        self._search = ''

        self._setup_window()
        self._setup_style()
        self._build_menu()
        self._build_layout()
        # Forza il rendering iniziale (evita schermo nero al primo avvio)
        self.root.update_idletasks()
        self.root.update()

    # ── Setup finestra ────────────────────────────────────────────────────────

    def _setup_window(self):
        self.root.title('BackupManager')
        self.root.geometry('1280x800')
        self.root.minsize(960, 640)
        self.root.configure(bg=C['bg'])

        # Icona app
        icon = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'assets', 'icon.png'
        )
        if os.path.exists(icon):
            try:
                from PIL import Image, ImageTk
                img   = Image.open(icon).resize((128, 128), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self.root.iconphoto(True, photo)
                self.root._icon = photo   # mantieni riferimento
            except Exception:
                pass

    def _setup_style(self):
        s = ttk.Style()
        # Scrollbar sottile
        s.configure('Vertical.TScrollbar',
                    background=C['sep'],
                    troughcolor=C['bg'],
                    borderwidth=0,
                    arrowsize=0)
        # Combobox
        s.configure('TCombobox',
                    fieldbackground='#3a3a3c',
                    background='#3a3a3c',
                    foreground='white',
                    selectbackground='#3a3a3c')
        s.map('TCombobox',
              fieldbackground=[('readonly', '#3a3a3c')],
              foreground=[('readonly', 'white')])

    # ── Menu ──────────────────────────────────────────────────────────────────

    def _build_menu(self):
        mb = tk.Menu(self.root)

        # File
        fm = tk.Menu(mb, tearoff=0)
        fm.add_command(label='Apri Backup…',
                       command=self.open_backup, accelerator='Cmd+O')
        fm.add_separator()
        fm.add_command(label='Esporta selezionati…',
                       command=self.export_selected, accelerator='Cmd+E')
        fm.add_command(label='Esporta tutto…',
                       command=self.export_all)
        fm.add_separator()
        fm.add_command(label='Esci',
                       command=self.root.quit, accelerator='Cmd+Q')
        mb.add_cascade(label='File', menu=fm)

        # Modifica
        em = tk.Menu(mb, tearoff=0)
        em.add_command(label='Seleziona tutto',
                       command=lambda: self.gallery.select_all(),
                       accelerator='Cmd+A')
        em.add_command(label='Deseleziona tutto',
                       command=lambda: self.gallery.deselect_all(),
                       accelerator='Cmd+D')
        mb.add_cascade(label='Modifica', menu=em)

        # Vista
        vm = tk.Menu(mb, tearoff=0)
        vm.add_command(label='Tutte le foto e i video',
                       command=lambda: self._do_filter('all'))
        vm.add_command(label='Solo foto',
                       command=lambda: self._do_filter('photo'))
        vm.add_command(label='Solo video',
                       command=lambda: self._do_filter('video'))
        mb.add_cascade(label='Vista', menu=vm)

        # Aiuto
        hm = tk.Menu(mb, tearoff=0)
        hm.add_command(label='Informazioni su BackupManager…',
                       command=self._about)
        hm.add_separator()
        hm.add_command(label='Cancella cache anteprime',
                       command=self._clear_cache)
        mb.add_cascade(label='Aiuto', menu=hm)

        self.root.config(menu=mb)

        # Shortcut tastiera
        self.root.bind('<Command-o>', lambda e: self.open_backup())
        self.root.bind('<Command-e>', lambda e: self.export_selected())
        self.root.bind('<Command-a>', lambda e: self.gallery.select_all())

    # ── Layout principale ─────────────────────────────────────────────────────

    def _build_layout(self):
        # Toolbar superiore
        self.toolbar = Toolbar(
            self.root,
            on_open=self.open_backup,
            on_search=self._do_search,
            on_sort=self._do_sort,
            on_export=self.export_selected,
            on_zoom=self._do_zoom,
        )
        self.toolbar.pack(fill='x', side='top')

        # Separatore
        tk.Frame(self.root, bg=C['sep'], height=1).pack(fill='x')

        # Area contenuto
        content = tk.Frame(self.root, bg=C['bg'])
        content.pack(fill='both', expand=True)

        # Sidebar sinistra
        self.sidebar = Sidebar(content, on_filter_change=self._do_filter)
        self.sidebar.pack(side='left', fill='y')

        # Separatore verticale
        tk.Frame(content, bg=C['sep'], width=1).pack(side='left', fill='y')

        # Galleria
        self.gallery = GalleryView(
            content,
            media_manager=self.media_manager,
            on_open=self._open_item,
            on_selection_change=self._on_sel_change,
        )
        self.gallery.pack(side='left', fill='both', expand=True)

        # Separatore + Status bar
        tk.Frame(self.root, bg=C['sep'], height=1).pack(fill='x', side='bottom')
        self._build_status()

    def _build_status(self):
        bar = tk.Frame(self.root, bg=C['status'], height=26)
        bar.pack(fill='x', side='bottom')
        bar.pack_propagate(False)

        self._status = tk.StringVar(
            value='Apri un backup iPhone con il pulsante "📁 Apri Backup"')
        tk.Label(bar, textvariable=self._status,
                 font=('Helvetica Neue', 11),
                 fg=C['text2'], bg=C['status'],
                 padx=14).pack(side='left', pady=4)

    # ── Apertura backup ───────────────────────────────────────────────────────

    def open_backup(self):
        """Apre il dialogo per scegliere la cartella del backup o foto."""
        log = open(os.path.expanduser('~/.BackupManager/launch.log'), 'a')

        self.root.lift()
        self.root.focus_force()
        self.root.update()
        log.write('[open_backup] Apertura dialogo\n'); log.flush()

        folder = filedialog.askdirectory(
            title='Seleziona la cartella con foto/video o il backup iPhone',
            initialdir='/Volumes',
            parent=self.root,
        )

        log.write(f'[open_backup] Cartella scelta: {folder!r}\n'); log.flush()

        if not folder:
            log.write('[open_backup] Annullato\n'); log.close()
            return

        # ── Rilevamento automatico modalità ──────────────────────────────────
        # 1) Backup iTunes/Finder standard (con Manifest.db)
        # 2) Scansione diretta (qualsiasi cartella con foto/video)
        target = None

        if os.path.exists(os.path.join(folder, 'Manifest.db')):
            target = folder
            log.write(f'[open_backup] Modalità iTunes: {folder}\n')
        else:
            # Prova sottocartelle (es. utente seleziona cartella "Backup")
            try:
                for entry in sorted(os.listdir(folder)):
                    sub = os.path.join(folder, entry)
                    if os.path.isdir(sub) and os.path.exists(
                            os.path.join(sub, 'Manifest.db')):
                        target = sub
                        log.write(f'[open_backup] iTunes in sottocartella: {sub}\n')
                        break
            except PermissionError:
                pass

        if target is None:
            # Nessun Manifest.db: usa scansione diretta per qualsiasi cartella
            log.write('[open_backup] Nessun Manifest.db: modalità scansione diretta\n')
            target = folder

        log.write(f'[open_backup] Avvio caricamento da: {target}\n'); log.close()
        self._load_async(target)

    def _load_async(self, folder: str):
        log = open(os.path.expanduser('~/.BackupManager/launch.log'), 'a')
        log.write(f'[_load_async] Inizio caricamento: {folder}\n'); log.close()

        self._status.set('⏳  Apertura backup in corso…')
        self.gallery.show_loading(True)
        self.root.update()

        def run():
            logf = open(os.path.expanduser('~/.BackupManager/launch.log'), 'a')
            try:
                logf.write('[run] BackupReader init\n'); logf.flush()
                reader = BackupReader(folder)
                logf.write('[run] get_device_info\n'); logf.flush()
                info   = reader.get_device_info()
                logf.write('[run] get_media_files\n'); logf.flush()
                items  = reader.get_media_files(progress_callback=self._prog_cb)
                logf.write(f'[run] trovati {len(items)} elementi\n'); logf.close()
                self.root.after(0, self._on_loaded, reader, info, items)
            except Exception as e:
                import traceback
                logf.write(f'[run] ERRORE: {e}\n{traceback.format_exc()}\n'); logf.close()
                self.root.after(0, self._show_error, str(e))

        threading.Thread(target=run, daemon=True).start()

    def _show_error(self, msg: str):
        self.gallery.show_loading(False)
        self._status.set('Errore nel caricamento')
        self.root.lift()
        messagebox.showerror('Errore', f'Errore nel caricamento:\n{msg}', parent=self.root)

    def _prog_cb(self, cur: int, tot: int):
        self.root.after(
            0, self._status.set,
            f'⏳  Analisi file: {cur:,} / {tot:,}…'
        )

    def _on_loaded(self, reader, info, items):
        self.backup_reader = reader
        self.all_items     = items

        photos = sum(1 for i in items if i.is_photo)
        videos = sum(1 for i in items if i.is_video)
        total_bytes = sum(i.size for i in items)

        self.sidebar.update_device_info(info, photos, videos, total_bytes)
        self.sidebar.set_cache_info(self.media_manager.get_cache_size_str())

        self.gallery.load_items(items)
        self.gallery.show_loading(False)

        self._update_status()

    # ── Filtri / Ricerca / Sort / Zoom ────────────────────────────────────────

    def _do_filter(self, mtype: str):
        self._filter = mtype
        self.gallery.filter_items(mtype, self._search)
        self._update_status()

    def _do_search(self, q: str):
        self._search = q
        self.gallery.filter_items(self._filter, q)
        self._update_status()

    def _do_sort(self, key: str):
        self.gallery.sort_items(key)

    def _do_zoom(self, sz: int):
        self.gallery.set_thumbnail_size(sz)

    # ── Export ────────────────────────────────────────────────────────────────

    def export_selected(self):
        sel = self.gallery.get_selected()
        if not sel:
            messagebox.showinfo(
                'Nessuna selezione',
                'Seleziona prima le foto/video da esportare.\n\n'
                '• Click singolo → seleziona uno\n'
                '• Cmd+Click    → selezione multipla\n'
                '• Shift+Click  → selezione per range\n'
                '• Cmd+A        → seleziona tutto'
            )
            return
        self._run_export(sel)

    def export_all(self):
        if not self.all_items:
            messagebox.showinfo('Nessun contenuto',
                                'Carica prima un backup iPhone.')
            return
        n = len(self.all_items)
        if not messagebox.askyesno(
                'Esporta tutto',
                f'Stai per esportare {n:,} file.\n\nContinuare?'):
            return
        self._run_export(self.all_items)

    def _run_export(self, items: list):
        dest = filedialog.askdirectory(
            title='Scegli la cartella di destinazione per l\'esportazione')
        if not dest:
            return

        convert = messagebox.askyesno(
            'Formato HEIC',
            'Vuoi convertire le foto HEIC in JPEG?\n\n'
            '• Sì  →  JPEG  (compatibile con tutti i dispositivi)\n'
            '• No  →  HEIC  (formato originale, qualità massima)',
            default='no'
        )

        self._status.set(f'⬆  Esportazione di {len(items):,} file…')

        def run():
            res = self.export_manager.export_items(
                items=items,
                destination=dest,
                convert_heic=convert,
                preserve_dates=True,
                progress_callback=self._export_prog,
            )
            self.root.after(0, self._on_exported, res, dest)

        threading.Thread(target=run, daemon=True).start()

    def _export_prog(self, cur: int, tot: int, name: str):
        self.root.after(
            0, self._status.set,
            f'⬆  {cur}/{tot} — {name}'
        )

    def _on_exported(self, res: dict, dest: str):
        msg = (f'✅  Esportazione completata!\n\n'
               f'• Esportati con successo:  {res["success"]:,} file\n'
               f'• Errori:                  {res["failed"]} file\n\n'
               f'Cartella di destinazione:\n{dest}')
        if res['errors']:
            msg += '\n\nPrimi errori:\n' + '\n'.join(res['errors'][:5])

        messagebox.showinfo('Esportazione completata', msg)
        self._update_status()
        os.system(f'open "{dest}"')   # Apri Finder

    # ── Apertura elemento ─────────────────────────────────────────────────────

    def _open_item(self, item):
        """Apre l'elemento nel viewer a schermo intero."""
        filtered = self.gallery._filtered
        try:
            idx = filtered.index(item)
        except ValueError:
            idx = 0
        v = MediaViewer(self.root, filtered, idx)
        v.focus()

    # ── Selezione ─────────────────────────────────────────────────────────────

    def _on_sel_change(self, count: int):
        self.toolbar.set_export_enabled(count > 0)
        self._update_status()

    # ── Status bar ────────────────────────────────────────────────────────────

    def _update_status(self):
        if not self.all_items:
            self._status.set(
                'Apri un backup iPhone con il pulsante "📁 Apri Backup"')
            return

        vis = len(self.gallery._filtered)
        tot = len(self.all_items)
        sel = len(self.gallery._sel)

        parts = [f'{vis:,} elementi']
        if vis != tot:
            parts.append(f'{tot:,} totali')
        if sel:
            parts.append(f'✓ {sel:,} selezionati')

        self._status.set('  •  '.join(parts))

    # ── Misc ──────────────────────────────────────────────────────────────────

    def _about(self):
        messagebox.showinfo(
            'Informazioni su BackupManager',
            f'BackupManager  v{APP_VERSION}\n\n'
            'Visualizza ed esporta foto e video\n'
            'dai backup iPhone su macOS.\n\n'
            'Sviluppato con Python · tkinter · Pillow · OpenCV\n\n'
            '© 2025'
        )

    def _clear_cache(self):
        sz = self.media_manager.get_cache_size_str()
        if messagebox.askyesno(
                'Cancella cache',
                f'Dimensione cache attuale: {sz}\n\n'
                'Cancellare tutte le anteprime salvate?\n'
                '(Verranno rigenerate alla prossima apertura)'):
            self.media_manager.clear_disk_cache()
            self.sidebar.set_cache_info('0.0 MB')
            messagebox.showinfo('Cache cancellata',
                                'Cache delle anteprime eliminata con successo.')


# ── Entry point ───────────────────────────────────────────────────────────────

def _force_macos_render(root: tk.Tk):
    """
    Forza il rendering dei widget su macOS.
    Quando l'app è lanciata da un .app bundle tkinter non ridisegna i widget
    finché la finestra non riceve un evento. Questo trick lo innesca.
    """
    try:
        root.update_idletasks()
        root.update()
        # Ridimensiona di 1px e torna indietro → forza un redraw completo
        g = root.geometry()
        w, rest = g.split('x', 1)
        h = rest.split('+')[0]
        root.geometry(f'{int(w)+1}x{h}')
        root.update_idletasks()
        root.geometry(g)
        root.update_idletasks()
        root.lift()
        root.focus_force()
    except Exception:
        pass


def main():
    root = tk.Tk()
    BackupManagerApp(root)
    # Forza il rendering dopo 200ms (finestra già visibile a quel punto)
    root.after(200, _force_macos_render, root)
    root.mainloop()


if __name__ == '__main__':
    main()
