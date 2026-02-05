"""Rerank Model Configuration Checker.

This module provides utilities for validating rerank model configurations,
ensuring that all required settings are properly configured before use.
"""

import os
from typing import Any, Dict, List, Optional

from src.common.memory.services.rerank_model.rerank_model import RerankModel, RerankProvider


class ConfigValidationError(Exception):
    """Exception raised when rerank model configuration validation fails.

    Attributes:
        message: Explanation of the validation error.
        provider: The rerank provider that failed validation.
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
            provider: The rerank provider that failed validation.
            missing_fields: List of missing or invalid configuration fields.
        """
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.missing_fields = missing_fields or []


class RerankModelConfigChecker:
    """Validates rerank model configurations.

    This class provides methods to check whether rerank models are properly
    configured with valid API keys, model files, and other required settings.

    Example usage:
        checker = RerankModelConfigChecker()
        is_valid = checker.check_maas_config(api_key="your-key")
        model_valid = checker.check_model(my_rerank_model)
    """

    @staticmethod
    def check_maas_config(
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> bool:
        """Validates MaaS rerank configuration.

        Args:
            api_key: The MaaS API key. If None, checks environment variable.
            base_url: The MaaS API base URL. If None, checks environment variable.
            model_name: The model name to validate.

        Returns:
            True if configuration is valid, False otherwise.
        """
        # Check API key
        if not api_key:
            api_key = os.getenv("MAAS_API_KEY")

        if not api_key:
            return False

        # Check base URL
        if not base_url:
            base_url = os.getenv("MAAS_BASE_URL")

        if not base_url:
            # Base URL has a default, so this is optional
            pass

        # Check model name if provided
        if model_name:
            valid_prefixes = ["bge-reranker", "rerank"]
            if not any(model_name.startswith(prefix) for prefix in valid_prefixes):
                # Not necessarily invalid, might be a custom model
                pass

        return True

    @staticmethod
    def check_local_bge_config(
        model_name: Optional[str] = None, device: Optional[str] = None
    ) -> bool:
        """Validates Local BGE reranker configuration.

        Args:
            model_name: The BGE reranker model name to validate.
            device: The device to run on ("cpu", "cuda", "auto").

        Returns:
            True if configuration is valid, False otherwise.
        """
        # Check if sentence-transformers is installed
        try:
            # pylint: disable=import-outside-toplevel, unused-import
            import sentence_transformers
        except ImportError:
            return False

        # Check device validity
        if device and device not in ["cpu", "cuda", "auto"]:
            return False

        # Check model name format
        if model_name:
            # BGE reranker models typically follow pattern "BAAI/bge-reranker-*"
            if not model_name.startswith("BAAI/bge-reranker"):
                # Might be a valid model from other sources
                pass

        return True

    @staticmethod
    def check_model(model: RerankModel) -> bool:
        """Validates a rerank model instance.

        This method calls the model's check_config() method to validate
        its configuration.

        Args:
            model: The rerank model instance to validate.

        Returns:
            True if the model is properly configured, False otherwise.
        """
        if not model:
            return False

        try:
            return model.check_config()
        except Exception:  # pylint: disable=broad-exception-caught
            return False

    @staticmethod
    def validate_model(model: RerankModel, raise_on_error: bool = True) -> bool:
        """Validates a rerank model and optionally raises an exception on failure.

        Args:
            model: The rerank model instance to validate.
            raise_on_error: If True, raises ConfigValidationError on failure.

        Returns:
            True if the model is valid.

        Raises:
            ConfigValidationError: If validation fails and raise_on_error is True.
        """
        is_valid = RerankModelConfigChecker.check_model(model)

        if not is_valid and raise_on_error:
            provider = model.provider.value if hasattr(model, "provider") else "unknown"
            raise ConfigValidationError(
                f"Rerank model configuration validation failed for provider: {provider}",
                provider=provider,
            )

        return is_valid

    @staticmethod
    def get_config_issues(model: RerankModel) -> List[str]:
        """Identifies specific configuration issues with a model.

        Args:
            model: The rerank model instance to check.

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

        # Provider-specific checks
        if hasattr(model, "provider"):
            if model.provider == RerankProvider.MAAS:
                if not hasattr(model, "api_key") or not model.api_key:
                    issues.append("MaaS model missing 'api_key'")
                if not hasattr(model, "base_url") or not model.base_url:
                    issues.append("MaaS model missing 'base_url'")

            elif model.provider == RerankProvider.LOCAL_BGE:
                if not hasattr(model, "model"):
                    issues.append("Local BGE model missing 'model' attribute")
                try:
                    # pylint: disable=import-outside-toplevel, unused-import
                    import sentence_transformers
                except ImportError:
                    issues.append(
                        "sentence-transformers library not installed for BGE model"
                    )

        return issues

    @staticmethod
    def create_validation_report(models: Dict[str, RerankModel]) -> Dict[str, Any]:
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
            is_valid = RerankModelConfigChecker.check_model(model)
            issues = RerankModelConfigChecker.get_config_issues(model)

            report["results"][name] = {"valid": is_valid, "issues": issues}

            if is_valid:
                report["valid_count"] += 1
            else:
                report["invalid_count"] += 1

        return report


def check_all_env_configs() -> Dict[str, bool]:
    """Checks all rerank provider environment configurations.

    Returns:
        A dictionary mapping provider names to their configuration status:
        {
            "maas": bool,
            "local_bge": bool
        }
    """
    return {
        "maas": RerankModelConfigChecker.check_maas_config(),
        "local_bge": RerankModelConfigChecker.check_local_bge_config(),
    }


def get_available_providers() -> List[str]:
    """Returns a list of rerank providers that are properly configured.

    Returns:
        List of provider names (strings) that have valid configurations.
    """
    configs = check_all_env_configs()
    return [provider for provider, is_valid in configs.items() if is_valid]
