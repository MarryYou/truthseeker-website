"""Main FastAPI application entry point."""
from __future__ import annotations
import uuid
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from backend.api.auth import router as auth_router
from backend.api.chat import router as chat_router
from backend.api.research import router as research_router
from backend.api.settings import router as settings_router
from backend.services.app_lifecycle import lifespan
from backend.core.config import CORS_ORIGINS
from backend.core.logging import trace_id_var, source_var, logger
from backend.db.engine import async_session
import time


app = FastAPI(
    title="TruthSeeker API",
    description="Deep Research and Fact-Checking Engine",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):
    """Middleware to inject a unique Trace ID and Request Source for each request."""
    trace_id = request.headers.get("X-Trace-ID") or str(uuid.uuid4())
    is_internal = request.headers.get("X-Internal-Request") == "true"

    t_token = trace_id_var.set(trace_id)
    s_token = source_var.set("internal" if is_internal else "external")
    
    start_time = time.perf_counter()
    logger.info("API Request | method={} path={} query={}", request.method, request.url.path, request.query_params)
    
    try:
        response = await call_next(request)
        duration = time.perf_counter() - start_time
        logger.info("API Response | status={} duration={:.3f}s", response.status_code, duration)
        
        if not response.background:
            response.headers["X-Trace-ID"] = trace_id
        return response
    except Exception as e:
        duration = time.perf_counter() - start_time
        # pylint: disable=no-member
        if isinstance(e, HTTPException) and 400 <= e.status_code < 500:
            logger.warning("API Client Error | status={} duration={:.3f}s detail={}", e.status_code, duration, e.detail)
        else:
            logger.error("API Error | duration={:.3f}s error={}", duration, e)
        raise e
    finally:
        trace_id_var.reset(t_token)
        source_var.reset(s_token)


@app.exception_handler(Exception)
async def global_exception_handler(_request: Request, exc: Exception):
    """Global error handler to catch unhandled exceptions."""
    logger.exception("Unhandled Exception Caught by Global Handler | error={}", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": f"Internal server error: {str(exc)}"}
    )


app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(research_router)
app.include_router(settings_router)


@app.get("/health", tags=["system"])
async def health_check():
    """Health check endpoint that pings the database."""
    try:
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        logger.error("Health check failed | error={}", e)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unhealthy", "database": "disconnected", "detail": str(e)}
        )
