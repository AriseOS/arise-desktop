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
from fastapi import FastAPI, HTTPException, Depends
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

# Create FastAPI application
app = FastAPI(
    title="Ami Cloud Backend",
    description="Memory-as-a-Service + Auth",
    version="3.0.0"
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

# Add request context middleware for logging
from core.middleware import RequestContextMiddleware
app.add_middleware(RequestContextMiddleware)


# ===== JWT Auth Dependency =====

security = HTTPBearer(auto_error=False)


async def get_current_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    """FastAPI dependency: extract user_id from JWT access token."""
    if credentials is None:
        raise HTTPException(401, "Authentication required")
    from api.auth import auth_service
    payload = auth_service.verify_token(credentials.credentials, expected_type="access")
    if payload is None:
        raise HTTPException(401, "Invalid or expired token")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(401, "Token missing user identity")
    return user_id


async def get_user_llm_api_key(
    user_id: str = Depends(get_current_user_id),
) -> str:
    """FastAPI dependency: get per-user sub2api API key. No fallback."""
    from database.models import SessionLocal, User

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == int(user_id)).first()
        if user and user.sub2api_api_key:
            return user.sub2api_api_key
    finally:
        db.close()
    raise HTTPException(403, "User has no API key. Please contact admin to provision your account.")


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

        # 3. Initialize database
        from database.models import init_db
        init_db()
        print("Database: initialized")

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
        "version": "3.0.0"
    }


