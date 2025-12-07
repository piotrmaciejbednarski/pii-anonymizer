"""
FastAPI application entry point.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import settings
from app.core.logging import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting PII Anonymizer API...")
    logger.info(f"Device: {settings.device}")
    logger.info(f"GLiNER model: {settings.gliner_model_path}")
    logger.info(f"Polimorf DB: {settings.polimorf_db}")
    
    # Pre-warm models (optional - comment out for faster startup)
    # try:
    #     from app.engine.hybrid_runner import get_hybrid_runner
    #     runner = get_hybrid_runner()
    #     _ = runner.gliner_model  # Trigger model load
    #     logger.info("Models pre-loaded")
    # except Exception as e:
    #     logger.warning(f"Model pre-loading failed: {e}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down PII Anonymizer API...")


app = FastAPI(
    title="PII Anonymizer",
    description=(
        "Hybrid Context-Aware PII Anonymizer for Polish.\n\n"
        "Detects and anonymizes personally identifiable information (PII) "
        "with correct Polish inflection using GLiNER and Polimorf."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api/v1")


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": "PII Anonymizer",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/v1/health",
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )

