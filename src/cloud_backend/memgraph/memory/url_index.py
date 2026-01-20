"""URLIndex - Fast URL to State lookup using in-memory index.

This module provides a fast in-memory index for mapping URLs to State IDs.
The index is built from the graph store on initialization and maintained
during runtime as new PageInstances are added.

Design Decision (from memory-graph-ontology-design.md 8.4):
    - Use in-memory Dict for O(1) lookup
    - Easy to debug
    - Build from graph on startup
"""

from typing import Dict, List, Optional

from src.cloud_backend.memgraph.graphstore.graph_store import GraphStore
from src.cloud_backend.memgraph.ontology.state import State


class URLIndex:
    """URLIndex - Fast URL to State ID lookup.

    This class maintains an in-memory mapping from URLs to State IDs,
    enabling O(1) lookup to find which State a URL belongs to.

    The index supports:
    - Real-time merge: When a new URL comes in, check if it exists
    - Fast lookup: O(1) URL -> State ID
    - Rebuild: Can rebuild from graph store

    Attributes:
        _url_to_state: Dictionary mapping URL to State ID.
    """

    def __init__(self):
        """Initialize URLIndex with empty mappings."""
        self._url_to_state: Dict[str, str] = {}

    def find_state_by_url(self, url: str) -> Optional[str]:
        """Find the State ID that contains the given URL.

        Args:
            url: URL to look up.

        Returns:
            State ID if found, None otherwise.
        """
        return self._url_to_state.get(url)

    def add_url(self, url: str, state_id: str) -> None:
        """Add a URL to State mapping.

        Args:
            url: URL to add.
            state_id: State ID that contains this URL.
        """
        self._url_to_state[url] = state_id

    def remove_url(self, url: str) -> bool:
        """Remove a URL from the index.

        Args:
            url: URL to remove.

        Returns:
            True if URL was found and removed, False otherwise.
        """
        if url in self._url_to_state:
            del self._url_to_state[url]
            return True
        return False

    def has_url(self, url: str) -> bool:
        """Check if a URL exists in the index.

        Args:
            url: URL to check.

        Returns:
            True if URL exists in the index.
        """
        return url in self._url_to_state

    def get_all_urls_for_state(self, state_id: str) -> List[str]:
        """Get all URLs that belong to a State.

        Args:
            state_id: State ID to look up.

        Returns:
            List of URLs belonging to the State.
        """
        return [url for url, sid in self._url_to_state.items() if sid == state_id]

    def clear(self) -> None:
        """Clear the entire index."""
        self._url_to_state.clear()

    def build_from_graph(self, graph_store: GraphStore) -> int:
        """Build the index from a GraphStore.

        This method queries all State nodes from the graph and builds
        the URL index from their instances field.

        Args:
            graph_store: GraphStore to build index from.

        Returns:
            Number of URLs indexed.
        """
        self.clear()

        try:
            # Query all State nodes
            nodes = graph_store.query_nodes(label="State", filters=None, limit=None)

            url_count = 0
            for node_data in nodes:
                state = State.from_dict(node_data)
                state_id = state.id

                # Add primary URL (backward compatibility)
                if state.page_url:
                    self.add_url(state.page_url, state_id)
                    url_count += 1

                # Add all instance URLs
                for instance in state.instances:
                    url = (
                        instance.url
                        if hasattr(instance, "url")
                        else instance.get("url")
                    )
                    if url and url != state.page_url:  # Avoid duplicates
                        self.add_url(url, state_id)
                        url_count += 1

            return url_count

        except Exception as e:
            print(f"Error building URL index from graph: {e}")
            return 0

    def get_stats(self) -> Dict[str, int]:
        """Get index statistics.

        Returns:
            Dictionary with index statistics.
        """
        unique_states = len(set(self._url_to_state.values()))
        return {
            "total_urls": len(self._url_to_state),
            "unique_states": unique_states,
            "avg_urls_per_state": (
                len(self._url_to_state) / unique_states if unique_states > 0 else 0
            ),
        }

    def __len__(self) -> int:
        """Return the number of URLs in the index."""
        return len(self._url_to_state)

    def __contains__(self, url: str) -> bool:
        """Check if URL is in the index."""
        return url in self._url_to_state


__all__ = [
    "URLIndex",
]