@app.get("/")
def root():
    return {
        "service": "Ami Cloud Backend",
        "version": "3.0.0",
        "docs": "/docs"
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


@app.post("/api/v1/app/version-check")
async def check_app_version(data: dict):
    """Check if app version is compatible"""
    client_version = data.get("version", "0.0.0")
    platform = data.get("platform", "unknown")

    minimum_version = get_minimum_app_version()
    compatible = is_version_compatible(client_version, minimum_version)

    response = {
        "compatible": compatible,
        "minimum_version": minimum_version,
        "client_version": client_version
    }

    if not compatible:
        base_url = "http://download.ariseos.com/releases/latest"
        platform_urls = {
            "macos-arm64": f"{base_url}/macos-arm64/Ami-latest-macos-arm64.dmg",
            "windows-x64": f"{base_url}/windows-x64/Ami-latest-windows-x64.zip",
        }
        response["update_url"] = platform_urls.get(platform, base_url)
        response["message"] = f"Please update Ami to version {minimum_version} or later"
        logger.info(f"Version check: {client_version} < {minimum_version} (platform: {platform})")
    else:
        logger.debug(f"Version check: {client_version} is compatible")

    return response


# ===== Auth API =====

@app.post("/api/v1/auth/login")
async def login(data: dict):
    """
    User login

    Body: {"username": "...", "password": "..."}
    Returns: {"access_token": "...", "refresh_token": "...", "user_id": "...", "username": "..."}
    """
    from api.auth import auth_service
    from database.models import SessionLocal

    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        raise HTTPException(400, "Missing username or password")

    db = SessionLocal()
    try:
        user = auth_service.authenticate_user(db, username, password)
        if not user:
            raise HTTPException(401, "Invalid credentials")

        user.last_login = datetime.now(timezone.utc)
        db.commit()

        token_data = {"sub": str(user.id), "username": user.username}
        access_token = auth_service.create_access_token(token_data)
        refresh_token = auth_service.create_refresh_token(token_data)

        logger.info(f"User login: {username}")
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user_id": str(user.id),
            "username": user.username,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.post("/api/v1/auth/register")
async def register(data: dict):
    """
    User registration (auto-login on success)

    Body: {"username": "...", "email": "...", "password": "..."}
    Returns: {"success": True, "access_token": "...", "refresh_token": "...", "user_id": "...", "username": "..."}
    """
    from api.auth import auth_service
    from database.models import SessionLocal

    username = data.get("username")
    email = data.get("email")
    password = data.get("password")

    if not username or not email or not password:
        raise HTTPException(400, "Missing username, email, or password")

    # Input validation
    if len(username) > 50:
        raise HTTPException(400, "Username must be 50 characters or fewer")
    if len(email) > 100:
        raise HTTPException(400, "Email must be 100 characters or fewer")
    if len(password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    if len(password) > 128:
        raise HTTPException(400, "Password must be 128 characters or fewer")

    db = SessionLocal()
    try:
        user = auth_service.create_user(db, username, email, password)

        # Provision sub2api user + API key (required for LLM access)
        try:
            result = await sub2api_client.provision_user(
                email=email, password=password, username=username,
            )
        except Exception as e:
            # Sub2api failed — delete the Cloud Backend user to keep consistency
            logger.error(f"Sub2api provisioning failed for {username}: {e}")
            db.delete(user)
            db.commit()
            raise HTTPException(502, f"Failed to provision API access: {e}")

        user.sub2api_user_id = result["user_id"]
        user.sub2api_api_key = result["api_key"]
        db.commit()
        logger.info(f"Sub2api provisioned for user {username}: sub2api_id={result['user_id']}")

        # Auto-login: issue tokens immediately
        token_data = {"sub": str(user.id), "username": user.username}
        access_token = auth_service.create_access_token(token_data)
        refresh_token = auth_service.create_refresh_token(token_data)

        logger.info(f"User registered: {username}")
        return {
            "success": True,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user_id": str(user.id),
            "username": user.username,
        }
    except (HTTPException, ValueError) as e:
        if isinstance(e, ValueError):
            raise HTTPException(400, str(e))
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.post("/api/v1/auth/refresh")
async def refresh_token(data: dict):
    """
    Refresh access token using a valid refresh token.

    Body: {"refresh_token": "..."}
    Returns: {"access_token": "..."}
    """
    from api.auth import auth_service

    token = data.get("refresh_token")
    if not token:
        raise HTTPException(400, "Missing refresh_token")

    payload = auth_service.verify_token(token, expected_type="refresh")
    if payload is None:
        raise HTTPException(401, "Invalid or expired refresh token")

    user_id = payload.get("sub")
    username = payload.get("username")
    if not user_id:
        raise HTTPException(401, "Token missing user identity")

    access_token = auth_service.create_access_token({"sub": user_id, "username": username})
    return {"access_token": access_token}


@app.get("/api/v1/auth/credentials")
async def get_credentials(user_id: str = Depends(get_current_user_id)):
    """
    Return LLM API key for the authenticated user.
    The daemon stores this locally and uses it for LLM calls via sub2api proxy.

    Returns: {"api_key": "sk-xxx"}
    """
    from database.models import SessionLocal, User

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == int(user_id)).first()
        if not user or not user.sub2api_api_key:
            raise HTTPException(403, "User has no API key provisioned")
        return {"api_key": user.sub2api_api_key}
    finally:
        db.close()


@app.get("/api/v1/auth/me")
async def get_me(
    user_id: str = Depends(get_current_user_id),
):
    """Get current user profile."""
    from database.models import SessionLocal, User

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == int(user_id)).first()
        if not user:
            raise HTTPException(404, "User not found")

        return {
            "user_id": str(user.id),
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login": user.last_login.isoformat() if user.last_login else None,
        }
    finally:
        db.close()


