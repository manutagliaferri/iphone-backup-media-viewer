"""
export_utils.py — Esportazione file media senza perdita di qualità
Copia diretta del file originale (nessuna ri-codifica).
Opzione conversione HEIC → JPEG con qualità massima.
"""

import os
import shutil
import subprocess
from typing import List, Optional, Callable


class ExportManager:
    """Gestisce l'esportazione di file media da backup iPhone."""

    def export_items(
        self,
        items: list,
        destination: str,
        convert_heic: bool = False,
        preserve_dates: bool = True,
        rename_with_date: bool = False,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> dict:
        """
        Esporta una lista di MediaItem nella cartella di destinazione.

        Modalità default: copia lossless (nessuna ri-codifica, qualità originale).

        Args:
            items:             Lista di MediaItem da esportare
            destination:       Cartella di destinazione
            convert_heic:      Se True, converte HEIC→JPEG via sips
            preserve_dates:    Ripristina i timestamp originali del file
            rename_with_date:  Prefissa il nome con la data (YYYY-MM-DD_)
            progress_callback: callable(current, total, filename)

        Returns:
            Dict con chiavi 'success', 'failed', 'skipped', 'errors'
        """
        os.makedirs(destination, exist_ok=True)

        results = {'success': 0, 'failed': 0, 'skipped': 0, 'errors': []}

        for i, item in enumerate(items):
            if progress_callback:
                progress_callback(i + 1, len(items), item.filename)

            try:
                self._export_one(
                    item, destination,
                    convert_heic=convert_heic,
                    preserve_dates=preserve_dates,
                    rename_with_date=rename_with_date,
                    results=results,
                )
            except Exception as e:
                results['failed'] += 1
                results['errors'].append(f"{item.filename}: {e}")

        return results

    # ── Implementazione ───────────────────────────────────────────────────────

    def _export_one(self, item, dest: str, convert_heic: bool,
                    preserve_dates: bool, rename_with_date: bool, results: dict):
        name = item.filename

        if rename_with_date and (item.date_modified or item.date_created):
            dt = item.date_modified or item.date_created
            name = dt.strftime('%Y-%m-%d_') + name

        if convert_heic and item.extension in ('.heic', '.heif'):
            # Converti HEIC → JPEG con qualità massima
            out_name = os.path.splitext(name)[0] + '.jpg'
            out_path = self._unique(dest, out_name)
            self._heic_to_jpeg(item.physical_path, out_path)
        else:
            # Copia 1:1 senza alcuna modifica (lossless)
            out_path = self._unique(dest, name)
            shutil.copy2(item.physical_path, out_path)  # copy2 preserva metadati

        # Ripristina timestamp originale
        if preserve_dates:
            self._set_time(out_path, item)

        results['success'] += 1

    def _heic_to_jpeg(self, src: str, dst: str):
        """Converte HEIC in JPEG usando sips (massima qualità)."""
        r = subprocess.run(
            ['sips', '-s', 'format', 'jpeg',
             '-s', 'formatOptions', 'best',
             src, '--out', dst],
            capture_output=True, timeout=60
        )
        if r.returncode != 0 or not os.path.exists(dst):
            # Fallback Pillow
            from PIL import Image, ImageOps
            with Image.open(src) as img:
                img = ImageOps.exif_transpose(img)
                img.save(dst, 'JPEG', quality=100, subsampling=0)

    def _set_time(self, path: str, item):
        """Imposta i timestamp del file esportato ai valori originali."""
        dt = item.date_modified or item.date_created
        if dt:
            try:
                ts = dt.timestamp()
                os.utime(path, (ts, ts))
            except OSError:
                pass

    def _unique(self, directory: str, filename: str) -> str:
        """Genera un percorso file unico per evitare sovrascritture."""
        dest = os.path.join(directory, filename)
        if not os.path.exists(dest):
            return dest
        name, ext = os.path.splitext(filename)
        n = 1
        while os.path.exists(dest):
            dest = os.path.join(directory, f"{name}_{n}{ext}")
            n += 1
        return dest
