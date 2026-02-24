"""
Sub2API Client - All user management delegated to sub2api.

Sub2api is the AI API Gateway that handles:
- User accounts (registration, login, profile)
- API key management (create, list, revoke)
- LLM request forwarding with per-user token tracking
- Email verification, password reset, session management

Cloud Backend has NO local users table. Sub2api is the single source of truth
for all user data. This client wraps both the Admin API and user-facing API.
"""

import logging
from typing import Optional
import httpx

logger = logging.getLogger(__name__)


def _extract_data(resp_json: dict) -> any:
    """Extract payload from sub2api response.

    Sub2api wraps responses as {"data": <payload>, "success": true}.
    Handles: missing "data" key (return raw), null data (raise), error responses.
    """
    if not isinstance(resp_json, dict):
        return resp_json
    # Check for error responses that returned 200
    if resp_json.get("success") is False:
        error_msg = resp_json.get("error", resp_json.get("message", "Unknown error"))
        raise RuntimeError(f"Sub2api returned error: {error_msg}")
    if "data" not in resp_json:
        return resp_json
    payload = resp_json["data"]
    if payload is None:
        raise RuntimeError(f"Sub2api returned null data: {resp_json}")
    return payload


class Sub2APIClient:
    """Client for sub2api Admin + User APIs."""

    def __init__(self, base_url: str, admin_api_key: str):
        """
        Args:
            base_url: Sub2api gateway base URL (e.g., "http://localhost:8080")
            admin_api_key: Admin API key for sub2api (x-api-key header)
        """
        self.base_url = base_url.rstrip("/")
        self.api_base = f"{self.base_url}/api"
        self.admin_api_key = admin_api_key

    def _admin_headers(self) -> dict:
        return {
            "x-api-key": self.admin_api_key,
            "Content-Type": "application/json",
        }

    # ===== User Management (Admin API) =====

    async def create_user(self, email: str, password: str, username: str = "") -> dict:
        """Create a user in sub2api via Admin API.

        POST /api/v1/admin/users
        Returns: {"id": int, "email": str, "username": str, "status": str, "role": str, ...}
        """
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.api_base}/v1/admin/users",
                json={
                    "email": email,
                    "password": password,
                    "username": username,
                },
                headers=self._admin_headers(),
            )
            resp.raise_for_status()
            return _extract_data(resp.json())

    async def get_user(self, user_id: int) -> dict:
        """Get user details via Admin API.

        GET /api/v1/admin/users/:id
        Returns: {"id": int, "email": str, "username": str, "status": str,
                  "role": str, "balance": str, "created_at": str, ...}
        """
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.api_base}/v1/admin/users/{user_id}",
                headers=self._admin_headers(),
            )
            resp.raise_for_status()
            return _extract_data(resp.json())

    async def list_users(
        self, page: int = 1, per_page: int = 50, search: str = ""
    ) -> dict:
        """List users via Admin API.

        GET /api/v1/admin/users
        Returns: {"users": [...], "total": int}
        """
        params = {"page": page, "per_page": per_page}
        if search:
            params["search"] = search
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.api_base}/v1/admin/users",
                params=params,
                headers=self._admin_headers(),
            )
            resp.raise_for_status()
            return _extract_data(resp.json())

    async def update_user(self, user_id: int, **fields) -> dict:
        """Update user fields via Admin API.

        PUT /api/v1/admin/users/:id
        Supported fields: status, role, username, etc.
        Returns: updated user dict
        """
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.put(
                f"{self.api_base}/v1/admin/users/{user_id}",
                json=fields,
                headers=self._admin_headers(),
            )
            resp.raise_for_status()
            return _extract_data(resp.json())

    async def get_user_subscriptions(self, user_id: int) -> list:
        """Get user's subscriptions (plan/group info) via Admin API.

        GET /api/v1/admin/users/:id/subscriptions
        Returns: list of subscription objects with group info
        """
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.api_base}/v1/admin/users/{user_id}/subscriptions",
                headers=self._admin_headers(),
            )
            resp.raise_for_status()
            return _extract_data(resp.json())

    # ===== Authentication (User-facing API) =====

    async def login(self, email: str, password: str) -> dict:
        """Login via sub2api auth endpoint.

        POST /api/v1/auth/login
        Note: sub2api requires valid email (not username) in the email field.
        Callers should resolve username → email before calling this method.

        Returns: {"access_token": str, "refresh_token": str, ...}
        """
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.api_base}/v1/auth/login",
                json={"email": email, "password": password},
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            token_data = _extract_data(resp.json())

            if token_data.get("requires_2fa"):
                raise RuntimeError(
                    f"Sub2api user {email} has 2FA enabled, cannot login programmatically"
                )

            return token_data

    async def register(self, email: str, password: str, username: str = "") -> dict:
        """Register + provision user. Creates sub2api user + initial API key.

        Raises httpx.HTTPStatusError (409) if user already exists — caller should
        handle this and return a proper "email already exists" error.

        Returns: {"user_id": int, "api_key": str, "access_token": str, "refresh_token": str}
        """
        # 1. Create user via admin API (409 = already exists, propagated to caller)
        user = await self.create_user(email, password, username)
        sub2api_user_id = user["id"]
        logger.info(f"Created sub2api user: id={sub2api_user_id}, email={email}")

        # 2. Login to get JWT
        token_data = await self.login(email, password)
        user_jwt = token_data["access_token"]

        # 3. Create initial API key via user-facing API
        key_data = await self.create_api_key_for_user(user_jwt, name="ami-cloud")
        api_key = key_data["key"]

        logger.info(f"Provisioned sub2api API key for user {sub2api_user_id}")
        return {
            "user_id": sub2api_user_id,
            "api_key": api_key,
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token", ""),
        }

    # ===== API Key Management =====

    async def create_api_key_for_user(
        self, user_jwt: str, name: str = "cloud-backend"
    ) -> dict:
        """Create an API key using the user's JWT token.

        POST /api/v1/keys
        Returns: {"id": int, "key": "sk-xxx", "name": str, ...}
        """
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.api_base}/v1/keys",
                json={"name": name},
                headers={
                    "Authorization": f"Bearer {user_jwt}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            return _extract_data(resp.json())

    async def get_user_api_keys(self, user_id: int) -> list:
        """Get user's API keys via Admin API.

        GET /api/v1/admin/users/:id/api-keys
        Returns: list of API key objects
        """
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.api_base}/v1/admin/users/{user_id}/api-keys",
                headers=self._admin_headers(),
            )
            resp.raise_for_status()
            return _extract_data(resp.json())

    async def get_first_api_key(self, user_id: int) -> Optional[str]:
        """Get user's first API key value. Returns None if no keys.

        Used for per-user LLM access — each user's requests are routed
        through sub2api using their own API key.
        """
        keys = await self.get_user_api_keys(user_id)
        if keys and isinstance(keys, list) and len(keys) > 0:
            return keys[0].get("key")
        return None

    async def delete_api_key(self, user_id: int, key_id: int) -> None:
        """Delete/revoke an API key via Admin API.

        DELETE /api/v1/admin/users/:user_id/api-keys/:key_id
        """
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.delete(
                f"{self.api_base}/v1/admin/users/{user_id}/api-keys/{key_id}",
                headers=self._admin_headers(),
            )
            resp.raise_for_status()

    # ===== Usage Tracking =====

    async def get_user_usage(self, user_id: int, period: str = "month") -> dict:
        """Get user's usage statistics via Admin API.

        GET /api/v1/admin/users/:id/usage
        Returns: {"total_requests": int, "total_cost": float, "total_tokens": int}
        """
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.api_base}/v1/admin/users/{user_id}/usage",
                params={"period": period},
                headers=self._admin_headers(),
            )
            resp.raise_for_status()
            return _extract_data(resp.json())

    # ===== Email Verification (proxy to sub2api) =====

    async def send_verify_code(self, email: str) -> dict:
        """Send email verification code via sub2api.

        POST /api/v1/auth/send-verify-code
        Returns: {"message": str, "countdown": int}
        """
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.api_base}/v1/auth/send-verify-code",
                json={"email": email},
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return _extract_data(resp.json())

    # ===== Password Reset (proxy to sub2api) =====

    async def forgot_password(self, email: str, frontend_base_url: str = "") -> dict:
        """Request password reset email via sub2api.

        POST /api/v1/auth/forgot-password
        Returns: {"message": str}
        """
        headers = {"Content-Type": "application/json"}
        if frontend_base_url:
            headers["X-Forwarded-Proto"] = "https"
            headers["Host"] = frontend_base_url.replace("https://", "").replace("http://", "")
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.api_base}/v1/auth/forgot-password",
                json={"email": email},
                headers=headers,
            )
            resp.raise_for_status()
            return _extract_data(resp.json())

    async def reset_password(self, email: str, token: str, new_password: str) -> dict:
        """Reset password using token from email via sub2api.

        POST /api/v1/auth/reset-password
        Returns: {"message": str}
        """
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.api_base}/v1/auth/reset-password",
                json={
                    "email": email,
                    "token": token,
                    "new_password": new_password,
                },
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return _extract_data(resp.json())

    async def change_password(self, user_jwt: str, current_password: str, new_password: str) -> dict:
        """Change password for authenticated user via sub2api.

        POST /api/v1/auth/change-password
        Returns: {"message": str}
        """
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.api_base}/v1/auth/change-password",
                json={
                    "current_password": current_password,
                    "new_password": new_password,
                },
                headers={
                    "Authorization": f"Bearer {user_jwt}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            return _extract_data(resp.json())

    # ===== Session Management (proxy to sub2api) =====

    async def logout(self, user_jwt: str, refresh_token: str = "") -> dict:
        """Logout user, optionally revoking a specific refresh token.

        POST /api/v1/auth/logout
        Returns: {"message": str}
        """
        body = {}
        if refresh_token:
            body["refresh_token"] = refresh_token
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.api_base}/v1/auth/logout",
                json=body,
                headers={
                    "Authorization": f"Bearer {user_jwt}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            return _extract_data(resp.json())

    async def revoke_all_sessions(self, user_jwt: str) -> dict:
        """Revoke all sessions for the authenticated user.

        POST /api/v1/auth/revoke-all-sessions
        Returns: {"message": str}
        """
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.api_base}/v1/auth/revoke-all-sessions",
                json={},
                headers={
                    "Authorization": f"Bearer {user_jwt}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            return _extract_data(resp.json())