@app.put("/api/v1/auth/me")
async def update_me(
    data: dict,
    user_id: str = Depends(get_current_user_id),
):
    """
    Update current user profile (full_name only).

    Body: {"full_name": "..."}
    """
    from database.models import SessionLocal, User

    full_name = data.get("full_name")
    if full_name is None:
        raise HTTPException(400, "Missing full_name")

    if len(full_name) > 100:
        raise HTTPException(400, "full_name must be 100 characters or fewer")

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == int(user_id)).first()
        if not user:
            raise HTTPException(404, "User not found")

        user.full_name = full_name
        db.commit()

        return {
            "success": True,
            "user_id": str(user.id),
            "full_name": user.full_name,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.post("/api/v1/auth/change-password")
async def change_password(
    data: dict,
    user_id: str = Depends(get_current_user_id),
):
    """
    Change current user's password.

    Body: {"current_password": "...", "new_password": "..."}
    """
    from api.auth import auth_service
    from database.models import SessionLocal, User

    current_password = data.get("current_password")
    new_password = data.get("new_password")

    if not current_password or not new_password:
        raise HTTPException(400, "Missing current_password or new_password")

    if len(new_password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    if len(new_password) > 128:
        raise HTTPException(400, "Password must be 128 characters or fewer")

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == int(user_id)).first()
        if not user:
            raise HTTPException(404, "User not found")

        if not auth_service.verify_password(current_password, user.hashed_password):
            raise HTTPException(401, "Invalid current password")

        user.hashed_password = auth_service.get_password_hash(new_password)
        db.commit()

        logger.info(f"Password changed for user: {user.username}")
        return {"success": True}
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ===== Memory API =====

@app.post("/api/v1/memory/add")
async def add_to_memory(
    data: dict,
    user_id: str = Depends(get_current_user_id),
    llm_api_key: str = Depends(get_user_llm_api_key),
):
    """
    Add Operations to User's Workflow Memory

    Processes operations and adds States, Actions, and IntentSequences
    to the user's workflow memory.

    Body:
        {
            "operations": [...],
            "session_id": "session_xxx",
            "generate_embeddings": true,
            "skip_cognitive_phrase": false
        }
    """
    import time
    start_time = time.time()

    operations = data.get("operations")
    session_id = data.get("session_id")
    snapshots = data.get("snapshots")
    generate_embeddings = data.get("generate_embeddings", True)
    skip_cognitive_phrase = data.get("skip_cognitive_phrase", False)

    if not operations:
        raise HTTPException(400, "operations is required")

    try:
        from src.common.memory.thinker.workflow_processor import WorkflowProcessor

        # Setup embedding service with per-user API key
        embedding_service = None
        if generate_embeddings:
            from src.common.llm import get_cached_embedding_service
            embedding_service = get_cached_embedding_service(
                api_key=llm_api_key,
                base_url=config_service.get("embedding.base_url"),
                model=config_service.get("embedding.model"),
                dimension=config_service.get("embedding.dimension"),
            )

        # Setup LLM providers with per-user API key
        llm_provider = None
        simple_llm_provider = None
        if generate_embeddings:
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
            workflow_data={"operations": operations},
            session_id=session_id,
            store_to_memory=True,
            snapshots=snapshots,
            skip_cognitive_phrase=skip_cognitive_phrase,
        )

        processing_time_ms = int((time.time() - start_time) * 1000)

        logger.info(f"Added to memory for user {user_id}: "
                   f"{result.metadata.get('new_states', 0)} new states, "
                   f"{result.metadata.get('reused_states', 0)} merged, "
                   f"{len(result.intent_sequences)} sequences")

        return {
            "success": True,
            "states_added": result.metadata.get("new_states", 0),
            "states_merged": result.metadata.get("reused_states", 0),
            "page_instances_added": len(result.page_instances),
            "intent_sequences_added": len(result.intent_sequences),
            "actions_added": len(result.actions),
            "processing_time_ms": processing_time_ms
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add to memory: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Failed to add to memory: {str(e)}")


@app.post("/api/v1/memory/phrase/query")
async def query_cognitive_phrase(
    data: dict,
    user_id: str = Depends(get_current_user_id),
    llm_api_key: str = Depends(get_user_llm_api_key),
):
    """
    Query CognitivePhrase (User-Recorded Complete Workflow)

    Body:
        {
            "query": "View team info on Product Hunt"
        }
    """
    query = data.get("query")
    if not query:
        raise HTTPException(400, "Missing query")

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
                    query, private_phrases, public_phrases
                )
            )
        else:
            can_satisfy, matching_phrases, reasoning, source = False, [], "No phrases", "private"

        if not can_satisfy or not matching_phrases:
            logger.info(f"No CognitivePhrase found for: {query[:50]}...")
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

        logger.info(f"Found CognitivePhrase for '{query[:30]}...': {phrase.id} (source={source}) with {len(states)} states")

        return {
            "success": True,
            "phrase": phrase_dict,
            "reasoning": reasoning,
            "source": source,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"CognitivePhrase query failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"CognitivePhrase query failed: {str(e)}")


@app.post("/api/v1/memory/query")
async def query_memory(
    data: dict,
    user_id: str = Depends(get_current_user_id),
    llm_api_key: str = Depends(get_user_llm_api_key),
):
    """
    Unified Memory Query - Task, Navigation, and Action queries

    Body:
        {
            "target": "Query description or task",
            "current_state": "state_id",
            "start_state": "start description or id",
            "end_state": "end description or id",
            "as_type": "task|navigation|action",
            "top_k": 10
        }
    """
    target = data.get("target", "")
    current_state = data.get("current_state")
    start_state = data.get("start_state")
    end_state = data.get("end_state")
    as_type = data.get("as_type")
    top_k = data.get("top_k", 10)

    try:
        user_reasoner = await _get_reasoner_for_user(user_id, llm_api_key=llm_api_key)

        result = await user_reasoner.query(
            target=target,
            current_state=current_state,
            start_state=start_state,
            end_state=end_state,
            as_type=as_type,
            top_k=top_k,
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

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Memory unified query failed: {e}\n{error_trace}")
        raise HTTPException(500, f"Memory unified query failed: {str(e)}")


@app.post("/api/v1/memory/state")
async def get_state_by_url(
    data: dict,
    user_id: str = Depends(get_current_user_id),
):
    """
    Get State and IntentSequences by URL

    Body:
        {
            "url": "https://example.com/products/123"
        }
    """
    url = data.get("url")
    if not url:
        raise HTTPException(400, "Missing url")

    try:
        from src.common.memory.memory_service import get_private_memory, get_public_memory

        priv_wm = get_private_memory(user_id).workflow_memory
        public_memory_service = get_public_memory()
        pub_wm = public_memory_service.workflow_memory if public_memory_service else None

        state = priv_wm.find_state_by_url(url)
        source = "private"
        wm = priv_wm

        if not state and pub_wm:
            state = pub_wm.find_state_by_url(url)
            if state:
                source = "public"
                wm = pub_wm

        if not state:
            raise HTTPException(404, f"No State found for URL: {url}")

        sequences = []
        if wm.intent_sequence_manager:
            sequences = wm.intent_sequence_manager.list_by_state(state.id)

        if source == "private" and pub_wm:
            pub_state = pub_wm.find_state_by_url(url)
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

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"State lookup failed: {e}\n{error_trace}")
        raise HTTPException(500, f"State lookup failed: {str(e)}")


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
        logger.error(f"Failed to get memory stats: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Failed to get memory stats: {str(e)}")


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
async def get_public_memory_stats():
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
        logger.error(f"Failed to get public memory stats: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Failed to get public memory stats: {str(e)}")


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
        logger.error(f"Failed to clear memory: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Failed to clear memory: {str(e)}")


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
        logger.error(f"Failed to list cognitive phrases: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Failed to list cognitive phrases: {str(e)}")


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
                raise HTTPException(404, "Public memory not available")
            wm = pub.workflow_memory
        else:
            from src.common.memory.memory_service import get_private_memory
            wm = get_private_memory(user_id).workflow_memory

        phrase = wm.phrase_manager.get_phrase(phrase_id)
        if not phrase:
            raise HTTPException(404, f"CognitivePhrase not found: {phrase_id}")

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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get cognitive phrase: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Failed to get cognitive phrase: {str(e)}")


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
            raise HTTPException(404, f"CognitivePhrase not found: {phrase_id}")

        success = wm.phrase_manager.delete_phrase(phrase_id)
        if not success:
            raise HTTPException(500, "Failed to delete phrase")

        logger.info(f"CognitivePhrase deleted: {phrase_id}")

        return {
            "success": True,
            "message": "CognitivePhrase deleted"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete cognitive phrase: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Failed to delete cognitive phrase: {str(e)}")


# ===== Public Phrase API (no auth) =====

@app.get("/api/v1/memory/public/phrases")
async def list_public_phrases(
    limit: Optional[int] = 50,
    sort: Optional[str] = "popular",
):
    """List CognitivePhrases from public memory. No auth required.

    Query Parameters:
        limit: Maximum number of phrases (default: 50)
        sort: "popular" (by use_count, default) or "recent" (by contributed_at)
    """
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
        logger.error(f"Failed to list public phrases: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Failed to list public phrases: {str(e)}")


@app.get("/api/v1/memory/public/phrases/{phrase_id}")
async def get_public_phrase(
    phrase_id: str,
):
    """Get a single CognitivePhrase from public memory. No auth required."""
    try:
        from src.common.memory.memory_service import get_public_memory
        pub = get_public_memory()
        if not pub or not pub.workflow_memory:
            raise HTTPException(404, "Public memory not available")
        wm = pub.workflow_memory

        phrase = wm.phrase_manager.get_phrase(phrase_id)
        if not phrase:
            raise HTTPException(404, f"Public phrase not found: {phrase_id}")

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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get public phrase: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Failed to get public phrase: {str(e)}")


# ===== Share / Publish API =====

@app.post("/api/v1/memory/share")
async def share_cognitive_phrase(
    data: dict,
    user_id: str = Depends(get_current_user_id),
):
    """Share a CognitivePhrase from private memory to public memory."""
    phrase_id = data.get("phrase_id")
    if not phrase_id:
        raise HTTPException(400, "Missing phrase_id")

    try:
        from src.common.memory.memory_service import share_phrase as do_share
        public_phrase_id = await do_share(user_id, phrase_id)

        return {
            "success": True,
            "public_phrase_id": public_phrase_id,
        }

    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        logger.error(f"Failed to share phrase: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Failed to share phrase: {str(e)}")


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
    data: dict,
    user_id: str = Depends(get_current_user_id),
):
    """Remove a CognitivePhrase from public memory. Only the original contributor can unpublish."""
    phrase_id = data.get("phrase_id")
    if not phrase_id:
        raise HTTPException(400, "Missing phrase_id")

    try:
        from src.common.memory.memory_service import get_public_memory
        pub = get_public_memory()
        if not pub or not pub.workflow_memory:
            raise HTTPException(404, "Public memory not available")

        wm = pub.workflow_memory

        existing = wm.phrase_manager.graph_store.query_nodes(
            label=wm.phrase_manager.node_label,
            filters={"source_phrase_id": phrase_id, "contributor_id": user_id},
            limit=1,
        )

        if not existing:
            raise HTTPException(404, "Published phrase not found or not owned by you")

        public_phrase_id = existing[0].get("id")
        wm.phrase_manager.graph_store.delete_node(wm.phrase_manager.node_label, public_phrase_id)

        logger.info(f"Unpublished phrase: private={phrase_id}, public={public_phrase_id}, user={user_id}")

        return {
            "success": True,
            "message": "Memory unpublished from community",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to unpublish phrase: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Failed to unpublish phrase: {str(e)}")


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
        api_key=llm_api_key,
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
    data: dict,
    user_id: str = Depends(get_current_user_id),
    llm_api_key: str = Depends(get_user_llm_api_key),
):
    """
    Query Workflow from Memory using Natural Language (Reasoner-based).

    Body:
        {
            "query": "Fill out the login form"
        }
    """
    query = data.get("query")

    if not query:
        raise HTTPException(400, "Missing query")

    try:
        user_reasoner = await _get_reasoner_for_user(user_id, llm_api_key=llm_api_key)
        result = await user_reasoner.plan(query)

        if not result or not result.success:
            return {
                "workflow": None,
                "confidence": 0.0,
                "matched_states": [],
                "matched_actions": [],
                "status": "no_match",
                "message": "No matching workflow found in memory"
            }

        logger.info(f"Workflow retrieved from memory for query: {query}")

        return {
            "workflow": result.workflow,
            "confidence": result.confidence if hasattr(result, 'confidence') else 1.0,
            "matched_states": [s.id for s in result.states] if hasattr(result, 'states') else [],
            "matched_actions": [a.id for a in result.actions] if hasattr(result, 'actions') else [],
            "status": "success"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Workflow query failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Workflow query failed: {str(e)}")


@app.post("/api/v1/memory/plan-route")
async def reasoner_plan(
    data: dict,
    user_id: str = Depends(get_current_user_id),
    llm_api_key: str = Depends(get_user_llm_api_key),
):
    """
    Reasoner Plan API - Get a workflow plan from memory.

    Body:
        {
            "target": "Search for product on Taobao",
            "session_id": "session_456"
        }
    """
    target = data.get("target")
    if not target:
        raise HTTPException(400, "Missing target (task description)")

    try:
        user_reasoner = await _get_reasoner_for_user(user_id, llm_api_key=llm_api_key)

        logger.info(f"Reasoner planning for target: {target[:50]}...")
        result = await user_reasoner.plan(target)

        if not result or not result.success:
            logger.info(f"Reasoner returned no workflow for target: {target[:50]}")
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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reasoner plan failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Reasoner plan failed: {str(e)}")


# ===== Memory Plan & Learn API =====

@app.post("/api/v1/memory/plan")
async def plan_with_memory(
    data: dict,
    user_id: str = Depends(get_current_user_id),
    llm_api_key: str = Depends(get_user_llm_api_key),
):
    """
    Memory-Powered Task Analysis using PlannerAgent.

    Body:
        {
            "task": "Search for top AI products on Product Hunt this week"
        }
    """
    task = data.get("task")
    if not task:
        raise HTTPException(400, "Missing task")

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
            api_key=llm_api_key,
            base_url=config_service.get("embedding.base_url"),
            model=config_service.get("embedding.model"),
            dimension=config_service.get("embedding.dimension"),
        )

        plan_result = await private_ms.plan(
            task=task,
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

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"PlannerAgent failed: {e}\n{error_trace}")
        raise HTTPException(500, f"PlannerAgent failed: {str(e)}")


@app.post("/api/v1/memory/learn")
async def learn_from_execution(
    data: dict,
    user_id: str = Depends(get_current_user_id),
    llm_api_key: str = Depends(get_user_llm_api_key),
):
    """
    Post-Execution Learning - Analyzes completed task execution data.

    Body:
        {
            "execution_data": {
                "task_id": "...",
                "user_request": "...",
                "subtasks": [...],
                "completed_count": 3,
                "failed_count": 0,
                "total_count": 3
            }
        }
    """
    execution_data_dict = data.get("execution_data")
    if not execution_data_dict:
        raise HTTPException(400, "Missing execution_data")

    try:
        from src.common.llm import get_cached_anthropic_provider, get_cached_embedding_service
        from src.common.memory.learner.models import TaskExecutionData
        from src.common.memory.memory_service import get_private_memory

        execution_data = TaskExecutionData.from_dict(execution_data_dict)
        private_ms = get_private_memory(user_id)

        llm_provider = get_cached_anthropic_provider(
            api_key=llm_api_key,
            model=config_service.get("llm.anthropic.model"),
            base_url=config_service.get("llm.proxy_url"),
        )

        embedding_service = get_cached_embedding_service(
            api_key=llm_api_key,
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

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"LearnerAgent failed: {e}\n{error_trace}")
        raise HTTPException(500, f"LearnerAgent failed: {str(e)}")


# ===== Usage Stats API =====

@app.get("/api/v1/usage/stats")
async def get_usage_stats(
    period: Optional[str] = "month",
    user_id: str = Depends(get_current_user_id),
):
    """Get current user's LLM usage statistics from sub2api.

    Query Parameters:
        period: "day", "week", "month" (default: "month")
    """
    from database.models import SessionLocal, User

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == int(user_id)).first()
        if not user or not user.sub2api_user_id:
            raise HTTPException(403, "User has no sub2api account linked")
        sub2api_uid = user.sub2api_user_id
    finally:
        db.close()

    try:
        usage = await sub2api_client.get_user_usage(sub2api_uid, period=period)
        return {"success": True, "usage": usage}
    except Exception as e:
        logger.error(f"Failed to get usage stats for user {user_id}: {e}")
        raise HTTPException(500, f"Failed to get usage stats: {str(e)}")


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
