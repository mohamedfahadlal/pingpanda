"""The data that PingPanda keeps about a checked URL."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class UrlResult:
    """Everything the tool knows about a single checked URL."""

    url_id: int
    url: str
    status: int | None
    elapsed: float  # seconds
    redirect_to: str | None
    ip_port: str
    redirect_ip_port: str | None
    attempts: int = 1

    @property
    def status_label(self) -> str:
        return "Invalid" if self.status is None else str(self.status)
