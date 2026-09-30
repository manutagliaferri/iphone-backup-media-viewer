"""
backup_reader.py — iPhone Backup Parser per BackupManager

Supporta tre modalità (rilevazione automatica):
  1. iTunes/Finder standard   — Manifest.db valido con dati
  2. Snapshot (iOS 17+)       — Manifest.db vuoto + cartella Snapshot/
                                File hashed senza estensione; tipo rilevato
                                via magic bytes.
  3. Scansione diretta        — Qualsiasi cartella con foto/video nominati
                                normalmente (es. copia manuale da iPhone).
"""

import sqlite3
import os
import plistlib
from dataclasses import dataclass
from typing import List, Optional, Callable
from datetime import datetime

# Offset tra Mac Absolute Time (epoch 2001-01-01) e Unix (epoch 1970-01-01)
MAC_EPOCH_OFFSET = 978307200

PHOTO_EXTENSIONS = frozenset({
    '.heic', '.heif', '.jpg', '.jpeg', '.png', '.gif',
    '.tiff', '.tif', '.bmp', '.webp', '.dng', '.raw'
})
VIDEO_EXTENSIONS = frozenset({
    '.mp4', '.mov', '.m4v', '.avi', '.mkv', '.3gp', '.3g2', '.wmv'
})

# Percorsi da escludere in modalità iTunes (thumbnail di sistema, ecc.)
SKIP_PREFIXES = (
    'Media/PhotoData/Thumbnails/',
    'Media/PhotoData/CPL/',
    'Media/PhotoData/Mutations/',
    'Media/.Thumbnails/',
    'Media/DCIM/.',
)

# Cartelle da ignorare in modalità scansione diretta
SKIP_DIRS = {
    'Thumbnails', '.Thumbnails', 'Mutations', 'CPL',
    '__MACOSX', '.Spotlight-V100', '.fseventsd',
    'PhotoData', 'tmp', 'Temp', 'Snapshot',
}

# ── Magic bytes per identificare tipo file senza estensione ──────────────────
# Ogni entry: (sequenza_bytes, media_type, estensione)
# Il magic viene cercato sia all'inizio del file sia come substring nei primi 28 byte
_MAGIC = [
    (b'\xff\xd8\xff',                  'photo', '.jpg'),   # JPEG
    (b'\x89PNG\r\n\x1a\n',            'photo', '.png'),   # PNG
    (b'GIF87a',                        'photo', '.gif'),   # GIF87
    (b'GIF89a',                        'photo', '.gif'),   # GIF89
    (b'II*\x00',                       'photo', '.tiff'),  # TIFF LE
    (b'MM\x00*',                       'photo', '.tiff'),  # TIFF BE
    (b'ftypheic',                      'photo', '.heic'),  # HEIC
    (b'ftypmif1',                      'photo', '.heic'),  # HEIF
    (b'ftypavif',                      'photo', '.heic'),  # AVIF
    (b'\x1aE\xdf\xa3',                'video', '.mkv'),   # MKV/WebM
    (b'RIFF',                          'video', '.avi'),   # AVI (segue WAVE/AVI)
    (b'ftyp',                          'video', '.mp4'),   # MP4/MOV/3GP generico
]


def _detect_media_type(path: str):
    """
    Legge i primi 32 byte del file per determinare il tipo media.
    Ritorna (media_type, estensione) o (None, None) se non riconosciuto.
    """
    try:
        with open(path, 'rb') as f:
            header = f.read(32)
        # Cerca il magic sia all'inizio sia a offset 4 (per box ftyp di HEIC/MP4)
        for magic, mtype, ext in _MAGIC:
            if header.startswith(magic):
                return mtype, ext
            if magic in header:
                return mtype, ext
    except OSError:
        pass
    return None, None


@dataclass
class MediaItem:
    """Rappresenta una singola foto o video da un backup iPhone."""
    file_id:       str
    relative_path: str
    domain:        str
    filename:      str
    extension:     str
    media_type:    str           # 'photo' o 'video'
    physical_path: str           # Percorso fisico nel backup
    size:          int = 0
    date_created:  Optional[datetime] = None
    date_modified: Optional[datetime] = None

    @property
    def is_video(self) -> bool:
        return self.media_type == 'video'

    @property
    def is_photo(self) -> bool:
        return self.media_type == 'photo'

    @property
    def size_str(self) -> str:
        s = self.size
        if s < 1024:          return f"{s} B"
        elif s < 1024 ** 2:   return f"{s / 1024:.1f} KB"
        elif s < 1024 ** 3:   return f"{s / 1024**2:.1f} MB"
        return f"{s / 1024**3:.2f} GB"

    @property
    def date_str(self) -> str:
        dt = self.date_modified or self.date_created
        if dt:
            return dt.strftime('%d %b %Y  %H:%M')
        return 'Data sconosciuta'


