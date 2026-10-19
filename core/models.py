from dataclasses import dataclass, field
from datetime import datetime, timezone

@dataclass(frozen=True)
class Job:
    """Immutable domain model representing a normalized job posting."""
    source: str
    id: str
    title: str
    url: str
    org: str = "Unknown"
    location: str = "Unknown"
    wage: str = "Undisclosed"
    closing: str = ""
    details: str = ""
    score: int = 0
    matched_keywords: tuple[str, ...] = field(default_factory=tuple)
    scraped_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def composite_key(self) -> str:
        """Globally unique identity across all heterogeneous sources."""
        return f"{self.source}::{self.id}"