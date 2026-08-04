"""Dateiablage und Typerkennung.

Der Client-`Content-Type` wird bewusst ignoriert: der Typ kommt aus den
**Magic Bytes**. Dateinamen erzeugt der Server (`secrets.token_hex`), damit
weder der Client-Name noch ein erratbarer Pfad in die Ablage gelangt (ADR-008).
"""

from __future__ import annotations

import secrets
from datetime import datetime
from pathlib import Path

import anyio

JPEG = "image/jpeg"
PNG = "image/png"
WEBP = "image/webp"
HEIC = "image/heic"
PDF = "application/pdf"

SUPPORTED_MEDIA_TYPES = (JPEG, PNG, WEBP, HEIC, PDF)

_EXTENSIONS = {JPEG: ".jpg", PNG: ".png", WEBP: ".webp", HEIC: ".heic", PDF: ".pdf"}


class UnsupportedFileError(ValueError):
    """Die Datei ist kein unterstützter Bild- oder PDF-Typ."""


def detect_media_type(data: bytes) -> str | None:
    """Medientyp aus den Magic Bytes bestimmen (`None` = unbekannt)."""
    if data.startswith(b"\xff\xd8\xff"):
        return JPEG
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return WEBP
    if data.startswith(b"%PDF-"):
        return PDF
    # HEIC/HEIF: ISO-BMFF-Box "ftyp" mit passender Marke — das ist, was ein
    # iPhone standardmäßig liefert.
    if data[4:8] == b"ftyp" and data[8:12] in (
        b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1",
    ):
        return HEIC
    return None


def extension_for(media_type: str) -> str:
    return _EXTENSIONS.get(media_type, ".bin")


class FileStore:
    """Belege unter `MEDIA_DIR/JJJJ/MM/<zufall>.<ext>`.

    Die Monatsordner halten das Verzeichnis übersichtlich; der relative Pfad
    landet am Bon.
    """

    def __init__(self, root: Path) -> None:
        self._root = root

    async def save(self, data: bytes, media_type: str, *, when: datetime | None = None) -> str:
        stamp = when or datetime.now()
        folder = self._root / f"{stamp:%Y}" / f"{stamp:%m}"
        await anyio.to_thread.run_sync(lambda: folder.mkdir(parents=True, exist_ok=True))

        name = f"{secrets.token_hex(16)}{extension_for(media_type)}"
        target = folder / name
        await anyio.Path(target).write_bytes(data)
        return target.relative_to(self._root).as_posix()

    async def read(self, relative_path: str) -> bytes:
        return await anyio.Path(self._resolve(relative_path)).read_bytes()

    async def delete(self, relative_path: str) -> None:
        path = anyio.Path(self._resolve(relative_path))
        if await path.exists():
            await path.unlink()

    def _resolve(self, relative_path: str) -> Path:
        """Pfad auflösen und im Wurzelverzeichnis verankern (kein `../`-Ausbruch)."""
        target = (self._root / relative_path).resolve()
        root = self._root.resolve()
        if not target.is_relative_to(root):
            raise UnsupportedFileError("Pfad liegt außerhalb der Ablage")
        return target
