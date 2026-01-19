"""Memory-based vector index for efficient similarity search.

This module provides an in-memory vector indexing system for graph nodes,
supporting efficient nearest neighbor search with cosine and euclidean distance metrics.
"""

from typing import List, Optional, Tuple

import numpy as np


class VectorIndex:
    """Memory-based vector index for efficient similarity search.

    Uses numpy for vectorized operations and supports cosine and euclidean metrics.
    Provides fast nearest neighbor search for high-dimensional vectors.

    Attributes:
        metric_type: Distance metric type ("cosine" or "euclidean")
        vectors: Numpy array of indexed vectors
        node_ids: List of node IDs corresponding to vectors
        dimension: Dimensionality of vectors
    """

    def __init__(self, metric_type: str = "cosine"):
        """Initialize vector index.

        Args:
            metric_type: Distance metric type ("cosine" or "euclidean"). Defaults to "cosine".
        """
        self.metric_type = metric_type
        self.vectors: Optional[np.ndarray] = None  # Shape: (n_vectors, dimension)
        self.node_ids: List[str] = []  # Corresponding node IDs
        self.dimension: Optional[int] = None

    def build(self, vectors: np.ndarray, node_ids: List[str]):
        """Build index from vectors.

        Args:
            vectors: Array of shape (n_vectors, dimension)
            node_ids: List of node IDs corresponding to vectors

        Raises:
            ValueError: If vectors and node_ids have different lengths
        """
        if len(vectors) != len(node_ids):
            raise ValueError(
                f"Vectors and node_ids must have same length: {len(vectors)} != {len(node_ids)}"
            )

        if len(vectors) == 0:
            self.vectors = None
            self.node_ids = []
            self.dimension = None
            return

        self.vectors = np.array(vectors, dtype=np.float32)
        self.node_ids = list(node_ids)
        self.dimension = (
            self.vectors.shape[1] if len(self.vectors.shape) > 1 else self.vectors.shape[0]
        )

        # Normalize vectors for cosine similarity
        if self.metric_type == "cosine":
            norms = np.linalg.norm(self.vectors, axis=1, keepdims=True)
            norms = np.where(norms == 0, 1, norms)  # Avoid division by zero
            self.vectors = self.vectors / norms

    def search(
        self, query_vector: np.ndarray, topk: int = 10
    ) -> List[Tuple[str, float]]:
        """Search for nearest neighbors.

        Args:
            query_vector: Query vector of shape (dimension,)
            topk: Number of top results to return. Defaults to 10.

        Returns:
            List of (node_id, distance) tuples, sorted by distance (ascending)
        """
        if self.vectors is None or len(self.vectors) == 0:
            return []

        query_vector = np.array(query_vector, dtype=np.float32).flatten()

        if self.metric_type == "cosine":
            # Normalize query vector
            query_norm = np.linalg.norm(query_vector)
            if query_norm > 0:
                query_vector = query_vector / query_norm

            # Compute cosine similarity (dot product with normalized vectors)
            similarities = np.dot(self.vectors, query_vector)
            distances = 1 - similarities
        else:  # euclidean
            # Compute euclidean distances
            distances = np.linalg.norm(self.vectors - query_vector, axis=1)

        # Get top-k indices
        topk = min(topk, len(distances))
        if topk == 0:
            return []

        # Use argpartition for efficient top-k selection
        if topk < len(distances):
            top_indices = np.argpartition(distances, topk - 1)[:topk]
            top_indices = top_indices[np.argsort(distances[top_indices])]
        else:
            top_indices = np.argsort(distances)

        # Return results
        results = []
        for idx in top_indices:
            results.append((self.node_ids[idx], float(distances[idx])))

        return results

    def add_vector(self, vector: np.ndarray, node_id: str):
        """Add a single vector to the index.

        Args:
            vector: Vector to add
            node_id: Corresponding node ID
        """
        vector = np.array(vector, dtype=np.float32).flatten()

        if self.vectors is None:
            self.vectors = vector.reshape(1, -1)
            self.node_ids = [node_id]
            self.dimension = len(vector)

            if self.metric_type == "cosine":
                norm = np.linalg.norm(vector)
                if norm > 0:
                    self.vectors = self.vectors / norm
        else:
            if self.metric_type == "cosine":
                norm = np.linalg.norm(vector)
                if norm > 0:
                    vector = vector / norm

            self.vectors = np.vstack([self.vectors, vector.reshape(1, -1)])
            self.node_ids.append(node_id)

    def remove_vector(self, node_id: str):
        """Remove a vector from the index.

        Args:
            node_id: Node ID to remove
        """
        if node_id not in self.node_ids:
            return

        idx = self.node_ids.index(node_id)
        self.node_ids.pop(idx)

        if len(self.node_ids) == 0:
            self.vectors = None
            self.dimension = None
        else:
            self.vectors = np.delete(self.vectors, idx, axis=0)

    def update_vector(self, vector: np.ndarray, node_id: str):
        """Update an existing vector in the index.

        Args:
            vector: New vector
            node_id: Node ID to update
        """
        if node_id not in self.node_ids:
            # If not exists, add it
            self.add_vector(vector, node_id)
            return

        idx = self.node_ids.index(node_id)
        vector = np.array(vector, dtype=np.float32).flatten()

        if self.metric_type == "cosine":
            norm = np.linalg.norm(vector)
            if norm > 0:
                vector = vector / norm

        self.vectors[idx] = vector

    def rebuild(self):
        """Rebuild the index (useful after multiple updates)."""
        if self.vectors is not None and len(self.node_ids) > 0:
            # Re-normalize if using cosine metric
            if self.metric_type == "cosine":
                norms = np.linalg.norm(self.vectors, axis=1, keepdims=True)
                norms = np.where(norms == 0, 1, norms)
                self.vectors = self.vectors / norms

    def size(self) -> int:
        """Get the number of vectors in the index.

        Returns:
            Number of indexed vectors
        """
        return len(self.node_ids)

    def clear(self):
        """Clear all vectors from the index."""
        self.vectors = None
        self.node_ids = []
        self.dimension = None

    def __len__(self) -> int:
        """Return the number of vectors in the index.

        Returns:
            Number of indexed vectors
        """
        return self.size()

    def __repr__(self) -> str:
        """Return string representation of the index.

        Returns:
            String representation
        """
        return (
            f"VectorIndex(size={self.size()}, dimension={self.dimension}, "
            f"metric={self.metric_type})"
        )