"""Pure upload helpers — magic-byte sniffing, no I/O.

We trust the file's own bytes over the client-supplied Content-Type, so a
mislabeled or spoofed upload is rejected before it ever hits storage or the
vision LLM.
"""

# media type -> file extension used for the server-generated filename
EXTENSION = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}


def detect_media_type(data: bytes) -> str | None:
    """Return the media type inferred from the leading bytes, or None if the
    content is not a supported receipt format (JPEG/PNG/WebP/PDF)."""
    if len(data) < 12:
        return None
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:5] == b"%PDF-":
        return "application/pdf"
    return None
