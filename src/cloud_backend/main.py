"""
Ami Cloud Backend - Memory-as-a-Service + Auth

Provides:
1. User authentication (registration, login, JWT-based auth)
2. Memory endpoints (add, query, stats, phrases, share, learn, plan)
3. Per-user LLM API keys via sub2api for token tracking and billing
"""

import uvicorn
import logging
import sys
import os
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

logger = logging.getLogger(__name__)

# Load configuration early (before creating app)
from core.config_service import CloudConfigService
config_service = CloudConfigService()

# Global service instances
storage_service = None
sub2api_client = None  # Sub2API admin client for per-user token tracking
embedding_api_key = None  # Server-side embedding API key (not per-user)
rerank_api_key = None  # Server-side rerank API key (not per-user)

# Create FastAPI application
app = FastAPI(
    title="Ami Cloud Backend",
    description="Memory-as-a-Service + Auth",
    version="3.1.0"
)

# Register structured error handlers
from api.errors import register_error_handlers, AppError, ErrorCode
register_error_handlers(app)

# Register rate limiter
from core.rate_limiter import limiter, rate_limit_handler, RATE_AUTH_LOGIN, RATE_AUTH_REGISTER, RATE_AUTH_PASSWORD_RESET, RATE_PUBLIC_DEFAULT
from slowapi.errors import RateLimitExceeded
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

# Import Pydantic schemas
from api.schemas import (
    LoginRequest, LoginResponse,
    RegisterRequest, RegisterResponse,
    RefreshTokenRequest, RefreshTokenResponse,
    CredentialsResponse, UserProfileResponse,
    ChangePasswordRequest, SuccessResponse,
    ForgotPasswordRequest, ResetPasswordRequest,
    ResendVerificationRequest, LogoutRequest,
    ApiKeyItem, ApiKeyListResponse,
    CreateApiKeyRequest, CreateApiKeyResponse,
    AdminUserItem, AdminUserListResponse,
    AdminSetPlanRequest, AdminSetActiveRequest, AdminSystemHealthResponse,
    VersionCheckRequest, VersionCheckResponse,
    MemoryAddRequest, MemoryAddResponse,
    PhraseQueryRequest, MemoryQueryRequest,
    StateByUrlRequest, SharePhraseRequest, UnpublishPhraseRequest,
    WorkflowQueryRequest, PlanRouteRequest,
    PlanWithMemoryRequest, LearnFromExecutionRequest,
    TestEmbeddingRequest, TestRerankRequest,
    ErrorResponse,
)

# Setup CORS from config (must be done before app starts)
cors_origins = config_service.get("cors.allow_origins", ["*"])
cors_credentials = config_service.get("cors.allow_credentials", True)
cors_methods = config_service.get("cors.allow_methods", ["*"])
cors_headers = config_service.get("cors.allow_headers", ["*"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=cors_credentials,
    allow_methods=cors_methods,
    allow_headers=cors_headers,
)

# Add security response headers middleware
from core.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestContextMiddleware)

# Prometheus metrics (optional, enabled if prometheus-fastapi-instrumentator is installed)
try:
    from prometheus_fastapi_instrumentator import Instrumentator
    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        excluded_handlers=["/health", "/metrics"],
    )
    instrumentator.instrument(app).expose(app, endpoint="/metrics")
    logger.info("Prometheus metrics enabled at /metrics")
except ImportError:
    pass  # prometheus-fastapi-instrumentator not installed, skip


# ===== JWT Auth Dependency =====

security = HTTPBearer(auto_error=False)


async def get_current_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    """FastAPI dependency: extract user_id from JWT access token."""
    if credentials is None:
        raise AppError(ErrorCode.AUTH_REQUIRED, "Authentication required", status_code=401)
    from api.auth import auth_service
    payload = auth_service.verify_token(credentials.credentials, expected_type="access")
    if payload is None:
        raise AppError(ErrorCode.AUTH_INVALID_TOKEN, "Invalid or expired token", status_code=401)
    user_id = payload.get("sub")
    if not user_id:
        raise AppError(ErrorCode.AUTH_INVALID_TOKEN, "Token missing user identity", status_code=401)
    return user_id


async def get_sub2api_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[str]:
    """FastAPI dependency: extract embedded sub2api JWT from our access token.

    Returns None if the token doesn't contain a sub2api JWT (e.g., old tokens).
    """
    if credentials is None:
        return None
    from api.auth import auth_service
    payload = auth_service.verify_token(credentials.credentials, expected_type="access")
    if payload is None:
        return None
    return payload.get("s2a")


async def get_user_llm_api_key(
    user_id: str = Depends(get_current_user_id),
) -> str:
    """FastAPI dependency: get per-user sub2api API key from sub2api."""
    try:
        api_key = await sub2api_client.get_first_api_key(int(user_id))
    except Exception as e:
        logger.error(f"Failed to get API key for user {user_id}: {e}")
        raise AppError(
            ErrorCode.SERVICE_SUB2API_FAILED,
            "Failed to retrieve API key from gateway",
            status_code=502,
        )
    if api_key:
        return api_key
    raise AppError(
        ErrorCode.AUTH_NO_API_KEY,
        "User has no API key. Please contact admin to provision your account.",
        status_code=403,
    )


# ===== Startup / Shutdown =====

@app.on_event("startup")
async def startup_event():
    """Startup initialization"""
    global storage_service, sub2api_client

    print("\n" + "="*80)
    print("Ami Cloud Backend Starting...")
    print("="*80)
    print(f"Config: {config_service.config_path}")

    try:
        from services.storage_service import StorageService
        from src.common.memory.memory_service import MemoryServiceConfig, init_memory_services

        # 1. CORS already configured
        print(f"CORS: {len(cors_origins)} allowed origins")

        # 2. Initialize storage service
        storage_base_path = config_service.get_storage_path()
        storage_service = StorageService(base_path=str(storage_base_path))
        print(f"Storage: {storage_service.base_path}")

        # 3. No local database — all user data is in sub2api's PostgreSQL
        print("Database: using sub2api PostgreSQL (no local users table)")

        # 4. Initialize Memory Services (multi-tenant: private + public)
        graph_config = config_service.get("graph_store", {})
        memory_config = config_service.get("memory", {})

        base_config = MemoryServiceConfig(
            graph_backend=graph_config.get("backend", "surrealdb"),
            graph_url=graph_config.get("url") or os.getenv("SURREALDB_URL", "ws://localhost:8000/rpc"),
            graph_namespace=graph_config.get("namespace") or os.getenv("SURREALDB_NAMESPACE", "ami"),
            graph_database="public",
            graph_username=graph_config.get("username") or os.getenv("SURREALDB_USER", "root"),
            graph_password=graph_config.get("password") or os.getenv("SURREALDB_PASSWORD", ""),
            vector_dimensions=graph_config.get("vector_dimensions", 1024),
            intent_sequence_dedup_threshold=memory_config.get("intent_sequence_dedup_threshold"),
        )
        init_memory_services(base_config)
        print(f"Memory Services: multi-tenant ({base_config.graph_backend})")

        # 5. Validate required config (no fallback defaults for sensitive values)
        required_configs = [
            "llm.proxy_url",
            "llm.anthropic.model",
            "embedding.base_url",
            "embedding.model",
            "embedding.dimension",
        ]
        for key in required_configs:
            if not config_service.get(key):
                print(f"FATAL: Required config '{key}' not set in cloud-backend.yaml")
                sys.exit(1)
        print(f"Config validated: LLM proxy={config_service.get('llm.proxy_url')}")

        # 5b. Load server-side API keys for embedding and rerank (not per-user)
        global embedding_api_key, rerank_api_key

        embedding_key_env = config_service.get("embedding.api_key_env", "EMBEDDING_API_KEY")
        embedding_api_key = os.environ.get(embedding_key_env)
        if not embedding_api_key:
            print(f"FATAL: {embedding_key_env} environment variable required for embedding service")
            sys.exit(1)
        print(f"Embedding: server-side key loaded from ${embedding_key_env}")

        rerank_key_env = config_service.get("rerank.api_key_env", "RERANK_API_KEY")
        rerank_api_key = os.environ.get(rerank_key_env)
        if rerank_api_key:
            print(f"Rerank: server-side key loaded from ${rerank_key_env}")
        else:
            print(f"Rerank: ${rerank_key_env} not set, rerank service disabled")

        # 6. Initialize sub2api client (per-user API key provisioning + token tracking)
        sub2api_admin_key_env = config_service.get("sub2api.admin_api_key_env", "SUB2API_ADMIN_API_KEY")
        sub2api_admin_key = os.environ.get(sub2api_admin_key_env)
        if not sub2api_admin_key:
            print(f"FATAL: {sub2api_admin_key_env} environment variable required")
            sys.exit(1)

        from services.sub2api_client import Sub2APIClient
        sub2api_client = Sub2APIClient(
            base_url=config_service.get("llm.proxy_url"),
            admin_api_key=sub2api_admin_key,
        )
        print(f"Sub2API: per-user token tracking enabled")

        # 7. Reasoner ready for per-request initialization
        print("Reasoner (ready for initialization)")

        # 8. Setup structured logging
        log_level = config_service.get("logging.level", "INFO")
        json_logging = config_service.get("logging.json_format", True)
        log_file = config_service.get("logging.file", None)
        max_bytes = config_service.get("logging.max_bytes", 100 * 1024 * 1024)
        backup_count = config_service.get("logging.backup_count", 5)
        loki_url = config_service.get("logging.loki_url", None)

        from core.logging_config import setup_logging
        setup_logging(
            service_name="cloud_backend",
            level=log_level,
            json_format=json_logging,
            log_file=log_file,
            max_bytes=max_bytes,
            backup_count=backup_count,
            loki_url=loki_url,
        )
        log_info = f"Logging: {log_level} (JSON={json_logging})"
        if log_file:
            log_info += f" -> {log_file}"
        print(log_info)

        print("="*80)
        print("Cloud Backend Ready!")
        print(f"  Server: http://{config_service.get('server.host')}:{config_service.get('server.port')}")
        print(f"  Docs: http://localhost:{config_service.get('server.port')}/docs")
        print("="*80 + "\n")

    except SystemExit:
        raise
    except Exception as e:
        print(f"FATAL: Failed to initialize services: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    print("Cloud Backend shutdown complete")


# ===== Health Check =====

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "cloud-backend",
        "version": "3.1.0"
    }


