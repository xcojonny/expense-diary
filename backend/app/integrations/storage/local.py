from pathlib import Path

from uuid6 import uuid7

from app.core.config import get_settings


class LocalStorage:
    """Stores uploaded receipt files on the local filesystem under MEDIA_DIR.

    Filenames are server-generated (uuid7 + extension) so a client can never
    influence the path; the returned value is relative to MEDIA_DIR and goes
    into ``Receipt.image_path``.
    """

    def __init__(self, base_dir: str | None = None) -> None:
        self.base = Path(base_dir or get_settings().media_dir)

    def save(self, data: bytes, extension: str) -> str:
        self.base.mkdir(parents=True, exist_ok=True)
        name = f"{uuid7().hex}{extension}"
        (self.base / name).write_bytes(data)
        return name

    def read(self, rel_path: str) -> bytes:
        return (self.base / rel_path).read_bytes()

    def delete(self, rel_path: str) -> None:
        (self.base / rel_path).unlink(missing_ok=True)


def get_storage() -> LocalStorage:
    return LocalStorage()
