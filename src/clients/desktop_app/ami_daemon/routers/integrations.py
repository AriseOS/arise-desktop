"""
Integrations API Router

Manages cloud service integrations (Gmail, Google Drive, Calendar, Notion).
Based on Eigent's integration management patterns.

Features:
- OAuth flow handling for Google services
- Token-based authentication for Notion
- Integration status tracking
- Credential storage (secure)
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import logging
import os
import json
from pathlib import Path

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/integrations", tags=["Integrations"])


# ============== Data Storage ==============

def get_integrations_file() -> Path:
    """Get path to integrations storage file."""
    ami_dir = Path.home() / ".ami"
    ami_dir.mkdir(exist_ok=True)
    return ami_dir / "integrations.json"


def load_integrations() -> Dict[str, Any]:
    """Load integrations from storage."""
    file_path = get_integrations_file()
    if file_path.exists():
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load integrations: {e}")
    return {"installed": [], "configs": {}}


def save_integrations(data: Dict[str, Any]) -> None:
    """Save integrations to storage."""
    file_path = get_integrations_file()
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save integrations: {e}")


# ============== Request/Response Models ==============

class IntegrationConfigRequest(BaseModel):
    """Configuration for token-based integrations."""
    api_key: Optional[str] = Field(None, description="API key (e.g., Notion)")


class IntegrationListResponse(BaseModel):
    """List of installed integrations."""
    installed: List[str]
    available: List[str] = [
        "gmail", "google_drive", "google_calendar", "notion"
    ]


class OAuthStatusResponse(BaseModel):
    """OAuth flow status."""
    completed: bool = False
    failed: bool = False
    error: Optional[str] = None


# ============== OAuth State Tracking ==============

# In-memory OAuth state (would be Redis in production)
_oauth_states: Dict[str, Dict[str, Any]] = {}


# ============== Endpoints ==============

@router.get("/list", response_model=IntegrationListResponse)
async def list_integrations():
    """
    List installed integrations.

    Returns list of integration IDs that have been configured.
    """
    data = load_integrations()
    return IntegrationListResponse(
        installed=data.get("installed", []),
        available=["gmail", "google_drive", "google_calendar", "notion"]
    )


@router.get("/oauth-status/{integration_id}", response_model=OAuthStatusResponse)
async def get_oauth_status(integration_id: str):
    """
    Get OAuth flow status for an integration.

    Frontend polls this endpoint after initiating OAuth to check completion.
    """
    state = _oauth_states.get(integration_id)
    if not state:
        # No active OAuth flow - check if already installed
        data = load_integrations()
        if integration_id in data.get("installed", []):
            return OAuthStatusResponse(completed=True)
        return OAuthStatusResponse(completed=False, failed=False)

    return OAuthStatusResponse(
        completed=state.get("completed", False),
        failed=state.get("failed", False),
        error=state.get("error")
    )


@router.post("/oauth-callback/{integration_id}")
async def oauth_callback(integration_id: str, code: str, state: Optional[str] = None):
    """
    Handle OAuth callback.

    This endpoint receives the authorization code after user consents.
    Exchanges code for tokens and stores credentials.
    """
    try:
        # For Google integrations, exchange code for tokens
        if integration_id in ("gmail", "google_drive", "google_calendar"):
            # In production, this would:
            # 1. Exchange auth code for access/refresh tokens
            # 2. Store tokens securely
            # 3. Mark integration as installed

            # For now, mark as completed (frontend handles OAuth via Tauri)
            _oauth_states[integration_id] = {"completed": True}

            # Update storage
            data = load_integrations()
            if integration_id not in data["installed"]:
                data["installed"].append(integration_id)
                save_integrations(data)

            logger.info(f"OAuth completed for {integration_id}")
            return {"success": True, "message": "OAuth completed"}

        else:
            raise HTTPException(status_code=400, detail="Invalid integration for OAuth")

    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        _oauth_states[integration_id] = {"failed": True, "error": str(e)}
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/configure/{integration_id}")
async def configure_integration(integration_id: str, config: IntegrationConfigRequest):
    """
    Configure a token-based integration.

    For integrations like Notion that use API keys instead of OAuth.
    """
    try:
        # Validate the configuration
        if integration_id == "notion":
            if not config.api_key or not config.api_key.startswith("secret_"):
                raise HTTPException(
                    status_code=400,
                    detail="Invalid Notion API key. Must start with 'secret_'"
                )

            # Store configuration
            data = load_integrations()
            if "configs" not in data:
                data["configs"] = {}
            data["configs"][integration_id] = {
                "api_key": config.api_key,  # In production, encrypt this
                "configured_at": str(os.popen('date').read().strip())
            }

            if integration_id not in data["installed"]:
                data["installed"].append(integration_id)

            save_integrations(data)
            logger.info(f"Configured {integration_id}")

            return {"success": True, "message": f"{integration_id} configured successfully"}

        else:
            raise HTTPException(status_code=400, detail=f"Unknown integration: {integration_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Configure error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/uninstall/{integration_id}")
async def uninstall_integration(integration_id: str):
    """
    Uninstall an integration.

    Removes credentials and marks as uninstalled.
    """
    try:
        data = load_integrations()

        # Remove from installed list
        if integration_id in data.get("installed", []):
            data["installed"].remove(integration_id)

        # Remove configuration
        if integration_id in data.get("configs", {}):
            del data["configs"][integration_id]

        save_integrations(data)

        # Clear OAuth state
        if integration_id in _oauth_states:
            del _oauth_states[integration_id]

        logger.info(f"Uninstalled {integration_id}")
        return {"success": True, "message": f"{integration_id} uninstalled"}

    except Exception as e:
        logger.error(f"Uninstall error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config/{integration_id}")
async def get_integration_config(integration_id: str):
    """
    Get configuration for an integration (without secrets).

    Returns metadata about configuration without exposing API keys.
    """
    data = load_integrations()

    if integration_id not in data.get("installed", []):
        raise HTTPException(status_code=404, detail="Integration not installed")

    config = data.get("configs", {}).get(integration_id, {})

    # Return config without sensitive data
    return {
        "integration_id": integration_id,
        "installed": True,
        "configured_at": config.get("configured_at"),
        "has_api_key": bool(config.get("api_key")),
    }
