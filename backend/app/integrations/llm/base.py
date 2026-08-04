"""Vertrag für Vision-Modelle.

Ein Protocol, damit der Wechsel von OpenAI zu Ollama eine neue Implementierung
ist und keine Änderung am Aufrufer. Die Adapter geben **rohen Text** zurück —
das Interpretieren übernimmt `domain/extraction`, damit es ohne Modell testbar
bleibt.
"""

from __future__ import annotations

from typing import Protocol


class VisionModel(Protocol):
    """Bild + Prompt rein, Modelltext raus."""

    @property
    def name(self) -> str:
        """Für Logs: welcher Provider/Modell hat geantwortet."""
        ...

    @property
    def available(self) -> bool:
        """`False` = nicht konfiguriert; der Aufrufer geht dann auf manuelle Erfassung."""
        ...

    async def extract(self, *, image: bytes, media_type: str, prompt: str) -> str | None:
        """Rohe Modellantwort, oder `None`, wenn kein Modell verfügbar ist."""
        ...


class LlmError(RuntimeError):
    """Der Provider hat einen Fehler gemeldet (Netz, Auth, Kontingent, Format)."""
