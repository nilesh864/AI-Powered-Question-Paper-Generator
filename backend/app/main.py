import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import auth, documents, export, generate
from app.core.config import settings
from app.db import mongodb

logger = logging.getLogger("uvicorn")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Graceful database connection startup
    try:
        await mongodb.connect_to_mongodb()
        logger.info("Successfully connected to MongoDB.")
    except Exception as e:
        logger.warning(f"MongoDB connection failed at startup: {e}. Operating in fallback/degraded mode.")
    
    yield
    
    # Clean shutdown
    try:
        await mongodb.close_mongodb_connection()
        logger.info("MongoDB connection closed.")
    except Exception as e:
        logger.error(f"Error closing MongoDB connection: {e}")


app = FastAPI(title=getattr(settings, "app_name", "Question Paper Generator"), version="1.0.0", lifespan=lifespan)

# Standardize CORS origins to prevent Network Error from Vite (port 5173)
origins = getattr(settings, "allowed_origins", None) or [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Route registrations
api_prefix = getattr(settings, "api_prefix", "/api/v1")

app.include_router(auth.router, prefix=api_prefix)
app.include_router(documents.router, prefix=api_prefix)
app.include_router(generate.router, prefix=api_prefix)
app.include_router(generate.papers_router, prefix=api_prefix)
app.include_router(export.router, prefix=api_prefix)


@app.exception_handler(mongodb.DatabaseUnavailable)
async def database_unavailable(_request: Request, error: mongodb.DatabaseUnavailable):
    return JSONResponse(status_code=503, content={"detail": str(error)})


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "database": "mongodb" if getattr(mongodb, "mongo_available", False) else "unavailable",
        "gemini_configured": bool(getattr(settings, "gemini_api_key", None))
    }