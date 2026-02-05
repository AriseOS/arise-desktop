"""Local BGE (BAAI General Embedding) Model.

This module provides a local implementation of text embeddings using the BGE
(BAAI General Embedding) models from the Beijing Academy of Artificial Intelligence.
Uses sentence-transformers for efficient local embedding generation.
"""

import warnings
from typing import Any, List, Optional

import numpy as np

from src.common.memory.services.embedding_model.embedding_model import (
    EmbeddingModel,
    EmbeddingProvider,
    EmbeddingResponse,
)


class LocalBGEModel(EmbeddingModel):
    """Local BGE embedding model implementation.

    Uses the sentence-transformers library to load and run BGE models locally.
    Supports various BGE model sizes (small, base, large) for different
    trade-offs between speed and quality.

    Attributes:
        model_name: The BGE model name (e.g., "BAAI/bge-base-en-v1.5").
        provider: Set to EmbeddingProvider.LOCAL_BOW (reused for local models).
        dimension: The output dimension of embeddings.
        model: The loaded sentence-transformers model.
        device: Device to run the model on ("cpu" or "cuda").
        config: Additional configuration parameters.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-base-en-v1.5",
        dimension: int = 768,
        **kwargs: Any,
    ) -> None:
        """Initializes the LocalBGEModel.

        Args:
            model_name: The BGE model identifier. Common options:
                - "BAAI/bge-small-en-v1.5" (384 dim)
                - "BAAI/bge-base-en-v1.5" (768 dim, recommended)
                - "BAAI/bge-large-en-v1.5" (1024 dim)
                - Or a local path to downloaded model (e.g., "models/bge-base-en-v1.5")
            dimension: The expected output dimension of embeddings.
            **kwargs: Additional configuration parameters:
                - device: Device to run on ("cpu", "cuda", or "auto")
                - normalize_embeddings: Whether to normalize embeddings (default: True)
                - batch_size: Batch size for encoding (default: 32)
                - use_local_model: Whether to use local model directory (default: False)
        """
        super().__init__(model_name=model_name, dimension=dimension, **kwargs)
        self.provider = EmbeddingProvider.LOCAL_BOW  # Reuse for local models

        # Extract configuration
        self.device = kwargs.get("device", "cpu")
        self.normalize_embeddings = kwargs.get("normalize_embeddings", True)
        self.batch_size = kwargs.get("batch_size", 32)
        self.use_local_model = kwargs.get("use_local_model", False)

        # Initialize model (lazy loading)
        self.model = None
        self._load_model()

    def _load_model(self) -> None:
        """Loads the sentence-transformers model.

        Raises:
            ImportError: If sentence-transformers is not installed.
            Exception: If the model cannot be loaded.
        """
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for LocalBGEModel. "
                "Install it with: pip install sentence-transformers"
            )

        try:
            # Determine model path
            model_path = self.model_name

            # If use_local_model is True, construct local path
            if self.use_local_model:
                import os
                from pathlib import Path

                # Get the directory of this file
                current_dir = Path(__file__).parent
                models_dir = current_dir / "models"

                # Extract short name if it's a HuggingFace path
                if "/" in self.model_name:
                    short_name = self.model_name.split("/")[-1]
                else:
                    short_name = self.model_name

                local_path = models_dir / short_name

                # Use local path if it exists, otherwise fallback to remote
                if local_path.exists():
                    model_path = str(local_path)
                    print(f"Loading model from local path: {model_path}")
                else:
                    print(f"Local model not found at {local_path}, downloading from HuggingFace...")

            self.model = SentenceTransformer(model_path, device=self.device)

            # Update dimension based on actual model
            if self.model.get_sentence_embedding_dimension() != self.dimension:
                actual_dim = self.model.get_sentence_embedding_dimension()
                warnings.warn(
                    f"Model dimension ({actual_dim}) differs from specified "
                    f"dimension ({self.dimension}). Using model dimension.",
                    UserWarning,
                )
                self.dimension = actual_dim

        except Exception as e:
            raise RuntimeError(f"Failed to load BGE model '{self.model_name}': {e}")

    def embed(self, text: str, **kwargs: Any) -> EmbeddingResponse:
        """Generates an embedding for a single text input.

        Args:
            text: Input text to embed.
            **kwargs: Additional parameters:
                - normalize: Override normalize_embeddings for this call.

        Returns:
            EmbeddingResponse containing the embedding vector.
        """
        if self.model is None:
            self._load_model()

        # Get normalization setting
        normalize = kwargs.get("normalize", self.normalize_embeddings)

        # Encode text
        embedding = self.model.encode(
            text, normalize_embeddings=normalize, convert_to_numpy=True
        )

        return EmbeddingResponse(
            embedding=embedding,
            model=self.model_name,
            provider=self.provider.value,
            dimension=len(embedding),
            usage={"input_length": len(text)},
        )

    def embed_batch(self, texts: List[str], **kwargs: Any) -> List[EmbeddingResponse]:
        """Generates embeddings for multiple text inputs.

        Args:
            texts: List of input texts to embed.
            **kwargs: Additional parameters:
                - normalize: Override normalize_embeddings for this call.
                - batch_size: Override batch_size for this call.

        Returns:
            List of EmbeddingResponse objects, one per input text.
        """
        if self.model is None:
            self._load_model()

        # Get parameters
        normalize = kwargs.get("normalize", self.normalize_embeddings)
        batch_size = kwargs.get("batch_size", self.batch_size)

        # Encode all texts
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=normalize,
            convert_to_numpy=True,
            show_progress_bar=False,
        )

        # Create responses
        responses = []
        for i, embedding in enumerate(embeddings):
            response = EmbeddingResponse(
                embedding=embedding,
                model=self.model_name,
                provider=self.provider.value,
                dimension=len(embedding),
                usage={"input_length": len(texts[i])},
            )
            responses.append(response)

        return responses

    async def embed_async(self, text: str, **kwargs: Any) -> EmbeddingResponse:
        """Generates an embedding for a single text input (async).

        Note: Currently wraps the synchronous method. For true async support,
        consider using a thread pool executor in production.

        Args:
            text: Input text to embed.
            **kwargs: Additional parameters.

        Returns:
            EmbeddingResponse containing the embedding vector.
        """
        # For now, just call synchronous version
        # TODO: Implement true async using asyncio.to_thread or similar
        return self.embed(text, **kwargs)

    async def embed_batch_async(
        self, texts: List[str], **kwargs: Any
    ) -> List[EmbeddingResponse]:
        """Generates embeddings for multiple text inputs (async).

        Note: Currently wraps the synchronous method. For true async support,
        consider using a thread pool executor in production.

        Args:
            texts: List of input texts to embed.
            **kwargs: Additional parameters.

        Returns:
            List of EmbeddingResponse objects, one per input text.
        """
        # For now, just call synchronous version
        # TODO: Implement true async using asyncio.to_thread or similar
        return self.embed_batch(texts, **kwargs)

    def check_config(self) -> bool:
        """Validates the model configuration.

        Checks if the model can be loaded successfully.

        Returns:
            True if the model is loaded and ready, False otherwise.
        """
        try:
            if self.model is None:
                self._load_model()
            return self.model is not None
        except Exception:
            return False

    def get_model_info(self) -> dict:
        """Returns information about the loaded model.

        Returns:
            Dictionary containing model metadata:
                - model_name: The model identifier
                - dimension: Embedding dimension
                - device: Device the model is running on
                - max_seq_length: Maximum sequence length
        """
        if self.model is None:
            self._load_model()

        return {
            "model_name": self.model_name,
            "dimension": self.dimension,
            "device": str(self.model.device),
            "max_seq_length": self.model.max_seq_length,
        }
