"""Domain module - Represents an app or website domain.

Domain represents the main page/homepage of an app or website. It acts as a
central node that connects to all States (pages/screens) within that app/website
through Manage edges.
"""

import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator


def normalize_domain_url(domain_url: str, domain_type: Optional[str] = None) -> str:
    """Normalize domain_url for consistent deduplication.

    - Website: extract host, lower, strip www., drop default ports.
    - App: lower + strip.
    """
    if not isinstance(domain_url, str):
        return domain_url

    raw = domain_url.strip()
    if not raw:
        return raw

    if isinstance(domain_type, str) and domain_type.lower() == "app":
        return raw.lower()

    host = ""
    port = None
    try:
        parsed = urlparse(raw if "://" in raw else f"http://{raw}")
        host = parsed.hostname or ""
        port = parsed.port
    except Exception:
        host = ""
        port = None

    if not host:
        host = raw.split("/")[0]
        host = host.split("?")[0].split("#")[0]

    host = host.lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]

    if port and port not in (80, 443):
        host = f"{host}:{port}"

    return host


class Domain(BaseModel):
    """Domain - Represents an app or website domain (main page/homepage).

    A Domain represents the main page or homepage of an app or website. It serves
    as a central hub node in the memory graph, connecting to all State nodes that
    belong to this app/website through Manage edges.

    Key Concept:
        - One Domain = One App or Website (identified by domain URL or app ID)
        - Domain connects to multiple States (all pages/screens in that app/website)
        - Manage edges store visit metadata (timestamps, visit counts, etc.)

    Attributes:
        id: Unique domain identifier (auto-generated if not provided).
        domain_url: Domain URL (e.g., "example.com") or app identifier (e.g., "com.app.name").
        domain_name: Human-readable name of the domain/app (optional).
        domain_type: Type of domain - "website" or "app" (default: "website").
        created_at: When this domain was first discovered (milliseconds, optional).
        updated_at: When this domain was last updated (milliseconds, optional).
        user_id: User ID (optional).
        attributes: Additional metadata.
    """

    # Core identifiers
    id: Optional[str] = Field(
        default=None,
        description="Unique domain identifier"
    )

    # Domain information (REQUIRED - identifies the app/website)
    domain_url: str = Field(
        ...,
        description="Domain URL (e.g., 'example.com') or app identifier (e.g., 'com.app.name')"
    )
    domain_name: Optional[str] = Field(
        default=None,
        description="Human-readable name of the domain/app"
    )
    domain_type: str = Field(
        default="website",
        description="Type of domain: 'website' or 'app'"
    )

    # Time information
    created_at: Optional[int] = Field(
        default=None,
        description="When this domain was first discovered (milliseconds)"
    )
    updated_at: Optional[int] = Field(
        default=None,
        description="When this domain was last updated (milliseconds)"
    )

    # User information
    user_id: Optional[str] = Field(default=None, description="User ID")

    # Additional metadata
    attributes: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata"
    )

    @model_validator(mode="before")
    @classmethod
    def generate_id(cls, data: Any) -> Any:
        """Normalize domain_url and auto-generate ID if not provided.

        Args:
            data: Input data dictionary.

        Returns:
            Data with ID generated if missing.
        """
        if isinstance(data, dict):
            domain_url = data.get("domain_url")
            if domain_url:
                domain_type = data.get("domain_type") or "website"
                normalized = normalize_domain_url(domain_url, domain_type)
                if normalized:
                    data["domain_url"] = normalized
                    if not data.get("id"):
                        data["id"] = normalized
            elif not data.get("id"):
                data["id"] = str(uuid.uuid4())
        return data

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation of the domain.
        """
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Domain":
        """Create instance from dictionary.

        Args:
            data: Dictionary containing domain data.

        Returns:
            Domain instance.
        """
        return cls(**data)


class Manage(BaseModel):
    """Manage - Edge connecting Domain to State (tracks visit information).

    A Manage edge connects a Domain node to a State node, representing that
    the State (page/screen) belongs to this Domain (app/website). The edge
    stores visit metadata such as visit timestamps, visit counts, and other
    tracking information.

    Key Concept:
        - One Manage edge = Domain manages/contains a State
        - Edge direction: Domain -> State
        - Stores visit metadata on the edge (visit times, counts, etc.)

    Attributes:
        domain_id: Domain ID (source of the edge).
        state_id: State ID (target of the edge).
        first_visit: First visit timestamp (milliseconds, optional).
        last_visit: Last visit timestamp (milliseconds, optional).
        visit_count: Number of times this state was visited (default: 0).
        visit_timestamps: List of all visit timestamps (optional).
        total_duration: Total time spent on this state (milliseconds, optional).
        user_id: User ID (optional).
        attributes: Additional metadata.
    """

    # Core relationship (REQUIRED - defines the edge)
    domain_id: str = Field(..., description="Domain ID (source)")
    state_id: str = Field(..., description="State ID (target)")

    # Visit tracking information
    first_visit: Optional[int] = Field(
        default=None,
        description="First visit timestamp (milliseconds)"
    )
    last_visit: Optional[int] = Field(
        default=None,
        description="Last visit timestamp (milliseconds)"
    )
    visit_count: int = Field(
        default=0,
        description="Number of times this state was visited"
    )
    visit_timestamps: Optional[List[int]] = Field(
        default=None,
        description="List of all visit timestamps"
    )
    total_duration: Optional[int] = Field(
        default=None,
        description="Total time spent on this state (milliseconds)"
    )

    # User information
    user_id: Optional[str] = Field(default=None, description="User ID")

    # Additional metadata
    attributes: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata"
    )

    @model_validator(mode='after')
    def validate_visit_data(self) -> 'Manage':
        """Validate visit data consistency.

        Returns:
            Self if validation passes.

        Raises:
            ValueError: If visit data is inconsistent.
        """
        # If visit_timestamps is provided, validate visit_count
        if self.visit_timestamps is not None:
            if self.visit_count > 0 and len(self.visit_timestamps) != self.visit_count:
                raise ValueError(
                    f"visit_count ({self.visit_count}) does not match "
                    f"length of visit_timestamps ({len(self.visit_timestamps)})"
                )

        # If first_visit and last_visit are both set, validate order
        if self.first_visit is not None and self.last_visit is not None:
            if self.first_visit > self.last_visit:
                raise ValueError(
                    f"first_visit ({self.first_visit}) cannot be later than "
                    f"last_visit ({self.last_visit})"
                )

        return self

    def add_visit(self, timestamp: int, duration: Optional[int] = None) -> None:
        """Add a new visit record.

        Args:
            timestamp: Visit timestamp in milliseconds.
            duration: Duration of this visit (milliseconds, optional).
        """
        # Update first_visit if not set or if this is earlier
        if self.first_visit is None or timestamp < self.first_visit:
            self.first_visit = timestamp

        # Update last_visit if not set or if this is later
        if self.last_visit is None or timestamp > self.last_visit:
            self.last_visit = timestamp

        # Increment visit count
        self.visit_count += 1

        # Add to visit_timestamps list
        if self.visit_timestamps is None:
            self.visit_timestamps = []
        self.visit_timestamps.append(timestamp)

        # Update total_duration if duration is provided
        if duration is not None:
            if self.total_duration is None:
                self.total_duration = 0
            self.total_duration += duration

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation of the manage edge.
        """
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Manage":
        """Create instance from dictionary.

        Args:
            data: Dictionary containing manage edge data.

        Returns:
            Manage instance.

        Raises:
            ValueError: If validation fails.
        """
        return cls(**data)


__all__ = [
    "Domain",
    "Manage",
    "normalize_domain_url",
]
