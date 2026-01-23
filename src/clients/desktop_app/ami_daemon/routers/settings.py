"""
Settings API Router

Manages user settings including budget configuration.
Based on Eigent's budget tracking and settings patterns.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import logging
import json
from pathlib import Path

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/settings", tags=["Settings"])


# ============== Data Storage ==============

def get_settings_file() -> Path:
    """Get path to settings storage file."""
    ami_dir = Path.home() / ".ami"
    ami_dir.mkdir(exist_ok=True)
    return ami_dir / "settings.json"


def load_settings() -> Dict[str, Any]:
    """Load settings from storage."""
    file_path = get_settings_file()
    if file_path.exists():
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load settings: {e}")
    return {
        "budget": {
            "maxTokens": None,
            "maxCostUsd": None,
            "warningThreshold": 0.8,
            "fallbackModel": "claude-3-5-haiku-20241022",
            "action": "warn"
        }
    }


def save_settings(data: Dict[str, Any]) -> None:
    """Save settings to storage."""
    file_path = get_settings_file()
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save settings: {e}")
        raise


# ============== Request/Response Models ==============

class BudgetConfig(BaseModel):
    """Budget configuration settings."""
    maxTokens: Optional[int] = Field(None, description="Maximum tokens per task (null = unlimited)")
    maxCostUsd: Optional[float] = Field(None, description="Maximum cost in USD per task (null = unlimited)")
    warningThreshold: float = Field(0.8, ge=0.0, le=1.0, description="Warning threshold (0.0-1.0)")
    fallbackModel: str = Field("claude-3-5-haiku-20241022", description="Model to use when budget exceeded")
    action: str = Field("warn", description="Action on budget exceed: warn, throttle, confirm, stop")


class BudgetConfigResponse(BaseModel):
    """Budget configuration response."""
    budget: BudgetConfig


# ============== Endpoints ==============

@router.get("/budget", response_model=BudgetConfigResponse)
async def get_budget_settings():
    """
    Get current budget settings.
    """
    settings = load_settings()
    budget = settings.get("budget", {})

    return BudgetConfigResponse(
        budget=BudgetConfig(
            maxTokens=budget.get("maxTokens"),
            maxCostUsd=budget.get("maxCostUsd"),
            warningThreshold=budget.get("warningThreshold", 0.8),
            fallbackModel=budget.get("fallbackModel", "claude-3-5-haiku-20241022"),
            action=budget.get("action", "warn")
        )
    )


@router.post("/budget")
async def update_budget_settings(config: BudgetConfig):
    """
    Update budget settings.

    Settings are applied to new tasks. Running tasks continue with their
    original budget configuration.
    """
    try:
        settings = load_settings()

        settings["budget"] = {
            "maxTokens": config.maxTokens,
            "maxCostUsd": config.maxCostUsd,
            "warningThreshold": config.warningThreshold,
            "fallbackModel": config.fallbackModel,
            "action": config.action
        }

        save_settings(settings)
        logger.info(f"Budget settings updated: {config.dict()}")

        return {
            "success": True,
            "message": "Budget settings updated",
            "budget": settings["budget"]
        }

    except Exception as e:
        logger.error(f"Failed to update budget settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
async def get_all_settings():
    """
    Get all settings.
    """
    return load_settings()


@router.post("")
async def update_all_settings(settings: Dict[str, Any]):
    """
    Update all settings.
    """
    try:
        # Merge with existing settings
        current = load_settings()
        current.update(settings)
        save_settings(current)

        return {"success": True, "message": "Settings updated"}

    except Exception as e:
        logger.error(f"Failed to update settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))
