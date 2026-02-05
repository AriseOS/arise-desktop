"""Embedding Model Configuration Checker.

This module provides utilities for validating embedding model configurations,
ensuring that all required settings are properly configured before use.
"""

import os
from typing import Any, Dict, List, Optional

from src.common.memory.services.embedding_model.embedding_model import (
    EmbeddingModel,
    EmbeddingProvider,
)


class ConfigValidationError(Exception):
    """Exception raised when embedding model configuration validation fails.

    Attributes:
        message: Explanation of the validation error.
        provider: The embedding provider that failed validation.
        missing_fields: List of missing or invalid configuration fields.
    """

    def __init__(
        self,
        message: str,
        provider: Optional[str] = None,
        missing_fields: Optional[List[str]] = None,
    ) -> None:
        """Initializes a ConfigValidationError.

        Args:
            message: Explanation of the validation error.
            provider: The embedding provider that failed validation.
            missing_fields: List of missing or invalid configuration fields.
        """
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.missing_fields = missing_fields or []


class EmbeddingModelConfigChecker:
    """Validates embedding model configurations.

    This class provides methods to check whether embedding models are properly
    configured with valid API keys, model files, and other required settings.

    Example usage:
        checker = EmbeddingModelConfigChecker()
        is_valid = checker.check_openai_config(api_key="your-key")
        model_valid = checker.check_model(my_embedding_model)
    """

    @staticmethod
    def check_openai_config(
        api_key: Optional[str] = None,
        api_client: Optional[Any] = None,
        model_name: Optional[str] = None,
    ) -> bool:
        """Validates OpenAI embedding configuration.

        Args:
            api_key: The OpenAI API key. If None, checks environment variable.
            api_client: An initialized OpenAI client instance.
            model_name: The model name to validate.

        Returns:
            True if configuration is valid, False otherwise.
        """
        # Check API key
        if not api_key:
            api_key = os.getenv("OPENAI_API_KEY")

        if not api_key and not api_client:
            return False

        # If client is provided, check its structure
        if api_client:
            if not hasattr(api_client, "embeddings"):
                return False

        # Check model name if provided
        if model_name:
            valid_prefixes = [
                "text-embedding-ada",
                "text-embedding-3-small",
                "text-embedding-3-large",
            ]
            if not any(model_name.startswith(prefix) for prefix in valid_prefixes):
                # Not necessarily invalid, but might be a custom model
                pass

        return True

    @staticmethod
    def check_local_bge_config(
        model_name: Optional[str] = None, device: Optional[str] = None
    ) -> bool:
        """Validates Local BGE model configuration.

        Args:
            model_name: The BGE model name to validate.
            device: The device to run on ("cpu", "cuda", "auto").

        Returns:
            True if configuration is valid, False otherwise.
        """
        # Check if sentence-transformers is installed
        try:
            import sentence_transformers
        except ImportError:
            return False

        # Check device validity
        if device and device not in ["cpu", "cuda", "auto"]:
            return False

        # Check model name format
        if model_name:
            # BGE models typically follow pattern "BAAI/bge-*"
            if not model_name.startswith("BAAI/bge-") and not model_name.startswith(
                "sentence-transformers/"
            ):
                # Might be a valid model from other sources
                pass

        return True

    @staticmethod
    def check_model(model: EmbeddingModel) -> bool:
        """Validates an embedding model instance.

        This method calls the model's check_config() method to validate
        its configuration.

        Args:
            model: The embedding model instance to validate.

        Returns:
            True if the model is properly configured, False otherwise.
        """
        if not model:
            return False

        try:
            return model.check_config()
        except Exception:
            return False

    @staticmethod
    def validate_model(model: EmbeddingModel, raise_on_error: bool = True) -> bool:
        """Validates an embedding model and optionally raises an exception on failure.

        Args:
            model: The embedding model instance to validate.
            raise_on_error: If True, raises ConfigValidationError on failure.

        Returns:
            True if the model is valid.

        Raises:
            ConfigValidationError: If validation fails and raise_on_error is True.
        """
        is_valid = EmbeddingModelConfigChecker.check_model(model)

        if not is_valid and raise_on_error:
            provider = model.provider.value if hasattr(model, "provider") else "unknown"
            raise ConfigValidationError(
                f"Embedding model configuration validation failed for provider: {provider}",
                provider=provider,
            )

        return is_valid

    @staticmethod
    def get_config_issues(model: EmbeddingModel) -> List[str]:
        """Identifies specific configuration issues with a model.

        Args:
            model: The embedding model instance to check.

        Returns:
            A list of configuration issue descriptions. Empty if valid.
        """
        issues = []

        if not model:
            issues.append("Model is None")
            return issues

        # Check basic model structure
        if not hasattr(model, "model_name") or not model.model_name:
            issues.append("Missing or empty 'model_name'")

        if not hasattr(model, "provider"):
            issues.append("Missing 'provider' attribute")

        if not hasattr(model, "dimension") or model.dimension <= 0:
            issues.append("Invalid or missing 'dimension'")

        # Provider-specific checks
        if hasattr(model, "provider"):
            if model.provider == EmbeddingProvider.OPENAI:
                if not hasattr(model, "client") and not hasattr(model, "api_key"):
                    issues.append("OpenAI model missing both 'client' and 'api_key'")
                elif hasattr(model, "api_key") and not model.api_key:
                    issues.append("OpenAI API key is empty")

            elif model.provider == EmbeddingProvider.LOCAL_BGE:
                if not hasattr(model, "model"):
                    issues.append("Local BGE model missing 'model' attribute")
                try:
                    import sentence_transformers
                except ImportError:
                    issues.append(
                        "sentence-transformers library not installed for BGE model"
                    )

        return issues

    @staticmethod
    def create_validation_report(models: Dict[str, EmbeddingModel]) -> Dict[str, Any]:
        """Creates a detailed validation report for multiple models.

        Args:
            models: A dictionary mapping model names to model instances.

        Returns:
            A dictionary containing validation results for each model:
            {
                "valid_count": int,
                "invalid_count": int,
                "results": {
                    "model_name": {
                        "valid": bool,
                        "issues": List[str]
                    }
                }
            }
        """
        report = {"valid_count": 0, "invalid_count": 0, "results": {}}

        for name, model in models.items():
            is_valid = EmbeddingModelConfigChecker.check_model(model)
            issues = EmbeddingModelConfigChecker.get_config_issues(model)

            report["results"][name] = {"valid": is_valid, "issues": issues}

            if is_valid:
                report["valid_count"] += 1
            else:
                report["invalid_count"] += 1

        return report


def check_all_env_configs() -> Dict[str, bool]:
    """Checks all embedding provider environment configurations.

    Returns:
        A dictionary mapping provider names to their configuration status:
        {
            "openai": bool,
            "local_bge": bool
        }
    """
    return {
        "openai": EmbeddingModelConfigChecker.check_openai_config(),
        "local_bge": EmbeddingModelConfigChecker.check_local_bge_config(),
    }


def get_available_providers() -> List[str]:
    """Returns a list of embedding providers that are properly configured.

    Returns:
        List of provider names (strings) that have valid configurations.
    """
    configs = check_all_env_configs()
    return [provider for provider, is_valid in configs.items() if is_valid]
