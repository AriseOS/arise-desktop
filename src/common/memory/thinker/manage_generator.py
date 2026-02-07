"""Manage Generator - Generates Domain-State connections (Manage edges).

This module creates Manage edges that connect Domains to States, tracking visit information.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from src.common.memory.ontology.domain import Domain, Manage, normalize_domain_url
from src.common.memory.ontology.state import State

logger = logging.getLogger(__name__)


class ManageGenerationResult:
    """Result of manage edge generation.

    Attributes:
        manages: List of generated Manage objects
        domain_state_map: Mapping from (domain_id, state_id) to Manage
        generation_metadata: Metadata about generation
        timestamp: When generation was performed
    """

    def __init__(
        self,
        manages: List[Manage],
        domain_state_map: Dict[tuple, Manage],
        generation_metadata: Dict[str, Any]
    ):
        """Initialize generation result.

        Args:
            manages: List of Manage objects
            domain_state_map: (domain_id, state_id) to Manage mapping
            generation_metadata: Generation metadata
        """
        self.manages = manages
        self.domain_state_map = domain_state_map
        self.generation_metadata = generation_metadata
        self.timestamp = datetime.now()


class ManageGenerator:
    """Generator for creating Manage edges connecting Domains to States.

    Creates Manage edges that:
    - Connect each Domain to all States belonging to that domain
    - Track visit information (timestamps, counts, duration)
    - Aggregate visit data across multiple visits to the same state
    """

    def __init__(self):
        """Initialize ManageGenerator."""
        pass

    def generate_manages(
        self,
        domains: List[Domain],
        states: List[State]
    ) -> ManageGenerationResult:
        """Generate Manage edges connecting domains to states.

        Args:
            domains: List of Domain objects
            states: List of State objects

        Returns:
            ManageGenerationResult containing generated manages

        Raises:
            ValueError: If input is invalid
        """
        if not domains:
            raise ValueError("Domains list is empty")

        if not states:
            raise ValueError("States list is empty")

        manages = []
        domain_state_map = {}  # (domain_id, state_id) -> Manage

        # Build domain URL mapping for quick lookup
        domain_url_map = self._build_domain_url_map(domains)

        # Process each state
        for state in states:
            # Find matching domain for this state
            domain = self._find_domain_for_state(state, domain_url_map)

            if not domain:
                logger.warning(f" No domain found for state {state.page_url}")
                continue

            # Create or update Manage edge
            key = (domain.id, state.id)

            if key not in domain_state_map:
                # Create new Manage edge
                manage = Manage(
                    domain_id=domain.id,
                    state_id=state.id,
                    first_visit=state.timestamp,
                    last_visit=state.end_timestamp or state.timestamp,
                    visit_count=1,
                    visit_timestamps=[state.timestamp],
                    total_duration=state.duration or 0,
                    attributes={
                        "domain_url": domain.domain_url,
                        "state_url": state.page_url
                    }
                )
                manages.append(manage)
                domain_state_map[key] = manage

            else:
                # Update existing Manage edge (multiple visits to same state)
                manage = domain_state_map[key]
                manage.add_visit(
                    timestamp=state.timestamp,
                    duration=state.duration
                )

        # Generate metadata
        metadata = {
            "generation_method": "rule_based",
            "manage_count": len(manages),
            "domain_count": len(domains),
            "state_count": len(states),
            "unique_domain_state_pairs": len(domain_state_map),
            "avg_states_per_domain": len(states) / len(domains) if domains else 0
        }

        return ManageGenerationResult(
            manages=manages,
            domain_state_map=domain_state_map,
            generation_metadata=metadata
        )

    def _build_domain_url_map(
        self,
        domains: List[Domain]
    ) -> Dict[str, Domain]:
        """Build mapping from URLs to domains.

        Args:
            domains: List of Domain objects

        Returns:
            Dictionary mapping URLs/domain strings to Domain objects
        """
        url_map = {}

        for domain in domains:
            # Map domain_url
            domain_url = normalize_domain_url(domain.domain_url, domain.domain_type)
            if not domain_url:
                continue
            url_map[domain_url] = domain

            # Also map common variations
            # Add variations (with/without www, etc.)
            variations = [
                domain_url,
                f"www.{domain_url}",
                domain_url.replace("www.", ""),
            ]

            for var in variations:
                url_map[var] = domain

        return url_map

    def _find_domain_for_state(
        self,
        state: State,
        domain_url_map: Dict[str, Domain]
    ) -> Optional[Domain]:
        """Find the domain that this state belongs to.

        Args:
            state: State object
            domain_url_map: URL to Domain mapping

        Returns:
            Domain object if found, None otherwise
        """
        page_url = state.page_url

        # Prefer explicit state domain if available
        if state.domain:
            domain_key = normalize_domain_url(state.domain)
            if domain_key in domain_url_map:
                return domain_url_map[domain_key]

        # Try exact match first
        if page_url in domain_url_map:
            return domain_url_map[page_url]

        # Try to extract domain from URL
        try:
            parsed = urlparse(page_url)
            domain_url = parsed.netloc

            if not domain_url and parsed.path:
                # Handle app-style URLs (no scheme)
                domain_url = parsed.path.split('/')[0]

            domain_url = normalize_domain_url(domain_url)
            if not domain_url:
                return None

            # Try direct lookup
            if domain_url in domain_url_map:
                return domain_url_map[domain_url]

            # Try without www prefix
            domain_url_no_www = domain_url.replace('www.', '')
            if domain_url_no_www in domain_url_map:
                return domain_url_map[domain_url_no_www]

            # Try with www prefix
            domain_url_with_www = f"www.{domain_url}"
            if domain_url_with_www in domain_url_map:
                return domain_url_map[domain_url_with_www]

            # Try fuzzy match (contains)
            for url_key, domain in domain_url_map.items():
                if url_key in domain_url or domain_url in url_key:
                    return domain

        except Exception as err:
            logger.warning(f" Failed to parse URL {page_url}: {str(err)}")

        return None


__all__ = [
    "ManageGenerator",
    "ManageGenerationResult",
]
