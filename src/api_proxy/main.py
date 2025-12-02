"""
API Proxy Main Application

User management and LLM API proxy microservice
"""
import logging
from contextlib import asynccontextmanager

from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import get_config
from .database.connection import init_db, create_all_tables
from .api import auth, proxy, stats
from .api.admin import dashboard


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager

    Handles startup and shutdown events
    """
    # Startup
    logger.info("Starting API Proxy...")

    try:
        # Load configuration
        config = get_config()
        logger.info(f"Configuration loaded from {config}")

        # Initialize database
        init_db()
        logger.info("Database connection initialized")

        # Create tables if they don't exist
        create_all_tables()
        logger.info("Database tables created/verified")

        logger.info("API Proxy started successfully")

    except Exception as e:
        logger.error(f"Failed to start API Proxy: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down API Proxy...")


# Create FastAPI application
app = FastAPI(
    title="Ami API Proxy",
    description="User management and LLM API proxy service",
    version="1.0.0",
    lifespan=lifespan
)


# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for now
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle uncaught exceptions"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Internal server error",
            "detail": str(exc)
        }
    )


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint

    Returns server status and configuration
    """
    config = get_config()
    return {
        "status": "healthy",
        "service": "API Proxy",
        "version": "1.0.0",
        "config": {
            "server": {
                "host": config.get("server.host", "0.0.0.0"),
                "port": config.get("server.port", 8080),
            },
            "database": {
                "type": config.get_db_type(),
            },
            "quota": {
                "trial_period_days": config.get("quota.trial.trial_period_days", 30),
                "trial_workflow_limit": config.get("quota.trial.workflow_executions_per_month", 50),
            }
        }
    }


# Include routers
app.include_router(
    auth.router,
    prefix="/api/auth",
    tags=["Authentication"]
)

app.include_router(
    proxy.router,
    tags=["LLM Proxy"]
)

app.include_router(
    stats.router,
    prefix="/api/stats",
    tags=["Statistics"]
)

app.include_router(
    dashboard.router,
    tags=["Admin Dashboard"]
)


# Mount static files for admin dashboard
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/admin", StaticFiles(directory=str(static_dir), html=True), name="static")


# Root endpoint - redirect to admin dashboard
@app.get("/")
async def root():
    """Root endpoint - redirects to admin dashboard"""
    return RedirectResponse(url="/admin/admin.html")


if __name__ == "__main__":
    import uvicorn

    config = get_config()

    uvicorn.run(
        "main:app",
        host=config.get("server.host", "0.0.0.0"),
        port=config.get("server.port", 8080),
        reload=config.get("server.reload", False),
        workers=config.get("server.workers", 1) if not config.get("server.reload", False) else 1,
    )
