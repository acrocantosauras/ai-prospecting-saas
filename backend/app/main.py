"""AI Prospecting SaaS - Backend Application."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.api.v1.endpoints import business_profile, icp, batches, prospects, exports
from app.core import init_db

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db.init()
    yield


app = FastAPI(
    title=settings.app_name,
    description="AI-powered B2B Prospecting SaaS API",
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Log the stack trace server-side; never return it to the client."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    detail = str(exc) if settings.debug else "Internal server error"
    return JSONResponse(status_code=500, content={"detail": detail})


# The dev server is reachable as both localhost and 127.0.0.1; browsers treat
# those as different origins, so allow both spellings of the configured URL.
_allowed_origins = {settings.frontend_url} if settings.frontend_url else set()
if settings.frontend_url:
    _allowed_origins.add(settings.frontend_url.replace("localhost", "127.0.0.1"))
    _allowed_origins.add(settings.frontend_url.replace("127.0.0.1", "localhost"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(_allowed_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(business_profile.router, prefix="/api/v1/business-profile", tags=["Business Profile"])
app.include_router(icp.router, prefix="/api/v1/icp", tags=["ICP"])
app.include_router(batches.router, prefix="/api/v1/batches", tags=["Batches"])
app.include_router(prospects.router, prefix="/api/v1/prospects", tags=["Prospects"])
app.include_router(exports.router, prefix="/api/v1/exports", tags=["Exports"])


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "mode": settings.demo_mode,
        "docs": "/docs",
    }
