"""
media_manager.py — Gestione Thumbnail e Preview per BackupManager
Genera e memorizza nella cache le anteprime di foto (HEIC, JPG, PNG…)
e video (MP4, MOV…). Usa Pillow, pillow-heif e OpenCV/ffmpeg.
"""

import os
import subprocess
import threading
from typing import Optional
from PIL import Image, ImageDraw, ImageOps

# Cache su disco
CACHE_DIR = os.path.expanduser('~/.BackupManager/thumb_cache')

# Supporto HEIC/HEIF via pillow-heif
HEIC_SUPPORT = False
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIC_SUPPORT = True
except ImportError:
    pass

# Supporto video via OpenCV
CV2_AVAILABLE = False
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    pass


class MediaManager:
    """
    Genera e mette in cache le anteprime dei file media.
    Thread-safe: può essere chiamato da più thread contemporaneamente.
    """

    def __init__(self):
        os.makedirs(CACHE_DIR, exist_ok=True)
        self._mem: dict = {}      # cache_key → PIL Image
        self._lock = threading.Lock()

    # ── API pubblica ──────────────────────────────────────────────────────────

    def get_thumbnail(self, item, size: tuple = (180, 180)) -> Optional[Image.Image]:
        """
        Restituisce la miniatura per un MediaItem.
        Usa la cache (memoria poi disco), genera se necessario.
        """
        key = f"{item.file_id}_{size[0]}"

        # Cache in memoria
        with self._lock:
            if key in self._mem:
                return self._mem[key]

        # Cache su disco
        disk = os.path.join(CACHE_DIR, f"{key}.jpg")
        if os.path.exists(disk):
            try:
                img = Image.open(disk).convert('RGB')
                img.load()
                with self._lock:
                    self._mem[key] = img
                return img
            except Exception:
                try:
                    os.unlink(disk)
                except OSError:
                    pass

        # Genera
        img = (self._photo_thumb(item.physical_path, size)
               if item.is_photo
               else self._video_thumb(item.physical_path, size))

        if img is None:
            img = self._placeholder(size, item.extension)

        img = self._fit_crop(img, size)

        # Salva su disco
        try:
            img.save(disk, 'JPEG', quality=85, optimize=True)
        except Exception:
            pass

        with self._lock:
            self._mem[key] = img
        return img

    def get_full_image(self, item, max_size: tuple = (4096, 4096)) -> Optional[Image.Image]:
        """Carica la foto/video a piena risoluzione per il viewer."""
        if item.is_photo:
            return self._load_photo_full(item.physical_path, max_size)
        return self._video_frame(item.physical_path, 0)

    def clear_memory_cache(self):
        with self._lock:
            self._mem.clear()

    def clear_disk_cache(self):
        """Cancella tutte le anteprime su disco."""
        for f in os.listdir(CACHE_DIR):
            try:
                os.unlink(os.path.join(CACHE_DIR, f))
            except OSError:
                pass
        self.clear_memory_cache()

    def get_cache_size_str(self) -> str:
        total = sum(
            os.path.getsize(os.path.join(CACHE_DIR, f))
            for f in os.listdir(CACHE_DIR)
            if os.path.isfile(os.path.join(CACHE_DIR, f))
        )
        return f"{total / 1024**2:.1f} MB"

    # ── Foto ──────────────────────────────────────────────────────────────────

    def _photo_thumb(self, path: str, size: tuple) -> Optional[Image.Image]:
        try:
            with Image.open(path) as img:
                img = ImageOps.exif_transpose(img).convert('RGB')
                img.thumbnail(size, Image.BILINEAR)   # 3x più veloce di LANCZOS
                return img.copy()
        except Exception:
            pass
        return self._sips_thumb(path, size)

    def _sips_thumb(self, path: str, size: tuple) -> Optional[Image.Image]:
        import tempfile
        try:
            tmp = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
            tmp.close()
            r = subprocess.run(
                ['sips', '-s', 'format', 'jpeg',
                 '-z', str(size[1]), str(size[0]),
                 path, '--out', tmp.name],
                capture_output=True, timeout=15
            )
            if r.returncode == 0 and os.path.exists(tmp.name):
                img = Image.open(tmp.name).convert('RGB')
                img.load()
                os.unlink(tmp.name)
                return img
        except Exception:
            pass
        return None

    def _load_photo_full(self, path: str, max_size: tuple) -> Optional[Image.Image]:
        try:
            img = Image.open(path)
            img = ImageOps.exif_transpose(img).convert('RGB')
            if img.width > max_size[0] or img.height > max_size[1]:
                img.thumbnail(max_size, Image.LANCZOS)
            return img
        except Exception:
            pass
        # Fallback sips → piena qualità
        import tempfile
        try:
            tmp = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
            tmp.close()
            subprocess.run(
                ['sips', '-s', 'format', 'jpeg',
                 '-s', 'formatOptions', 'best',
                 path, '--out', tmp.name],
                capture_output=True, timeout=30
            )
            img = Image.open(tmp.name).convert('RGB')
            img.load()
            os.unlink(tmp.name)
            return img
        except Exception:
            return None

    # ── Video ─────────────────────────────────────────────────────────────────

    def _video_thumb(self, path: str, size: tuple) -> Optional[Image.Image]:
        if CV2_AVAILABLE:
            img = self._cv2_thumb(path, size)
            if img:
                return img
        return self._ffmpeg_thumb(path, size)

    def _cv2_thumb(self, path: str, size: tuple) -> Optional[Image.Image]:
        try:
            cap = cv2.VideoCapture(path)
            if not cap.isOpened():
                return None
            total = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            seek  = min(int(total * 0.1), 60)
            cap.set(cv2.CAP_PROP_POS_FRAMES, seek)
            ret, frame = cap.read()
            cap.release()
            if ret:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(rgb)
                img.thumbnail(size, Image.LANCZOS)
                return img
        except Exception:
            pass
        return None

    def _ffmpeg_thumb(self, path: str, size: tuple) -> Optional[Image.Image]:
        import tempfile
        try:
            tmp = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
            tmp.close()
            r = subprocess.run([
                'ffmpeg', '-i', path, '-ss', '00:00:01', '-vframes', '1',
                '-vf', f'scale={size[0]}:{size[1]}:force_original_aspect_ratio=decrease',
                '-y', tmp.name
            ], capture_output=True, timeout=20)
            if r.returncode == 0 and os.path.getsize(tmp.name) > 0:
                img = Image.open(tmp.name).convert('RGB')
                img.load()
                os.unlink(tmp.name)
                return img
        except Exception:
            pass
        return None

    def _video_frame(self, path: str, frame_num: int) -> Optional[Image.Image]:
        """Carica un frame specifico dal video."""
        if CV2_AVAILABLE:
            try:
                cap = cv2.VideoCapture(path)
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                ret, frame = cap.read()
                cap.release()
                if ret:
                    return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            except Exception:
                pass
        return None

    # ── Utility ───────────────────────────────────────────────────────────────

    def _fit_crop(self, img: Image.Image, size: tuple) -> Image.Image:
        """Ridimensiona e ritaglia al centro. BILINEAR per velocità."""
        tw, th = size
        iw, ih = img.size
        scale = max(tw / iw, th / ih)
        nw = max(1, int(iw * scale))
        nh = max(1, int(ih * scale))
        img = img.resize((nw, nh), Image.BILINEAR)
        left = (nw - tw) // 2
        top  = (nh - th) // 2
        return img.crop((left, top, left + tw, top + th))

    def _placeholder(self, size: tuple, ext: str) -> Image.Image:
        """Genera una miniatura segnaposto per i file non caricati."""
        img  = Image.new('RGB', size, (44, 44, 46))
        draw = ImageDraw.Draw(img)
        text = ext.upper().lstrip('.')[:4]
        # Testo centrato
        try:
            bbox = draw.textbbox((0, 0), text)
            tw   = bbox[2] - bbox[0]
            th   = bbox[3] - bbox[1]
        except AttributeError:
            tw, th = len(text) * 8, 14
        draw.text(
            ((size[0] - tw) // 2, (size[1] - th) // 2),
            text, fill=(100, 100, 110)
        )
        return img