@app.get("/")
def root():
    return {
        "service": "Ami Cloud Backend",
        "version": "3.1.0",
        "docs": "/docs"
    }


@app.post("/api/v1/test/embedding")
async def test_embedding(
    data: TestEmbeddingRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Test embedding service connectivity."""
    from src.common.llm import get_cached_embedding_service
    service = get_cached_embedding_service(
        api_key=embedding_api_key,
        base_url=config_service.get("embedding.base_url"),
        model=config_service.get("embedding.model"),
        dimension=config_service.get("embedding.dimension"),
    )
    result = service.embed(data.text)
    return {
        "success": True,
        "model": result.model,
        "dimension": result.dimension,
        "usage": result.usage,
        "embedding_preview": result.to_list()[:5],
    }


@app.post("/api/v1/test/rerank")
async def test_rerank(
    data: TestRerankRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Test rerank service connectivity."""
    if not rerank_api_key:
        raise AppError(
            ErrorCode.SERVICE_RERANK_DISABLED,
            "Rerank service not configured (RERANK_API_KEY not set)",
            status_code=503,
        )
    from src.common.memory.services.rerank_model.maas_rerank_model import MaaSRerankModel
    model = MaaSRerankModel(
        model_name=config_service.get("rerank.model", "BAAI/bge-reranker-v2-m3"),
        api_key=rerank_api_key,
        base_url=config_service.get("rerank.base_url"),
    )
    result = model.rerank(data.query, data.documents)
    return {
        "success": True,
        "model": result.model,
        "results": [{"index": r.index, "score": r.score, "document": r.document} for r in result.results],
    }


# ===== Version Check API =====

def get_minimum_app_version() -> str:
    return config_service.get("app.minimum_version", "0.0.1")

def parse_version(version: str) -> tuple:
    try:
        parts = version.split(".")
        return tuple(int(p) for p in parts)
    except (ValueError, AttributeError):
        return (0, 0, 0)

def is_version_compatible(client_version: str, minimum_version: str) -> bool:
    return parse_version(client_version) >= parse_version(minimum_version)


@app.post("/api/v1/app/version-check", response_model=VersionCheckResponse)
async def check_app_version(data: VersionCheckRequest):
    """Check if app version is compatible"""
    minimum_version = get_minimum_app_version()
    compatible = is_version_compatible(data.version, minimum_version)

    response = VersionCheckResponse(
        compatible=compatible,
        minimum_version=minimum_version,
        client_version=data.version,
    )

    if not compatible:
        base_url = "http://download.ariseos.com/releases/latest"
        platform_urls = {
            "macos-arm64": f"{base_url}/macos-arm64/Ami-latest-macos-arm64.dmg",
            "windows-x64": f"{base_url}/windows-x64/Ami-latest-windows-x64.zip",
        }
        response.update_url = platform_urls.get(data.platform, base_url)
        response.message = f"Please update Ami to version {minimum_version} or later"
        logger.info(f"Version check: {data.version} < {minimum_version} (platform: {data.platform})")
    else:
        logger.debug(f"Version check: {data.version} is compatible")

    return response


# ===== Auth API =====

@app.post("/api/v1/auth/login", response_model=LoginResponse)
@limiter.limit(RATE_AUTH_LOGIN)
async def login(request: Request, data: LoginRequest):
    """User login — delegates authentication to sub2api."""
    from api.auth import auth_service

    import httpx

    # Sub2api login requires email (not username). If user provided a username,
    # resolve it to email via admin API first.
    login_email = data.username
    if "@" not in data.username:
        try:
            from services.sub2api_client import _extract_items
            result = await sub2api_client.list_users(page=1, per_page=1, search=data.username)
            users = _extract_items(result)
            if users:
                # Find exact username match (search is fuzzy)
                for u in users:
                    if u.get("username") == data.username:
                        login_email = u.get("email", data.username)
                        break
        except Exception:
            pass  # If admin lookup fails, try with the raw input

    try:
        sub2api_data = await sub2api_client.login(login_email, data.password)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise AppError(ErrorCode.AUTH_INVALID_CREDENTIALS, "Invalid credentials", status_code=401)
        logger.error(f"Sub2api login error for {data.username}: {e.response.status_code}")
        raise AppError(ErrorCode.SERVICE_SUB2API_FAILED, "Authentication service error", status_code=502)
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        logger.error(f"Sub2api unreachable during login: {e}")
        raise AppError(ErrorCode.SERVICE_SUB2API_FAILED, "Authentication service unavailable", status_code=502)
    except Exception as e:
        logger.warning(f"Login failed for {data.username}: {e}")
        raise AppError(ErrorCode.AUTH_INVALID_CREDENTIALS, "Invalid credentials", status_code=401)

    sub2api_jwt = sub2api_data["access_token"]

    # Decode sub2api JWT to extract user ID (we don't validate — sub2api already did)
    import json, base64
    try:
        payload_b64 = sub2api_jwt.split(".")[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        sub2api_payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        sub2api_user_id = sub2api_payload.get("id") or sub2api_payload.get("sub") or sub2api_payload.get("user_id")
    except Exception:
        logger.error("Failed to decode sub2api JWT payload")
        raise AppError(ErrorCode.SERVICE_SUB2API_FAILED, "Login succeeded but failed to extract user info", status_code=502)

    if sub2api_user_id is None:
        logger.error(f"Sub2api JWT missing user ID. Payload keys: {list(sub2api_payload.keys())}")
        raise AppError(ErrorCode.SERVICE_SUB2API_FAILED, "Login succeeded but user ID not found in token", status_code=502)

    # Get username and email from sub2api
    user_email = login_email
    try:
        user_info = await sub2api_client.get_user(int(sub2api_user_id))
        username = user_info.get("username") or user_info.get("email", "")
        user_email = user_info.get("email", login_email)
    except Exception:
        username = data.username

    # Issue our own JWT tokens with sub2api user ID as the subject
    # Embed sub2api JWT so we can proxy user-facing operations (e.g., create API key)
    token_data = {
        "sub": str(sub2api_user_id),
        "username": username,
        "s2a": sub2api_jwt,
    }
    access_token = auth_service.create_access_token(token_data)
    refresh_token = auth_service.create_refresh_token(token_data)

    logger.info(f"User login: {username} (sub2api_id={sub2api_user_id})")
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=str(sub2api_user_id),
        username=username,
        email=user_email,
    )


@app.post("/api/v1/auth/register", response_model=RegisterResponse)
@limiter.limit(RATE_AUTH_REGISTER)
async def register(request: Request, data: RegisterRequest):
    """User registration — creates user in sub2api + provisions API key."""
    from api.auth import auth_service
    import httpx

    try:
        result = await sub2api_client.register(
            email=data.email, password=data.password, username=data.username,
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 409:
            raise AppError(ErrorCode.AUTH_EMAIL_EXISTS, "Email already exists", status_code=409)
        logger.error(f"Registration failed for {data.username}: {e}")
        raise AppError(ErrorCode.SERVICE_SUB2API_FAILED, "Failed to create account", status_code=502)
    except Exception as e:
        logger.error(f"Registration failed for {data.username}: {e}")
        raise AppError(ErrorCode.SERVICE_SUB2API_FAILED, "Failed to create account", status_code=502)

    sub2api_user_id = result.get("user_id")
    if not sub2api_user_id:
        logger.error(f"Registration returned no user_id: {result}")
        raise AppError(ErrorCode.SERVICE_SUB2API_FAILED, "Registration succeeded but user ID missing", status_code=502)

    sub2api_access_token = result.get("access_token", "")
    if not sub2api_access_token:
        logger.warning(f"Registration returned no access_token for user {sub2api_user_id}")

    # Issue our own JWT tokens, embedding the sub2api JWT for proxied operations
    token_data = {
        "sub": str(sub2api_user_id),
        "username": data.username,
    }
    if sub2api_access_token:
        token_data["s2a"] = sub2api_access_token
    access_token = auth_service.create_access_token(token_data)
    refresh_token = auth_service.create_refresh_token(token_data)

    logger.info(f"User registered: {data.username} (sub2api_id={sub2api_user_id})")
    return RegisterResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=str(sub2api_user_id),
        username=data.username,
        email=data.email,
    )


@app.post("/api/v1/auth/refresh", response_model=RefreshTokenResponse)
async def refresh_token(data: RefreshTokenRequest):
    """Refresh access token using a valid refresh token."""
    from api.auth import auth_service

    payload = auth_service.verify_token(data.refresh_token, expected_type="refresh")
    if payload is None:
        raise AppError(
            ErrorCode.AUTH_REFRESH_FAILED,
            "Invalid or expired refresh token",
            status_code=401,
        )

    user_id = payload.get("sub")
    username = payload.get("username")
    if not user_id:
        raise AppError(
            ErrorCode.AUTH_INVALID_TOKEN,
            "Token missing user identity",
            status_code=401,
        )

    # Preserve the embedded sub2api JWT across token refreshes
    token_data = {"sub": user_id, "username": username}
    s2a = payload.get("s2a")
    if s2a:
        token_data["s2a"] = s2a
    access_token = auth_service.create_access_token(token_data)
    return RefreshTokenResponse(access_token=access_token)


@app.get("/api/v1/auth/credentials", response_model=CredentialsResponse)
async def get_credentials(user_id: str = Depends(get_current_user_id)):
    """Return LLM API key for the authenticated user."""
    api_key = await sub2api_client.get_first_api_key(int(user_id))
    if not api_key:
        raise AppError(
            ErrorCode.AUTH_NO_API_KEY,
            "User has no API key provisioned",
            status_code=403,
        )
    return CredentialsResponse(api_key=api_key)


@app.get("/api/v1/auth/me", response_model=UserProfileResponse)
async def get_me(
    user_id: str = Depends(get_current_user_id),
):
    """Get current user profile from sub2api."""
    try:
        user = await sub2api_client.get_user(int(user_id))
    except Exception as e:
        logger.error(f"Failed to get user profile from sub2api: {e}")
        raise AppError(ErrorCode.AUTH_USER_NOT_FOUND, "User not found", status_code=404)

    # Determine plan from subscriptions
    plan = "free"
    try:
        from services.sub2api_client import _extract_items
        subs_raw = await sub2api_client.get_user_subscriptions(int(user_id))
        subs_list = _extract_items(subs_raw)
        if subs_list:
            # Use the first active subscription's group name as the plan
            for sub in subs_list:
                if sub.get("status") == "active":
                    group_name = sub.get("group_name") or sub.get("group", {}).get("name", "")
                    if group_name:
                        plan = group_name
                    break
    except Exception as e:
        logger.warning(f"Failed to fetch subscriptions for user {user_id}: {e}")

    return UserProfileResponse(
        user_id=str(user.get("id")),
        username=user.get("username", ""),
        email=user.get("email", ""),
        role=user.get("role", "user"),
        status=user.get("status", "active"),
        plan=plan,
        created_at=user.get("created_at"),
    )


@app.post("/api/v1/auth/change-password", response_model=SuccessResponse)
async def change_password(
    data: ChangePasswordRequest,
    user_id: str = Depends(get_current_user_id),
    sub2api_token: Optional[str] = Depends(get_sub2api_token),
):
    """Change current user's password via sub2api."""
    import httpx

    async def _get_fresh_jwt() -> str:
        """Login with current password to get a fresh sub2api JWT."""
        user_info = await sub2api_client.get_user(int(user_id))
        email = user_info.get("email")
        sub2api_data = await sub2api_client.login(email, data.current_password)
        return sub2api_data["access_token"]

    try:
        user_jwt = None

        # Try embedded sub2api JWT first
        if sub2api_token:
            try:
                await sub2api_client.change_password(sub2api_token, data.current_password, data.new_password)
                logger.info(f"Password changed for user {user_id}")
                return SuccessResponse()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    # s2a expired, fall through to re-login
                    logger.info(f"s2a expired for user {user_id}, falling back to re-login for password change")
                else:
                    raise

        # Fallback: login with current password to get fresh JWT
        user_jwt = await _get_fresh_jwt()
        await sub2api_client.change_password(user_jwt, data.current_password, data.new_password)

        logger.info(f"Password changed for user {user_id}")
        return SuccessResponse()
    except AppError:
        raise
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise AppError(
                ErrorCode.AUTH_INVALID_PASSWORD,
                "Invalid current password",
                status_code=401,
            )
        logger.error(f"Password change failed for user {user_id}: {e}")
        raise AppError(ErrorCode.SERVICE_SUB2API_FAILED, "Password change failed", status_code=502)
    except Exception as e:
        error_msg = str(e)
        if "401" in error_msg or "invalid" in error_msg.lower() or "password" in error_msg.lower():
            raise AppError(
                ErrorCode.AUTH_INVALID_PASSWORD,
                "Invalid current password",
                status_code=401,
            )
        logger.error(f"Password change failed for user {user_id}: {e}")
        raise AppError(ErrorCode.SERVICE_SUB2API_FAILED, "Password change failed", status_code=502)


# ===== Email Verification (proxy to sub2api) =====

@app.post("/api/v1/auth/send-verify-code", response_model=SuccessResponse)
@limiter.limit(RATE_AUTH_PASSWORD_RESET)
async def send_verify_code(request: Request, data: ResendVerificationRequest):
    """Send email verification code. Proxied to sub2api."""
    try:
        result = await sub2api_client.send_verify_code(data.email)
        return SuccessResponse(message=result.get("message", "Verification code sent"))
    except Exception as e:
        logger.error(f"Failed to send verification code: {e}")
        raise AppError(ErrorCode.SERVICE_SUB2API_FAILED, "Failed to send verification code", status_code=502)


# ===== Password Reset (proxy to sub2api) =====

@app.post("/api/v1/auth/forgot-password", response_model=SuccessResponse)
@limiter.limit(RATE_AUTH_PASSWORD_RESET)
async def forgot_password(request: Request, data: ForgotPasswordRequest):
    """Request password reset email. Proxied to sub2api.
    Always returns success to prevent email enumeration."""
    try:
        frontend_base_url = config_service.get("email.base_url", "")
        result = await sub2api_client.forgot_password(data.email, frontend_base_url)
        return SuccessResponse(
            message=result.get("message", "If your email is registered, you will receive a password reset link shortly.")
        )
    except Exception as e:
        logger.error(f"Forgot password request failed: {e}")
        # Still return success to prevent email enumeration
        return SuccessResponse(
            message="If your email is registered, you will receive a password reset link shortly."
        )


@app.post("/api/v1/auth/reset-password", response_model=SuccessResponse)
@limiter.limit(RATE_AUTH_PASSWORD_RESET)
async def reset_password(request: Request, data: ResetPasswordRequest):
    """Reset password using token from email. Proxied to sub2api."""
    try:
        result = await sub2api_client.reset_password(data.email, data.token, data.new_password)
        return SuccessResponse(message=result.get("message", "Password reset successfully"))
    except Exception as e:
        logger.error(f"Password reset failed: {e}")
        raise AppError(
            ErrorCode.SERVICE_SUB2API_FAILED,
            "Password reset failed",
            status_code=502,
        )


# ===== Session Management (proxy to sub2api) =====

@app.post("/api/v1/auth/logout", response_model=SuccessResponse)
async def logout(
    data: LogoutRequest,
    user_id: str = Depends(get_current_user_id),
    sub2api_token: Optional[str] = Depends(get_sub2api_token),
):
    """Logout user, optionally revoking a specific refresh token. Proxied to sub2api."""
    if sub2api_token:
        try:
            await sub2api_client.logout(sub2api_token, data.refresh_token or "")
            logger.info(f"User {user_id} logged out (sub2api session revoked)")
        except Exception as e:
            logger.warning(f"Sub2api logout failed (non-fatal): {e}")
    else:
        logger.info(f"User {user_id} logged out (no sub2api token, local only)")
    return SuccessResponse(message="Logged out successfully")


@app.post("/api/v1/auth/revoke-all-sessions", response_model=SuccessResponse)
async def revoke_all_sessions(
    user_id: str = Depends(get_current_user_id),
    sub2api_token: Optional[str] = Depends(get_sub2api_token),
):
    """Revoke all sessions for current user. Proxied to sub2api."""
    if sub2api_token:
        try:
            await sub2api_client.revoke_all_sessions(sub2api_token)
            logger.info(f"All sessions revoked for user {user_id} (sub2api)")
        except Exception as e:
            logger.warning(f"Sub2api revoke-all-sessions failed (non-fatal): {e}")
    else:
        logger.info(f"Session revocation requested for user {user_id} (no sub2api token)")
    return SuccessResponse(message="All sessions revoked. Please log in again.")


# ===== API Key Self-Service Management =====

@app.get("/api/v1/keys", response_model=ApiKeyListResponse)
async def list_api_keys(
    user_id: str = Depends(get_current_user_id),
):
    """List user's API keys from sub2api."""
    from services.sub2api_client import _extract_items
    raw_keys = await sub2api_client.get_user_api_keys(int(user_id))

    keys = []
    for k in _extract_items(raw_keys):
        key_val = k.get("key", "")
        if len(key_val) > 8:
            preview = key_val[:5] + "..." + key_val[-4:]
        else:
            preview = key_val[:3] + "..."
        keys.append(ApiKeyItem(
            id=k.get("id"),
            name=k.get("name", "unnamed"),
            key_preview=preview,
            created_at=k.get("created_at"),
        ))

    return ApiKeyListResponse(keys=keys)


@app.post("/api/v1/keys", response_model=CreateApiKeyResponse)
async def create_api_key(
    data: CreateApiKeyRequest,
    user_id: str = Depends(get_current_user_id),
    sub2api_token: Optional[str] = Depends(get_sub2api_token),
):
    """Create a new API key for the user via sub2api.

    Uses the sub2api JWT embedded in the Cloud Backend access token
    (set during login) to call sub2api's user-facing key creation endpoint.
    """
    if not sub2api_token:
        raise AppError(
            ErrorCode.AUTH_INVALID_TOKEN,
            "Session does not contain sub2api credentials. Please re-login.",
            status_code=401,
        )

    import httpx
    try:
        key_data = await sub2api_client.create_api_key_for_user(sub2api_token, name=data.name)

        logger.info(f"API key created for user {user_id}: name={data.name}")
        return CreateApiKeyResponse(
            key=key_data["key"],
            name=data.name,
            id=key_data.get("id"),
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise AppError(
                ErrorCode.AUTH_INVALID_TOKEN,
                "Sub2api session expired. Please re-login to create API keys.",
                status_code=401,
            )
        logger.error(f"Failed to create API key: {e}")
        raise AppError(ErrorCode.SERVICE_SUB2API_FAILED, "Failed to create API key", status_code=502)
    except AppError:
        raise
    except Exception as e:
        logger.error(f"Failed to create API key: {e}")
        raise AppError(ErrorCode.SERVICE_SUB2API_FAILED, "Failed to create API key", status_code=502)


@app.delete("/api/v1/keys/{key_id}", response_model=SuccessResponse)
async def revoke_api_key(
    key_id: int,
    user_id: str = Depends(get_current_user_id),
):
    """Revoke (delete) an API key via sub2api."""
    try:
        await sub2api_client.delete_api_key(int(user_id), key_id)
        logger.info(f"API key {key_id} revoked for user {user_id}")
        return SuccessResponse(message="API key revoked")
    except Exception as e:
        logger.error(f"Failed to revoke API key: {e}")
        raise AppError(ErrorCode.SERVICE_SUB2API_FAILED, "Failed to revoke API key", status_code=502)


# ===== Admin API =====

async def require_admin(user_id: str = Depends(get_current_user_id)) -> str:
    """FastAPI dependency: require admin role. Checks sub2api user role."""
    try:
        user = await sub2api_client.get_user(int(user_id))
        if user.get("role") != "admin":
            raise AppError(ErrorCode.FORBIDDEN, "Admin access required", status_code=403)
        return user_id
    except AppError:
        raise
    except Exception:
        raise AppError(ErrorCode.FORBIDDEN, "Admin access required", status_code=403)


@app.get("/api/v1/admin/users", response_model=AdminUserListResponse)
async def admin_list_users(
    page: int = 1,
    per_page: int = 50,
    search: Optional[str] = None,
    admin_id: str = Depends(require_admin),
):
    """List all users (admin only) — data from sub2api."""
    try:
        from services.sub2api_client import _extract_items, _extract_total
        result = await sub2api_client.list_users(page, per_page, search or "")
        raw_users = _extract_items(result)
        total = _extract_total(result, raw_users)

        items = []
        for u in raw_users:
            items.append(AdminUserItem(
                user_id=str(u.get("id")),
                username=u.get("username", ""),
                email=u.get("email", ""),
                plan="free",  # Plan comes from subscriptions, simplified for list view
                is_active=u.get("status") == "active",
                is_admin=u.get("role") == "admin",
                created_at=u.get("created_at"),
            ))

        return AdminUserListResponse(users=items, total=total)
    except Exception as e:
        logger.error(f"Admin list users failed: {e}")
        raise AppError(
            ErrorCode.SERVICE_SUB2API_FAILED,
            "Failed to list users",
            status_code=502,
        )


@app.put("/api/v1/admin/users/{target_user_id}/plan")
async def admin_set_plan(
    target_user_id: int,
    data: AdminSetPlanRequest,
    admin_id: str = Depends(require_admin),
):
    """Set user's subscription plan (admin only).
    Maps plan name to sub2api group subscription."""
    # Not yet implemented — requires sub2api group/subscription configuration
    raise AppError(
        ErrorCode.INTERNAL_ERROR,
        "Plan management is not yet implemented. Configure sub2api groups first.",
        status_code=501,
    )


@app.put("/api/v1/admin/users/{target_user_id}/active", response_model=SuccessResponse)
async def admin_set_active(
    target_user_id: int,
    data: AdminSetActiveRequest,
    admin_id: str = Depends(require_admin),
):
    """Enable or disable a user account (admin only)."""
    try:
        new_status = "active" if data.is_active else "disabled"
        await sub2api_client.update_user(target_user_id, status=new_status)

        action = "enabled" if data.is_active else "disabled"
        logger.info(f"Admin {admin_id} {action} user {target_user_id}")
        return SuccessResponse(message=f"User {action}")
    except Exception as e:
        logger.error(f"Failed to update user status: {e}")
        raise AppError(
            ErrorCode.SERVICE_SUB2API_FAILED,
            "Failed to update user status",
            status_code=502,
        )


@app.get("/api/v1/admin/health", response_model=AdminSystemHealthResponse)
async def admin_system_health(
    admin_id: str = Depends(require_admin),
):
    """Get system health status (admin only)."""
    surreal_status = "not_configured"
    sub2api_status = "ok"
    users_total = 0
    users_active = 0

    # Get user counts from sub2api
    try:
        from services.sub2api_client import _extract_items, _extract_total
        result = await sub2api_client.list_users(1, 1)
        users_total = _extract_total(result, _extract_items(result))
        # Active count not directly available from sub2api list, use total as approximation
        users_active = users_total
    except Exception as e:
        sub2api_status = f"error: {e}"

    # Check SurrealDB
    try:
        from src.common.memory.memory_service import get_public_memory
        pub = get_public_memory()
        if pub and pub.workflow_memory:
            gs = pub.workflow_memory.state_manager.graph_store
            if hasattr(gs, 'run_script'):
                gs.run_script("SELECT 1")
                surreal_status = "ok"
    except Exception as e:
        surreal_status = f"error: {e}"

    # Check sub2api connectivity
    if sub2api_status == "ok":
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{sub2api_client.base_url}/health")
                if resp.status_code != 200:
                    sub2api_status = f"error: HTTP {resp.status_code}"
        except Exception as e:
            sub2api_status = f"error: {e}"

    return AdminSystemHealthResponse(
        database="ok (sub2api PostgreSQL)",
        surrealdb=surreal_status,
        sub2api=sub2api_status,
        users_total=users_total,
        users_active=users_active,
    )


# ===== Memory API =====

@app.post("/api/v1/memory/add", response_model=MemoryAddResponse)
async def add_to_memory(
    data: MemoryAddRequest,
    user_id: str = Depends(get_current_user_id),
    llm_api_key: str = Depends(get_user_llm_api_key),
):
    """Add Operations to User's Workflow Memory"""
    import time
    start_time = time.time()

    try:
        from src.common.memory.thinker.workflow_processor import WorkflowProcessor

        # Setup embedding service with server-side API key
        embedding_service = None
        if data.generate_embeddings:
            from src.common.llm import get_cached_embedding_service
            embedding_service = get_cached_embedding_service(
                api_key=embedding_api_key,
                base_url=config_service.get("embedding.base_url"),
                model=config_service.get("embedding.model"),
                dimension=config_service.get("embedding.dimension"),
            )

        # Setup LLM providers with per-user API key
        llm_provider = None
        simple_llm_provider = None
        if data.generate_embeddings:
            from src.common.llm import get_cached_anthropic_provider
            llm_provider = get_cached_anthropic_provider(
                api_key=llm_api_key,
                model=config_service.get("llm.anthropic.model"),
                base_url=config_service.get("llm.proxy_url")
            )
            simple_model = config_service.get("llm.anthropic.simple_model")
            if simple_model:
                simple_llm_provider = get_cached_anthropic_provider(
                    api_key=llm_api_key,
                    model=simple_model,
                    base_url=config_service.get("llm.proxy_url")
                )
            else:
                simple_llm_provider = llm_provider

        # Create processor with user's private memory
        from src.common.memory.memory_service import get_private_memory
        user_memory = get_private_memory(user_id)

        processor = WorkflowProcessor(
            llm_provider=llm_provider,
            memory=user_memory.workflow_memory,
            embedding_service=embedding_service,
            simple_llm_provider=simple_llm_provider,
        )

        result = await processor.process_workflow(
            workflow_data={"operations": data.operations},
            session_id=data.session_id,
            store_to_memory=True,
            snapshots=data.snapshots,
            skip_cognitive_phrase=data.skip_cognitive_phrase,
        )

        processing_time_ms = int((time.time() - start_time) * 1000)

        logger.info(f"Added to memory for user {user_id}: "
                   f"{result.metadata.get('new_states', 0)} new states, "
                   f"{result.metadata.get('reused_states', 0)} merged, "
                   f"{len(result.intent_sequences)} sequences")

        return MemoryAddResponse(
            states_added=result.metadata.get("new_states", 0),
            states_merged=result.metadata.get("reused_states", 0),
            page_instances_added=len(result.page_instances),
            intent_sequences_added=len(result.intent_sequences),
            actions_added=len(result.actions),
            processing_time_ms=processing_time_ms,
        )

    except AppError:
        raise
    except Exception as e:
        logger.error(f"Failed to add to memory: {e}", exc_info=True)
        raise AppError(
            ErrorCode.MEMORY_OPERATION_FAILED,
            f"Failed to add to memory: {str(e)}",
            status_code=500,
        )


@app.post("/api/v1/memory/phrase/query")
async def query_cognitive_phrase(
    data: PhraseQueryRequest,
    user_id: str = Depends(get_current_user_id),
    llm_api_key: str = Depends(get_user_llm_api_key),
):
    """Query CognitivePhrase (User-Recorded Complete Workflow)"""
    try:
        from src.common.memory.memory_service import get_private_memory, get_public_memory

        user_reasoner = await _get_reasoner_for_user(user_id, llm_api_key=llm_api_key)

        private_wm = get_private_memory(user_id).workflow_memory
        public_memory_service = get_public_memory()
        public_wm = public_memory_service.workflow_memory if public_memory_service else None

        private_phrases = private_wm.phrase_manager.list_phrases()
        public_phrases = public_wm.phrase_manager.list_phrases() if public_wm else []

        if private_phrases or public_phrases:
            can_satisfy, matching_phrases, reasoning, source = (
                await user_reasoner.phrase_checker.check_merged(
                    data.query, private_phrases, public_phrases
                )
            )
        else:
            can_satisfy, matching_phrases, reasoning, source = False, [], "No phrases", "private"

        if not can_satisfy or not matching_phrases:
            logger.info(f"No CognitivePhrase found for: {data.query[:50]}...")
            return {
                "success": True,
                "phrase": None,
                "reasoning": reasoning,
                "source": "none",
            }

        phrase = matching_phrases[0]
        wm = public_wm if source == "public" and public_wm else private_wm

        if source == "public" and public_wm:
            try:
                public_wm.phrase_manager.increment_use_count(phrase.id)
            except Exception as uc_err:
                logger.warning(f"Failed to increment use_count: {uc_err}")

        states = []
        for state_id in phrase.state_path:
            state = wm.state_manager.get_state(state_id)
            if state:
                states.append(state.to_dict() if hasattr(state, 'to_dict') else state)

        actions = []
        for i in range(len(phrase.state_path) - 1):
            source_id = phrase.state_path[i]
            target_id = phrase.state_path[i + 1]
            action = wm.action_manager.get_action(source_id, target_id)
            if action:
                actions.append(action.to_dict() if hasattr(action, 'to_dict') else action)

        phrase_dict = phrase.to_dict() if hasattr(phrase, 'to_dict') else phrase
        phrase_dict["states"] = states
        phrase_dict["actions"] = actions

        logger.info(f"Found CognitivePhrase for '{data.query[:30]}...': {phrase.id} (source={source}) with {len(states)} states")

        return {
            "success": True,
            "phrase": phrase_dict,
            "reasoning": reasoning,
            "source": source,
        }

    except AppError:
        raise
    except Exception as e:
        logger.error(f"CognitivePhrase query failed: {e}", exc_info=True)
        raise AppError(
            ErrorCode.MEMORY_OPERATION_FAILED,
            f"CognitivePhrase query failed: {str(e)}",
            status_code=500,
        )


@app.post("/api/v1/memory/query")
async def query_memory(
    data: MemoryQueryRequest,
    user_id: str = Depends(get_current_user_id),
    llm_api_key: str = Depends(get_user_llm_api_key),
):
    """Unified Memory Query - Task, Navigation, and Action queries"""
    try:
        user_reasoner = await _get_reasoner_for_user(user_id, llm_api_key=llm_api_key)

        result = await user_reasoner.query(
            target=data.target,
            current_state=data.current_state,
            start_state=data.start_state,
            end_state=data.end_state,
            as_type=data.as_type,
            top_k=data.top_k,
        )

        source = result.metadata.get("source", "private")

        intent_seq_used = result.query_type == "action"
        intent_seq_count = len(result.intent_sequences) if result.intent_sequences else 0
        logger.info(
            f"[MemoryQuery] type={result.query_type}, success={result.success}, "
            f"source={source}, "
            f"uses_intent_sequences={intent_seq_used}, intent_sequences={intent_seq_count}"
        )

        def _serialize(obj):
            d = obj.to_dict() if hasattr(obj, 'to_dict') else obj
            if isinstance(d, dict):
                d.pop("embedding_vector", None)
            return d

        response = {
            "success": result.success,
            "query_type": result.query_type,
            "source": source,
            "metadata": result.metadata,
        }

        if result.query_type == "task":
            response["states"] = [_serialize(s) for s in result.states]
            response["actions"] = [_serialize(a) for a in result.actions]
            if result.cognitive_phrase:
                response["cognitive_phrase"] = _serialize(result.cognitive_phrase)
            if result.execution_plan:
                response["execution_plan"] = [
                    step.model_dump() if hasattr(step, 'model_dump') else step
                    for step in result.execution_plan
                ]
            if result.subtasks:
                response["subtasks"] = [
                    {
                        "task_id": st.task_id,
                        "target": st.target,
                        "found": st.found,
                        "path_state_indices": st.path_state_indices,
                    }
                    for st in result.subtasks
                ]

        elif result.query_type == "navigation":
            response["states"] = [_serialize(s) for s in result.states]
            response["actions"] = [_serialize(a) for a in result.actions]

        elif result.query_type == "action":
            response["intent_sequences"] = [_serialize(seq) for seq in result.intent_sequences]
            if result.actions:
                response["outgoing_actions"] = [
                    a.to_dict() if hasattr(a, 'to_dict') else a
                    for a in result.actions
                ]

        logger.info(f"Memory unified query completed: type={result.query_type}, success={result.success}")
        return response

    except AppError:
        raise
    except Exception as e:
        logger.error(f"Memory unified query failed: {e}", exc_info=True)
        raise AppError(
            ErrorCode.MEMORY_OPERATION_FAILED,
            f"Memory unified query failed: {str(e)}",
            status_code=500,
        )


@app.post("/api/v1/memory/state")
async def get_state_by_url(
    data: StateByUrlRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Get State and IntentSequences by URL"""
    try:
        from src.common.memory.memory_service import get_private_memory, get_public_memory

        priv_wm = get_private_memory(user_id).workflow_memory
        public_memory_service = get_public_memory()
        pub_wm = public_memory_service.workflow_memory if public_memory_service else None

        state = priv_wm.find_state_by_url(data.url)
        source = "private"
        wm = priv_wm

        if not state and pub_wm:
            state = pub_wm.find_state_by_url(data.url)
            if state:
                source = "public"
                wm = pub_wm

        if not state:
            raise AppError(
                ErrorCode.MEMORY_NOT_FOUND,
                f"No State found for URL: {data.url}",
                status_code=404,
            )

        sequences = []
        if wm.intent_sequence_manager:
            sequences = wm.intent_sequence_manager.list_by_state(state.id)

        if source == "private" and pub_wm:
            pub_state = pub_wm.find_state_by_url(data.url)
            if pub_state and pub_wm.intent_sequence_manager:
                pub_sequences = pub_wm.intent_sequence_manager.list_by_state(pub_state.id)
                existing_descs = {(s.description or "").strip().lower() for s in sequences}
                for ps in pub_sequences:
                    desc = (ps.description or "").strip().lower()
                    if desc and desc not in existing_descs:
                        sequences.append(ps)
                        existing_descs.add(desc)

        state_dict = state.to_dict()
        state_dict.pop("embedding_vector", None)
        seq_dicts = []
        for seq in sequences:
            sd = seq.to_dict()
            sd.pop("embedding_vector", None)
            seq_dicts.append(sd)

        return {
            "success": True,
            "state": state_dict,
            "intent_sequences": seq_dicts,
            "source": source,
        }

    except AppError:
        raise
    except Exception as e:
        logger.error(f"State lookup failed: {e}", exc_info=True)
        raise AppError(
            ErrorCode.MEMORY_OPERATION_FAILED,
            f"State lookup failed: {str(e)}",
            status_code=500,
        )


@app.get("/api/v1/memory/stats")
async def get_memory_stats(
    user_id: str = Depends(get_current_user_id),
):
    """Get User's Workflow Memory Statistics"""
    try:
        from src.common.memory.memory_service import get_private_memory
        wm = get_private_memory(user_id).workflow_memory
        graph_store = wm.state_manager.graph_store

        if hasattr(graph_store, 'run_script'):
            def _count(table: str) -> int:
                try:
                    result = graph_store.run_script(
                        f"SELECT count() FROM {table} GROUP ALL"
                    )
                    if result and isinstance(result, list) and len(result) > 0:
                        row = result[0]
                        return row.get("count", 0) if isinstance(row, dict) else 0
                    return 0
                except Exception:
                    return 0

            total_states = _count("state")
            total_actions = _count("action")
            total_intent_sequences = _count("intentsequence")
            total_page_instances = _count("pageinstance")

            try:
                domain_result = graph_store.run_script(
                    "SELECT domain FROM state WHERE domain IS NOT NULL GROUP BY domain"
                )
                domains = sorted({
                    r["domain"] for r in domain_result
                    if isinstance(r, dict) and r.get("domain")
                }) if domain_result else []
            except Exception:
                domains = []
        else:
            all_states = wm.state_manager.list_states()
            total_states = len(all_states)
            total_page_instances = 0
            if wm.page_instance_manager:
                for s in all_states:
                    total_page_instances += len(wm.page_instance_manager.list_by_state(s.id))
            domains = sorted({s.domain for s in all_states if s.domain})
            total_actions = len(wm.action_manager.list_actions())
            total_intent_sequences = 0
            if wm.intent_sequence_manager:
                try:
                    seqs = wm.intent_sequence_manager.graph_store.query_nodes(
                        label="IntentSequence"
                    )
                    total_intent_sequences = len(seqs)
                except Exception:
                    pass

        url_index_stats = wm.url_index.get_stats()

        logger.info(f"Memory stats for user {user_id}: {total_states} states")

        return {
            "success": True,
            "user_id": user_id,
            "stats": {
                "total_states": total_states,
                "total_intent_sequences": total_intent_sequences,
                "total_page_instances": total_page_instances,
                "total_actions": total_actions,
                "domains": domains,
                "url_index_size": url_index_stats.get("total_urls", 0),
            }
        }

    except Exception as e:
        logger.error(f"Failed to get memory stats: {e}", exc_info=True)
        raise AppError(
            ErrorCode.MEMORY_OPERATION_FAILED,
            f"Failed to get memory stats: {str(e)}",
            status_code=500,
        )


# Public stats (no auth)
_public_stats_cache: Dict[str, Any] = {"data": None, "expires_at": 0.0}
_PUBLIC_STATS_TTL = 30


def _fetch_public_memory_stats() -> dict:
    """Query all memory stores and aggregate stats. Called at most once per TTL."""
    from src.common.memory.memory_service import get_public_memory, _private_stores

    stats = {
        "total_cognitive_phrases": 0,
        "total_domains": 0,
        "total_states": 0,
        "total_intent_sequences": 0,
        "total_executions": 0,
        "total_contributors": 0,
        "domains": [],
    }

    all_domains: set = set()
    all_contributors: set = set()

    def _count(graph_store, table: str) -> int:
        try:
            if hasattr(graph_store, 'run_script'):
                result = graph_store.run_script(
                    f"SELECT count() FROM {table} GROUP ALL"
                )
                if result and isinstance(result, list) and len(result) > 0:
                    row = result[0]
                    return row.get("count", 0) if isinstance(row, dict) else 0
            return 0
        except Exception:
            return 0

    def _get_domains(graph_store) -> set:
        try:
            if hasattr(graph_store, 'run_script'):
                result = graph_store.run_script(
                    "SELECT domain FROM state WHERE domain IS NOT NULL GROUP BY domain"
                )
                if result:
                    return {
                        r["domain"] for r in result
                        if isinstance(r, dict) and r.get("domain")
                    }
            return set()
        except Exception:
            return set()

    def _sum_use_counts(graph_store) -> int:
        try:
            if hasattr(graph_store, 'run_script'):
                result = graph_store.run_script(
                    "SELECT math::sum(use_count) AS total FROM cognitivephrase GROUP ALL"
                )
                if result and isinstance(result, list) and len(result) > 0:
                    row = result[0]
                    return int(row.get("total", 0) or 0) if isinstance(row, dict) else 0
            return 0
        except Exception:
            return 0

    def _get_contributors(graph_store) -> set:
        try:
            if hasattr(graph_store, 'run_script'):
                result = graph_store.run_script(
                    "SELECT contributor_id FROM cognitivephrase WHERE contributor_id IS NOT NULL GROUP BY contributor_id"
                )
                if result:
                    return {
                        r["contributor_id"] for r in result
                        if isinstance(r, dict) and r.get("contributor_id")
                    }
            return set()
        except Exception:
            return set()

    try:
        pub = get_public_memory()
        if pub and pub.workflow_memory:
            gs = pub.workflow_memory.state_manager.graph_store
            stats["total_states"] += _count(gs, "state")
            stats["total_intent_sequences"] += _count(gs, "intentsequence")
            stats["total_cognitive_phrases"] += _count(gs, "cognitivephrase")
            stats["total_executions"] += _sum_use_counts(gs)
            all_domains.update(_get_domains(gs))
            all_contributors.update(_get_contributors(gs))
    except Exception as e:
        logger.warning(f"Failed to get public memory stats: {e}")

    try:
        for uid, service in list(_private_stores.items()):
            try:
                wm = service.workflow_memory
                gs = wm.state_manager.graph_store
                stats["total_states"] += _count(gs, "state")
                stats["total_intent_sequences"] += _count(gs, "intentsequence")
                stats["total_cognitive_phrases"] += _count(gs, "cognitivephrase")
                stats["total_executions"] += _sum_use_counts(gs)
                all_domains.update(_get_domains(gs))
            except Exception:
                continue
        stats["total_contributors"] = max(len(all_contributors), len(_private_stores))
    except Exception as e:
        logger.warning(f"Failed to aggregate private memory stats: {e}")

    stats["domains"] = sorted(all_domains)
    stats["total_domains"] = len(all_domains)
    return stats


@app.get("/api/v1/memory/stats/public")
@limiter.limit(RATE_PUBLIC_DEFAULT)
async def get_public_memory_stats(request: Request):
    """Get aggregated Memory Service statistics (public, no auth required)."""
    import time

    try:
        now = time.monotonic()
        if _public_stats_cache["data"] is not None and now < _public_stats_cache["expires_at"]:
            return {"success": True, "stats": _public_stats_cache["data"]}

        stats = _fetch_public_memory_stats()
        _public_stats_cache["data"] = stats
        _public_stats_cache["expires_at"] = now + _PUBLIC_STATS_TTL
        return {"success": True, "stats": stats}

    except Exception as e:
        logger.error(f"Failed to get public memory stats: {e}", exc_info=True)
        raise AppError(
            ErrorCode.MEMORY_OPERATION_FAILED,
            f"Failed to get public memory stats: {str(e)}",
            status_code=500,
        )


@app.delete("/api/v1/memory")
async def clear_memory(
    user_id: str = Depends(get_current_user_id),
):
    """Clear User's Private Workflow Memory (irreversible)."""
    try:
        from src.common.memory.memory_service import get_private_memory
        wm = get_private_memory(user_id).workflow_memory

        graph_store = wm.graph_store
        has_delete_all = hasattr(graph_store, 'delete_all_nodes_by_label')

        if has_delete_all:
            graph_store.delete_all_nodes_by_label("action")
            graph_store.delete_all_nodes_by_label("has_instance")
            graph_store.delete_all_nodes_by_label("has_sequence")
            graph_store.delete_all_nodes_by_label("manages")

            states_count = graph_store.delete_all_nodes_by_label("State")
            page_instances_count = graph_store.delete_all_nodes_by_label("PageInstance")
            actions_count = 0
            domains_count = graph_store.delete_all_nodes_by_label("Domain")
            phrases_count = graph_store.delete_all_nodes_by_label("CognitivePhrase")
            sequences_count = graph_store.delete_all_nodes_by_label("IntentSequence")

        else:
            all_states = wm.state_manager.list_states()
            all_actions = wm.action_manager.list_actions()
            all_domains = wm.domain_manager.list_domains()
            all_phrases = wm.phrase_manager.list_phrases()

            states_count = len(all_states)
            actions_count = len(all_actions)
            domains_count = len(all_domains)
            phrases_count = len(all_phrases)
            sequences_count = 0
            page_instances_count = 0

            for action in all_actions:
                wm.delete_action(action.source, action.target)
            for state in all_states:
                if wm.page_instance_manager:
                    for inst in wm.page_instance_manager.list_by_state(state.id):
                        wm.page_instance_manager.delete_instance(inst.id)
                        page_instances_count += 1
                if wm.intent_sequence_manager:
                    for seq in wm.intent_sequence_manager.list_by_state(state.id):
                        wm.intent_sequence_manager.delete_sequence(seq.id)
                        sequences_count += 1
            for state in all_states:
                wm.delete_state(state.id)
            for domain in all_domains:
                wm.domain_manager.delete_domain(domain.id)
            for phrase in all_phrases:
                wm.phrase_manager.delete_phrase(phrase.id)

        wm.url_index.clear()

        logger.info(f"Memory cleared: "
                   f"{states_count} states, {page_instances_count} page_instances, "
                   f"{domains_count} domains, {phrases_count} phrases, "
                   f"{sequences_count} sequences")

        return {
            "success": True,
            "deleted_states": states_count,
            "deleted_page_instances": page_instances_count,
            "deleted_domains": domains_count,
            "deleted_phrases": phrases_count,
            "deleted_sequences": sequences_count,
        }

    except Exception as e:
        logger.error(f"Failed to clear memory: {e}", exc_info=True)
        raise AppError(
            ErrorCode.MEMORY_OPERATION_FAILED,
            f"Failed to clear memory: {str(e)}",
            status_code=500,
        )


# ===== CognitivePhrase API =====

@app.get("/api/v1/memory/phrases")
async def list_cognitive_phrases(
    limit: Optional[int] = 50,
    user_id: str = Depends(get_current_user_id),
):
    """List CognitivePhrases from user's private memory."""
    try:
        from src.common.memory.memory_service import get_private_memory
        wm = get_private_memory(user_id).workflow_memory

        phrases = wm.phrase_manager.list_phrases(limit=limit)

        phrase_list = []
        for phrase in phrases:
            phrase_list.append({
                "id": phrase.id,
                "label": phrase.label,
                "description": phrase.description,
                "access_count": phrase.access_count,
                "success_count": phrase.success_count,
                "created_at": phrase.created_at,
            })

        return {
            "success": True,
            "phrases": phrase_list,
            "total": len(phrase_list)
        }

    except Exception as e:
        logger.error(f"Failed to list cognitive phrases: {e}", exc_info=True)
        raise AppError(
            ErrorCode.MEMORY_OPERATION_FAILED,
            f"Failed to list cognitive phrases: {str(e)}",
            status_code=500,
        )


@app.get("/api/v1/memory/phrases/public")
async def list_public_phrases_compat(
    limit: Optional[int] = 50,
    sort: Optional[str] = "popular",
):
    """Compatibility alias for /api/v1/memory/public/phrases (ami-desktop uses this path)."""
    return await list_public_phrases(limit=limit, sort=sort)


@app.get("/api/v1/memory/phrases/{phrase_id}")
async def get_cognitive_phrase(
    phrase_id: str,
    source: Optional[str] = None,
    user_id: str = Depends(get_current_user_id),
):
    """Get CognitivePhrase detail with States and IntentSequences."""
    try:
        if source == "public":
            from src.common.memory.memory_service import get_public_memory
            pub = get_public_memory()
            if not pub or not pub.workflow_memory:
                raise AppError(
                    ErrorCode.MEMORY_PUBLIC_UNAVAILABLE,
                    "Public memory not available",
                    status_code=404,
                )
            wm = pub.workflow_memory
        else:
            from src.common.memory.memory_service import get_private_memory
            wm = get_private_memory(user_id).workflow_memory

        phrase = wm.phrase_manager.get_phrase(phrase_id)
        if not phrase:
            raise AppError(
                ErrorCode.MEMORY_PHRASE_NOT_FOUND,
                f"CognitivePhrase not found: {phrase_id}",
                status_code=404,
            )

        states = []
        for state_id in phrase.state_path:
            state = wm.state_manager.get_state(state_id)
            if state:
                states.append(state.to_dict())

        intent_sequences = []
        if phrase.execution_plan:
            for step in phrase.execution_plan:
                for seq_id in step.in_page_sequence_ids:
                    seq = wm.intent_sequence_manager.get_sequence(seq_id)
                    if seq:
                        intent_sequences.append(seq.to_dict())
                if step.navigation_sequence_id:
                    seq = wm.intent_sequence_manager.get_sequence(step.navigation_sequence_id)
                    if seq:
                        intent_sequences.append(seq.to_dict())

        return {
            "success": True,
            "phrase": phrase.to_dict(),
            "states": states,
            "intent_sequences": intent_sequences
        }

    except AppError:
        raise
    except Exception as e:
        logger.error(f"Failed to get cognitive phrase: {e}", exc_info=True)
        raise AppError(
            ErrorCode.MEMORY_OPERATION_FAILED,
            f"Failed to get cognitive phrase: {str(e)}",
            status_code=500,
        )


@app.delete("/api/v1/memory/phrases/{phrase_id}")
async def delete_cognitive_phrase(
    phrase_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Delete a CognitivePhrase from user's private memory."""
    try:
        from src.common.memory.memory_service import get_private_memory
        wm = get_private_memory(user_id).workflow_memory

        phrase = wm.phrase_manager.get_phrase(phrase_id)
        if not phrase:
            raise AppError(
                ErrorCode.MEMORY_PHRASE_NOT_FOUND,
                f"CognitivePhrase not found: {phrase_id}",
                status_code=404,
            )

        success = wm.phrase_manager.delete_phrase(phrase_id)
        if not success:
            raise AppError(
                ErrorCode.MEMORY_OPERATION_FAILED,
                "Failed to delete phrase",
                status_code=500,
            )

        logger.info(f"CognitivePhrase deleted: {phrase_id}")

        return {
            "success": True,
            "message": "CognitivePhrase deleted"
        }

    except AppError:
        raise
    except Exception as e:
        logger.error(f"Failed to delete cognitive phrase: {e}", exc_info=True)
        raise AppError(
            ErrorCode.MEMORY_OPERATION_FAILED,
            f"Failed to delete cognitive phrase: {str(e)}",
            status_code=500,
        )


# ===== Public Phrase API (no auth) =====

@app.get("/api/v1/memory/public/phrases")
async def list_public_phrases(
    limit: Optional[int] = 50,
    sort: Optional[str] = "popular",
):
    """List CognitivePhrases from public memory. No auth required."""
    try:
        from src.common.memory.memory_service import get_public_memory
        pub = get_public_memory()
        if not pub or not pub.workflow_memory:
            return {"success": True, "phrases": [], "total": 0}

        # Load all phrases, sort in Python, then truncate to limit
        phrases = pub.workflow_memory.phrase_manager.list_phrases(limit=None)

        phrase_list = []
        for phrase in phrases:
            phrase_list.append({
                "id": phrase.id,
                "label": phrase.label,
                "description": phrase.description,
                "contributor_id": phrase.contributor_id,
                "contributed_at": phrase.contributed_at,
                "use_count": phrase.use_count,
                "upvote_count": phrase.upvote_count,
                "state_count": len(phrase.state_path) if phrase.state_path else 0,
                "created_at": phrase.created_at,
            })

        if sort == "recent":
            phrase_list.sort(key=lambda p: p.get("contributed_at") or 0, reverse=True)
        else:
            phrase_list.sort(key=lambda p: p.get("use_count", 0), reverse=True)

        phrase_list = phrase_list[:limit]

        return {
            "success": True,
            "phrases": phrase_list,
            "total": len(phrase_list),
        }

    except Exception as e:
        logger.error(f"Failed to list public phrases: {e}", exc_info=True)
        raise AppError(
            ErrorCode.MEMORY_OPERATION_FAILED,
            f"Failed to list public phrases: {str(e)}",
            status_code=500,
        )


@app.get("/api/v1/memory/public/phrases/{phrase_id}")
async def get_public_phrase(
    phrase_id: str,
):
    """Get a single CognitivePhrase from public memory. No auth required."""
    try:
        from src.common.memory.memory_service import get_public_memory
        pub = get_public_memory()
        if not pub or not pub.workflow_memory:
            raise AppError(
                ErrorCode.MEMORY_PUBLIC_UNAVAILABLE,
                "Public memory not available",
                status_code=404,
            )
        wm = pub.workflow_memory

        phrase = wm.phrase_manager.get_phrase(phrase_id)
        if not phrase:
            raise AppError(
                ErrorCode.MEMORY_PHRASE_NOT_FOUND,
                f"Public phrase not found: {phrase_id}",
                status_code=404,
            )

        states = []
        for state_id in phrase.state_path:
            state = wm.state_manager.get_state(state_id)
            if state:
                states.append(state.to_dict())

        intent_sequences = []
        if phrase.execution_plan:
            for step in phrase.execution_plan:
                for seq_id in step.in_page_sequence_ids:
                    seq = wm.intent_sequence_manager.get_sequence(seq_id)
                    if seq:
                        intent_sequences.append(seq.to_dict())
                if step.navigation_sequence_id:
                    seq = wm.intent_sequence_manager.get_sequence(step.navigation_sequence_id)
                    if seq:
                        intent_sequences.append(seq.to_dict())

        return {
            "success": True,
            "phrase": phrase.to_dict(),
            "states": states,
            "intent_sequences": intent_sequences,
        }

    except AppError:
        raise
    except Exception as e:
        logger.error(f"Failed to get public phrase: {e}", exc_info=True)
        raise AppError(
            ErrorCode.MEMORY_OPERATION_FAILED,
            f"Failed to get public phrase: {str(e)}",
            status_code=500,
        )


# ===== Share / Publish API =====

@app.post("/api/v1/memory/share")
async def share_cognitive_phrase(
    data: SharePhraseRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Share a CognitivePhrase from private memory to public memory."""
    try:
        from src.common.memory.memory_service import share_phrase as do_share
        public_phrase_id = await do_share(user_id, data.phrase_id)

        return {
            "success": True,
            "public_phrase_id": public_phrase_id,
        }

    except ValueError as e:
        raise AppError(
            ErrorCode.MEMORY_PHRASE_NOT_FOUND,
            str(e),
            status_code=404,
        )
    except Exception as e:
        logger.error(f"Failed to share phrase: {e}", exc_info=True)
        raise AppError(
            ErrorCode.MEMORY_OPERATION_FAILED,
            f"Failed to share phrase: {str(e)}",
            status_code=500,
        )


@app.get("/api/v1/memory/publish-status")
async def get_publish_status(
    phrase_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Check if a private phrase has been published to public memory."""
    try:
        from src.common.memory.memory_service import get_public_memory
        pub = get_public_memory()
        if not pub or not pub.workflow_memory:
            return {"published": False}

        wm = pub.workflow_memory
        existing = wm.phrase_manager.graph_store.query_nodes(
            label=wm.phrase_manager.node_label,
            filters={"source_phrase_id": phrase_id, "contributor_id": user_id},
            limit=1,
        )

        if existing:
            return {
                "published": True,
                "public_phrase_id": existing[0].get("id"),
            }
        return {"published": False}

    except Exception as e:
        logger.error(f"Failed to check publish status: {e}")
        return {"published": False}


@app.post("/api/v1/memory/unpublish")
async def unpublish_cognitive_phrase(
    data: UnpublishPhraseRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Remove a CognitivePhrase from public memory. Only the original contributor can unpublish."""
    try:
        from src.common.memory.memory_service import get_public_memory
        pub = get_public_memory()
        if not pub or not pub.workflow_memory:
            raise AppError(
                ErrorCode.MEMORY_PUBLIC_UNAVAILABLE,
                "Public memory not available",
                status_code=404,
            )

        wm = pub.workflow_memory

        existing = wm.phrase_manager.graph_store.query_nodes(
            label=wm.phrase_manager.node_label,
            filters={"source_phrase_id": data.phrase_id, "contributor_id": user_id},
            limit=1,
        )

        if not existing:
            raise AppError(
                ErrorCode.MEMORY_NOT_OWNED,
                "Published phrase not found or not owned by you",
                status_code=404,
            )

        public_phrase_id = existing[0].get("id")
        wm.phrase_manager.graph_store.delete_node(wm.phrase_manager.node_label, public_phrase_id)

        logger.info(f"Unpublished phrase: private={data.phrase_id}, public={public_phrase_id}, user={user_id}")

        return {
            "success": True,
            "message": "Memory unpublished from community",
        }

    except AppError:
        raise
    except Exception as e:
        logger.error(f"Failed to unpublish phrase: {e}", exc_info=True)
        raise AppError(
            ErrorCode.MEMORY_OPERATION_FAILED,
            f"Failed to unpublish phrase: {str(e)}",
            status_code=500,
        )


# ===== Reasoner / Workflow Query API =====

async def _get_reasoner_for_user(
    user_id: str,
    llm_api_key: str,
    use_public: bool = False,
):
    """Get or create a Reasoner instance with per-user API keys and user memory."""
    from src.common.memory.reasoner.reasoner import Reasoner
    from src.common.llm import get_cached_embedding_service, get_cached_anthropic_provider
    from src.common.memory.memory_service import get_private_memory, get_public_memory

    if use_public:
        user_memory = get_public_memory()
    else:
        user_memory = get_private_memory(user_id)

    llm_provider = get_cached_anthropic_provider(
        api_key=llm_api_key,
        model=config_service.get("llm.anthropic.model"),
        base_url=config_service.get("llm.proxy_url")
    )

    embedding_service = get_cached_embedding_service(
        api_key=embedding_api_key,
        base_url=config_service.get("embedding.base_url"),
        model=config_service.get("embedding.model"),
        dimension=config_service.get("embedding.dimension"),
    )

    reasoner_config = config_service.get("reasoner", {})
    max_depth = reasoner_config.get("max_depth", 3)
    similarity_thresholds = reasoner_config.get("similarity_thresholds", {})
    path_planning_config = reasoner_config.get("path_planning", {})

    public_wm = None
    if not use_public:
        public_memory_service = get_public_memory()
        public_wm = public_memory_service.workflow_memory if public_memory_service else None

    reasoner = Reasoner(
        memory=user_memory.workflow_memory,
        llm_provider=llm_provider,
        embedding_service=embedding_service,
        max_depth=max_depth,
        similarity_thresholds=similarity_thresholds,
        public_memory=public_wm,
        path_planning_config=path_planning_config,
    )

    return reasoner


@app.post("/api/v1/memory/workflow-query")
async def query_workflow_from_memory(
    data: WorkflowQueryRequest,
    user_id: str = Depends(get_current_user_id),
    llm_api_key: str = Depends(get_user_llm_api_key),
):
    """Query Workflow from Memory using Natural Language (Reasoner-based)."""
    try:
        user_reasoner = await _get_reasoner_for_user(user_id, llm_api_key=llm_api_key)
        result = await user_reasoner.plan(data.query)

        if not result or not result.success:
            return {
                "workflow": None,
                "confidence": 0.0,
                "matched_states": [],
                "matched_actions": [],
                "status": "no_match",
                "message": "No matching workflow found in memory"
            }

        logger.info(f"Workflow retrieved from memory for query: {data.query}")

        return {
            "workflow": result.workflow,
            "confidence": result.confidence if hasattr(result, 'confidence') else 1.0,
            "matched_states": [s.id for s in result.states] if hasattr(result, 'states') else [],
            "matched_actions": [a.id for a in result.actions] if hasattr(result, 'actions') else [],
            "status": "success"
        }

    except AppError:
        raise
    except Exception as e:
        logger.error(f"Workflow query failed: {e}", exc_info=True)
        raise AppError(
            ErrorCode.MEMORY_OPERATION_FAILED,
            f"Workflow query failed: {str(e)}",
            status_code=500,
        )


@app.post("/api/v1/memory/plan-route")
async def reasoner_plan(
    data: PlanRouteRequest,
    user_id: str = Depends(get_current_user_id),
    llm_api_key: str = Depends(get_user_llm_api_key),
):
    """Reasoner Plan API - Get a workflow plan from memory."""
    try:
        user_reasoner = await _get_reasoner_for_user(user_id, llm_api_key=llm_api_key)

        logger.info(f"Reasoner planning for target: {data.target[:50]}...")
        result = await user_reasoner.plan(data.target)

        if not result or not result.success:
            logger.info(f"Reasoner returned no workflow for target: {data.target[:50]}")
            return {
                "success": False,
                "workflow": None,
                "states": [],
                "actions": [],
                "metadata": {},
                "message": "No matching workflow found in memory"
            }

        states_data = []
        for state in result.states:
            state_dict = state.to_dict() if hasattr(state, 'to_dict') else state
            states_data.append(state_dict)

        actions_data = []
        for action in result.actions:
            action_dict = action.to_dict() if hasattr(action, 'to_dict') else action
            actions_data.append(action_dict)

        logger.info(f"Reasoner returned workflow with {len(states_data)} states, {len(actions_data)} actions")

        return {
            "success": True,
            "workflow": result.workflow,
            "states": states_data,
            "actions": actions_data,
            "metadata": result.metadata or {}
        }

    except AppError:
        raise
    except Exception as e:
        logger.error(f"Reasoner plan failed: {e}", exc_info=True)
        raise AppError(
            ErrorCode.MEMORY_OPERATION_FAILED,
            f"Reasoner plan failed: {str(e)}",
            status_code=500,
        )


# ===== Memory Plan & Learn API =====

@app.post("/api/v1/memory/plan")
async def plan_with_memory(
    data: PlanWithMemoryRequest,
    user_id: str = Depends(get_current_user_id),
    llm_api_key: str = Depends(get_user_llm_api_key),
):
    """Memory-Powered Task Analysis using PlannerAgent."""
    try:
        from src.common.llm import get_cached_anthropic_provider, get_cached_embedding_service
        from src.common.memory.memory_service import get_private_memory, get_public_memory

        private_ms = get_private_memory(user_id)
        public_ms = get_public_memory()

        llm_provider = get_cached_anthropic_provider(
            api_key=llm_api_key,
            model=config_service.get("llm.anthropic.model"),
            base_url=config_service.get("llm.proxy_url"),
        )

        embedding_service = get_cached_embedding_service(
            api_key=embedding_api_key,
            base_url=config_service.get("embedding.base_url"),
            model=config_service.get("embedding.model"),
            dimension=config_service.get("embedding.dimension"),
        )

        plan_result = await private_ms.plan(
            task=data.task,
            llm_provider=llm_provider,
            embedding_service=embedding_service,
            public_memory_service=public_ms,
        )

        response = plan_result.to_dict()
        response["success"] = True
        step_count = len(plan_result.memory_plan.steps)
        logger.info(
            f"PlannerAgent completed: {step_count} steps, "
            f"{len(plan_result.memory_plan.preferences)} preferences "
            f"for user={user_id}"
        )
        return response

    except AppError:
        raise
    except Exception as e:
        logger.error(f"PlannerAgent failed: {e}", exc_info=True)
        raise AppError(
            ErrorCode.MEMORY_OPERATION_FAILED,
            f"PlannerAgent failed: {str(e)}",
            status_code=500,
        )


@app.post("/api/v1/memory/learn")
async def learn_from_execution(
    data: LearnFromExecutionRequest,
    user_id: str = Depends(get_current_user_id),
    llm_api_key: str = Depends(get_user_llm_api_key),
):
    """Post-Execution Learning - Analyzes completed task execution data."""
    try:
        from src.common.llm import get_cached_anthropic_provider, get_cached_embedding_service
        from src.common.memory.learner.models import TaskExecutionData
        from src.common.memory.memory_service import get_private_memory

        execution_data = TaskExecutionData.from_dict(data.execution_data)
        private_ms = get_private_memory(user_id)

        llm_provider = get_cached_anthropic_provider(
            api_key=llm_api_key,
            model=config_service.get("llm.anthropic.model"),
            base_url=config_service.get("llm.proxy_url"),
        )

        embedding_service = get_cached_embedding_service(
            api_key=embedding_api_key,
            base_url=config_service.get("embedding.base_url"),
            model=config_service.get("embedding.model"),
            dimension=config_service.get("embedding.dimension"),
        )

        learn_result = await private_ms.learn(
            execution_data=execution_data,
            llm_provider=llm_provider,
            embedding_service=embedding_service,
        )

        # Auto-share learned phrases to public memory
        shared_phrase_ids = []
        if learn_result.phrase_ids:
            from src.common.memory.memory_service import share_phrase
            for pid in learn_result.phrase_ids:
                try:
                    public_pid = await share_phrase(user_id, pid)
                    shared_phrase_ids.append(public_pid)
                    logger.info(f"Auto-shared phrase {pid} -> public {public_pid}")
                except Exception as e:
                    logger.warning(f"Auto-share phrase {pid} failed: {e}")

        reason = learn_result.learning_plan.reason
        logger.info(
            f"LearnerAgent completed: phrase_created={learn_result.phrase_created}, "
            f"phrase_id={learn_result.phrase_id}, reason={reason[:100]} "
            f"for user={user_id}"
        )
        return {
            "success": True,
            "phrase_created": learn_result.phrase_created,
            "phrase_id": learn_result.phrase_id,
            "phrase_ids": learn_result.phrase_ids,
            "shared_phrase_ids": shared_phrase_ids,
            "reason": reason,
        }

    except AppError:
        raise
    except Exception as e:
        logger.error(f"LearnerAgent failed: {e}", exc_info=True)
        raise AppError(
            ErrorCode.MEMORY_OPERATION_FAILED,
            f"LearnerAgent failed: {str(e)}",
            status_code=500,
        )


# ===== Usage Stats API =====

@app.get("/api/v1/usage/stats")
async def get_usage_stats(
    period: Optional[str] = "month",
    user_id: str = Depends(get_current_user_id),
):
    """Get current user's LLM usage statistics from sub2api."""
    try:
        usage = await sub2api_client.get_user_usage(int(user_id), period=period)
        return {"success": True, "usage": usage}
    except Exception as e:
        logger.error(f"Failed to get usage stats for user {user_id}: {e}")
        raise AppError(
            ErrorCode.SERVICE_SUB2API_FAILED,
            "Failed to get usage stats",
            status_code=502,
        )


if __name__ == "__main__":
    from core.config_service import CloudConfigService
    temp_config = CloudConfigService()

    uvicorn.run(
        "main:app",
        host=temp_config.get("server.host", "0.0.0.0"),
        port=temp_config.get("server.port", 9000),
        reload=temp_config.get("server.reload", False),
        log_level=temp_config.get("logging.level", "info").lower()
    )
