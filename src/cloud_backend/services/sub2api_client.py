"""
Sub2API Admin Client - Manages per-user accounts and API keys in sub2api.

Sub2api is the AI API Gateway (CRS) that handles LLM request forwarding
and per-user token usage tracking. This client uses the Admin API to:
1. Create a sub2api user when a Cloud Backend user registers
2. Create an API key for the sub2api user
3. Query per-user usage statistics
"""

import logging
import httpx

logger = logging.getLogger(__name__)


class Sub2APIClient:
    """Client for sub2api Admin API."""

    def __init__(self, base_url: str, admin_api_key: str):
        """
        Args:
            base_url: Sub2api base URL (e.g., "https://api.ariseos.com/api")
            admin_api_key: Admin API key for sub2api (x-api-key header)
        """
        self.base_url = base_url.rstrip("/")
        self.admin_api_key = admin_api_key

    def _admin_headers(self) -> dict:
        return {
            "x-api-key": self.admin_api_key,
            "Content-Type": "application/json",
        }

    async def create_user(self, email: str, password: str, username: str = "") -> dict:
        """Create a user in sub2api via Admin API.

        POST /api/v1/admin/users
        Returns: {"id": int, "email": str, "status": str, ...}
        """
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}/v1/admin/users",
                json={
                    "email": email,
                    "password": password,
                    "username": username,
                },
                headers=self._admin_headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            # sub2api wraps response in {"data": ...}
            return data.get("data", data)

    async def login_as_user(self, email: str, password: str) -> str:
        """Login as a user to get JWT token for user-facing API calls.

        POST /api/v1/auth/login
        Returns: JWT access token string
        """
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}/v1/auth/login",
                json={
                    "email": email,
                    "password": password,
                },
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            token_data = data.get("data", data)

            # sub2api may require 2FA — not expected for programmatic users
            if token_data.get("requires_2fa"):
                raise RuntimeError(
                    f"Sub2api user {email} has 2FA enabled, cannot login programmatically"
                )

            return token_data["access_token"]

    async def create_api_key_for_user(
        self, user_jwt: str, name: str = "cloud-backend"
    ) -> dict:
        """Create an API key using the user's JWT token.

        POST /api/v1/keys
        Returns: {"id": int, "key": "sk-xxx", "name": str, ...}
        """
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}/v1/keys",
                json={"name": name},
                headers={
                    "Authorization": f"Bearer {user_jwt}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", data)

    async def provision_user(self, email: str, password: str, username: str = "") -> dict:
        """Create user + API key in sub2api. Single call for registration flow.

        Handles retry: if user already exists in sub2api (e.g. from a previous
        partial failure), logs in and creates a new API key.

        Returns: {"user_id": int, "api_key": "sk-xxx"}
        """
        # 1. Create user via admin API (or handle "already exists")
        try:
            user = await self.create_user(email, password, username)
            sub2api_user_id = user["id"]
            logger.info(f"Created sub2api user: id={sub2api_user_id}, email={email}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                # User already exists in sub2api (partial failure retry)
                logger.info(f"Sub2api user already exists for {email}, proceeding to login")
                sub2api_user_id = None  # Will get from API key response
            else:
                raise

        # 2. Login as the user to get JWT
        user_jwt = await self.login_as_user(email, password)

        # 3. Create API key via user-facing API
        key_data = await self.create_api_key_for_user(user_jwt, name="ami-cloud")
        api_key = key_data["key"]

        # If we didn't get user_id from creation, get it from key data
        if sub2api_user_id is None:
            sub2api_user_id = key_data.get("user_id")

        logger.info(f"Provisioned sub2api API key for user {sub2api_user_id}")
        return {"user_id": sub2api_user_id, "api_key": api_key}

    async def get_user_usage(self, sub2api_user_id: int, period: str = "month") -> dict:
        """Get user's usage statistics via Admin API.

        GET /api/v1/admin/users/:id/usage
        Returns: {"total_requests": int, "total_cost": float, "total_tokens": int}
        """
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/v1/admin/users/{sub2api_user_id}/usage",
                params={"period": period},
                headers=self._admin_headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", data)

    async def get_user_api_keys(self, sub2api_user_id: int) -> list:
        """Get user's API keys via Admin API.

        GET /api/v1/admin/users/:id/api-keys
        Returns: list of API key objects
        """
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/v1/admin/users/{sub2api_user_id}/api-keys",
                headers=self._admin_headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", data)
