import logging
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.auth import router as auth_router
from app.api.conversations import router as conversations_router
from app.api.documents import router as documents_router
from app.api.legal import router as legal_router
from app.database.connection import engine, initialize_local_schema
from app.core.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_local_schema()
    yield

app = FastAPI(
    title="Apna Wakeel API",
    description="AI-powered legal information and navigation backend for Pakistan",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys([
        *[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
        f"{urlsplit(settings.frontend_url).scheme}://{urlsplit(settings.frontend_url).netloc}",
    ])),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(conversations_router)
app.include_router(documents_router)
app.include_router(legal_router)


@app.get("/")
async def root():
    return {
        "message": "Apna Wakeel API is running successfully!",
        "version": "0.1.0",
        "documentation": "/docs",
        "health_check": "/api/health",
        "frontend_url": "http://127.0.0.1:5173",
    }


@app.get("/api/health")
async def health_check():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return {
            "status": "ok",
            "service": "apna-wakeel-backend",
            "database": "connected",
        }

    except Exception as error:
        logger.error("Database health check failed: type=%s", type(error).__name__)
        raise HTTPException(status_code=503, detail="database_unavailable") from None