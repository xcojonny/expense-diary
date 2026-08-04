"""Kein Modell konfiguriert — der Default.

Wichtig für das Versprechen „ohne LLM voll bedienbar": eBon-PDFs laufen weiter
über den Textparser, Fotos landen in `needs_review` und werden manuell erfasst.
Die App ist nie unbenutzbar, nur weil kein Modell hinterlegt ist.
"""

from __future__ import annotations


class NullVisionModel:
    name = "none"
    available = False

    async def extract(self, *, image: bytes, media_type: str, prompt: str) -> str | None:
        return None