@dataclass
class DeviceInfo:
    """Informazioni sul dispositivo iPhone dal backup."""
    device_name:      str = 'iPhone'
    product_type:     str = ''
    ios_version:      str = ''
    serial_number:    str = ''
    last_backup_date: Optional[datetime] = None
    scan_mode:        str = 'itunes'   # 'itunes', 'snapshot', 'direct'

    def _get_model_name(self) -> str:
        pt = self.product_type
        if pt.startswith('iPhone17,'): return 'iPhone 16 series'
        if pt.startswith('iPhone16,'): return 'iPhone 15 series'
        if pt.startswith('iPhone15,'): return 'iPhone 14 series'
        if pt.startswith('iPhone14,'): return 'iPhone 13/14 series'
        if pt.startswith('iPhone13,'): return 'iPhone 12 series'
        if pt.startswith('iPhone12,'): return 'iPhone 11 series'
        if pt.startswith('iPhone11,'): return 'iPhone X/XS series'
        if pt.startswith('iPhone10,'): return 'iPhone 8/X series'
        if pt.startswith('iPhone'):    return 'iPhone'
        if pt.startswith('iPad'):      return 'iPad'
        return pt or 'Dispositivo sconosciuto'


class BackupReader:
    """
    Legge un backup iPhone in tre modalità (rilevazione automatica):
      - 'itunes'   : Manifest.db valido con dati
      - 'snapshot' : Manifest.db vuoto + cartella Snapshot/ (iOS 17+ / macOS Sonoma)
      - 'direct'   : Scansione ricorsiva di qualsiasi cartella con foto/video
    """

    def __init__(self, backup_path: str):
        self.backup_path  = backup_path
        self.manifest_db  = os.path.join(backup_path, 'Manifest.db')
        self.info_plist   = os.path.join(backup_path, 'Info.plist')
        self.status_plist = os.path.join(backup_path, 'Status.plist')
        self._snap_dir    = os.path.join(backup_path, 'Snapshot')

        # Rilevazione modalità
        mdb_size = os.path.getsize(self.manifest_db) \
                   if os.path.exists(self.manifest_db) else 0

        if mdb_size > 0:
            self.mode = 'itunes'
        elif os.path.isdir(self._snap_dir):
            self.mode = 'snapshot'
        else:
            self.mode = 'direct'

        self.is_itunes_backup = (self.mode == 'itunes')

    # ── Info dispositivo ──────────────────────────────────────────────────────

    def get_device_info(self) -> DeviceInfo:
        """Legge Info.plist (se disponibile) e restituisce info del dispositivo."""
        info = DeviceInfo()
        info.scan_mode = self.mode

        if self.mode == 'direct':
            info.device_name = os.path.basename(self.backup_path) or 'Backup Diretto'
            return info

        if self.mode == 'snapshot':
            info.device_name = 'iPhone (Snapshot)'
            # Prova a leggere Status.plist per la data
            if os.path.exists(self.status_plist):
                try:
                    with open(self.status_plist, 'rb') as f:
                        d = plistlib.load(f)
                    dt = d.get('Date')
                    if isinstance(dt, datetime):
                        info.last_backup_date = dt
                except Exception:
                    pass
            return info

        # Modalità iTunes
        if not os.path.exists(self.info_plist):
            return info
        try:
            with open(self.info_plist, 'rb') as f:
                d = plistlib.load(f)
            info.device_name   = d.get('Device Name', 'iPhone')
            info.product_type  = d.get('Product Type', '')
            info.ios_version   = d.get('Product Version', '')
            info.serial_number = d.get('Serial Number', '')
            lb = d.get('Last Backup Date')
            if isinstance(lb, datetime):
                info.last_backup_date = lb
        except Exception as e:
            print(f"[BackupReader] Avviso Info.plist: {e}")
        return info

    # ── File media ────────────────────────────────────────────────────────────

    def get_media_files(
        self,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> List[MediaItem]:
        """
        Restituisce tutti i media (foto + video) dal backup.
        Sceglie automaticamente la modalità in base a self.mode.
        """
        if self.mode == 'itunes':
            return self._scan_itunes(progress_callback)
        elif self.mode == 'snapshot':
            return self._scan_snapshot(progress_callback)
        else:
            return self._scan_direct(progress_callback)

    # ── Modalità 1: iTunes/Finder backup ─────────────────────────────────────

    def _scan_itunes(
        self,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> List[MediaItem]:
        """Legge Manifest.db e restituisce i file media mappati."""
        items: List[MediaItem] = []

        conn = sqlite3.connect(self.manifest_db)
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT fileID, domain, relativePath, flags, file
                FROM   Files
                WHERE  domain IN ('CameraRollDomain', 'MediaDomain')
                  AND  flags  = 1
                  AND  relativePath IS NOT NULL
                ORDER  BY relativePath
            """)
            rows = cur.fetchall()
            total = len(rows)

            for idx, (file_id, domain, rel_path, flags, blob) in enumerate(rows):
                if progress_callback and idx % 200 == 0:
                    progress_callback(idx, total)

                if not file_id or not rel_path:
                    continue
                if any(rel_path.startswith(p) for p in SKIP_PREFIXES):
                    continue
                if domain == 'CameraRollDomain' and not rel_path.startswith('Media/DCIM/'):
                    continue

                filename = os.path.basename(rel_path)
                if not filename or filename.startswith('.'):
                    continue

                ext = os.path.splitext(filename)[1].lower()
                if ext in PHOTO_EXTENSIONS:
                    mtype = 'photo'
                elif ext in VIDEO_EXTENSIONS:
                    mtype = 'video'
                else:
                    continue

                if len(file_id) < 2:
                    continue
                phys = os.path.join(self.backup_path, file_id[:2], file_id)
                if not os.path.exists(phys):
                    continue

                try:
                    size = os.path.getsize(phys)
                except OSError:
                    size = 0

                date_c, date_m = self._parse_blob(blob)

                items.append(MediaItem(
                    file_id=file_id,
                    relative_path=rel_path,
                    domain=domain,
                    filename=filename,
                    extension=ext,
                    media_type=mtype,
                    physical_path=phys,
                    size=size,
                    date_created=date_c,
                    date_modified=date_m,
                ))

        finally:
            conn.close()

        items.sort(
            key=lambda x: (x.date_modified or x.date_created or datetime.min),
            reverse=True,
        )
        return items

    # ── Modalità 2: Snapshot (iOS 17+ / macOS Sonoma) ─────────────────────────

    def _scan_snapshot(
        self,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> List[MediaItem]:
        """
        Scansiona la cartella Snapshot/ cercando file media hashed senza estensione.
        Il tipo viene determinato leggendo i magic bytes del file.
        Salta i PNG 300x300 (icone app) rilevabili dalla dimensione ~<500KB con
        magic PNG — in realtà includiamo tutto: l'utente vedrà anche icone,
        ma meglio troppo che niente.
        """
        items: List[MediaItem] = []

        # Raccoglie tutti i file nella Snapshot (non ricorsiva: max 2 livelli xx/hash)
        all_files = []
        try:
            for prefix_dir in os.listdir(self._snap_dir):
                prefix_path = os.path.join(self._snap_dir, prefix_dir)
                if not os.path.isdir(prefix_path) or len(prefix_dir) != 2:
                    continue
                for fname in os.listdir(prefix_path):
                    fpath = os.path.join(prefix_path, fname)
                    if os.path.isfile(fpath):
                        all_files.append(fpath)
        except OSError:
            pass

        total = len(all_files)

        for idx, phys in enumerate(all_files):
            if progress_callback and idx % 50 == 0:
                progress_callback(idx, total)

            try:
                stat = os.stat(phys)
                size = stat.st_size
                date_m = datetime.fromtimestamp(stat.st_mtime)
                date_c = datetime.fromtimestamp(stat.st_birthtime) \
                         if hasattr(stat, 'st_birthtime') else date_m
            except OSError:
                continue

            # Salta file troppo piccoli (sicuramente non foto/video originali)
            if size < 50_000:   # < 50 KB → skip
                continue

            mtype, ext = _detect_media_type(phys)
            if mtype is None:
                continue

            fname   = os.path.basename(phys)
            rel     = os.path.relpath(phys, self.backup_path)
            # Usa come filename il nome hashed + estensione rilevata
            display = fname + ext

            items.append(MediaItem(
                file_id=fname,
                relative_path=rel,
                domain='Snapshot',
                filename=display,
                extension=ext,
                media_type=mtype,
                physical_path=phys,
                size=size,
                date_created=date_c,
                date_modified=date_m,
            ))

        items.sort(
            key=lambda x: (x.date_modified or x.date_created or datetime.min),
            reverse=True,
        )
        return items

    # ── Modalità 3: Scansione diretta ─────────────────────────────────────────

    def _scan_direct(
        self,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> List[MediaItem]:
        """
        Scansiona ricorsivamente la cartella cercando tutti i file
        foto/video per estensione. Utile per backup manuali, copie DCIM, ecc.
        """
        items: List[MediaItem] = []

        all_files = []
        for root, dirs, files in os.walk(self.backup_path, followlinks=False):
            dirs[:] = [d for d in dirs
                       if d not in SKIP_DIRS and not d.startswith('.')]
            for fname in files:
                if fname.startswith('.'):
                    continue
                ext = os.path.splitext(fname)[1].lower()
                if ext in PHOTO_EXTENSIONS or ext in VIDEO_EXTENSIONS:
                    all_files.append(os.path.join(root, fname))

        total = len(all_files)

        for idx, phys in enumerate(all_files):
            if progress_callback and idx % 100 == 0:
                progress_callback(idx, total)

            fname = os.path.basename(phys)
            ext   = os.path.splitext(fname)[1].lower()
            mtype = 'photo' if ext in PHOTO_EXTENSIONS else 'video'

            try:
                stat   = os.stat(phys)
                size   = stat.st_size
                date_m = datetime.fromtimestamp(stat.st_mtime)
                date_c = datetime.fromtimestamp(stat.st_birthtime) \
                         if hasattr(stat, 'st_birthtime') else date_m
            except OSError:
                size = 0
                date_c = date_m = None

            if size < 10_240:
                continue

            rel_path = os.path.relpath(phys, self.backup_path)
            file_id  = rel_path.replace(os.sep, '_')

            items.append(MediaItem(
                file_id=file_id,
                relative_path=rel_path,
                domain='DirectScan',
                filename=fname,
                extension=ext,
                media_type=mtype,
                physical_path=phys,
                size=size,
                date_created=date_c,
                date_modified=date_m,
            ))

        items.sort(
            key=lambda x: (x.date_modified or x.date_created or datetime.min),
            reverse=True,
        )
        return items

    # ── Parsing metadata blob iTunes ──────────────────────────────────────────

    def _parse_blob(self, blob) -> tuple:
        """Estrai date di creazione e modifica dal blob plist di Manifest.db."""
        date_c = date_m = None
        if not blob:
            return date_c, date_m
        try:
            pdata   = plistlib.loads(bytes(blob))
            objects = pdata.get('$objects', [])
            for obj in objects:
                if not isinstance(obj, dict):
                    continue
                if 'Birth' in obj:
                    ts = obj['Birth']
                    if isinstance(ts, (int, float)) and ts > 0:
                        try:
                            date_c = datetime.fromtimestamp(ts + MAC_EPOCH_OFFSET)
                        except (OSError, OverflowError, ValueError):
                            pass
                if 'LastModified' in obj:
                    ts = obj['LastModified']
                    if isinstance(ts, (int, float)) and ts > 0:
                        try:
                            date_m = datetime.fromtimestamp(ts + MAC_EPOCH_OFFSET)
                        except (OSError, OverflowError, ValueError):
                            pass
        except Exception:
            pass
        return date_c, date_m

    # ── Utility statica ───────────────────────────────────────────────────────

    @staticmethod
    def find_local_backups() -> List[dict]:
        """Trova backup iPhone nella directory standard di macOS."""
        base = os.path.expanduser(
            '~/Library/Application Support/MobileSync/Backup'
        )
        result = []
        if os.path.isdir(base):
            for folder in os.listdir(base):
                fp = os.path.join(base, folder)
                if os.path.isfile(os.path.join(fp, 'Manifest.db')):
                    result.append({'path': fp, 'id': folder})
        return result
