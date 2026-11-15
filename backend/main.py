import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from backend.config import APP_NAME, APP_VERSION, ENVIRONMENT, APP_BASE_URL, validate_production_config
from backend.database import init_db
from backend.routers import auth, account, chat, conversations, memory, search

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
STATIC_DIR = FRONTEND_DIR / "static"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail fast on startup in production if any required environment variable is missing
    validate_production_config()
    # Initialize database tables and migrations
    init_db()
    yield

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    lifespan=lifespan
)

# Security Headers & CSP Middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "microphone=(self), camera=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://unpkg.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: blob: https:; "
        "connect-src 'self' https:; "
        "media-src 'self' blob: data:;"
    )
    if ENVIRONMENT == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# CORS configuration restricted to authorized domains
cors_origins = ["http://localhost:8000", "http://127.0.0.1:8000", "http://localhost:3000"]
if APP_BASE_URL:
    clean_base = APP_BASE_URL.rstrip("/")
    if clean_base not in cors_origins:
        cors_origins.append(clean_base)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins if ENVIRONMENT == "production" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(auth.router)
app.include_router(account.router)
app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(memory.router)
app.include_router(search.router)

# Health check endpoint for Render
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "app": APP_NAME,
        "version": APP_VERSION,
        "environment": ENVIRONMENT
    }

# PWA service worker and manifest served at root scope
@app.get("/sw.js")
async def serve_service_worker():
    sw_file = STATIC_DIR / "sw.js"
    if sw_file.exists():
        return FileResponse(sw_file, media_type="application/javascript")
    return JSONResponse(status_code=404, content={"error": "sw.js not found"})

@app.get("/manifest.json")
async def serve_manifest():
    manifest_file = STATIC_DIR / "manifest.json"
    if manifest_file.exists():
        return FileResponse(manifest_file, media_type="application/manifest+json")
    return JSONResponse(status_code=404, content={"error": "manifest.json not found"})

# Static assets
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Serve Frontend SPA
@app.get("/")
async def serve_index():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "GoldSea Chatbot API is operational. Frontend index.html not yet built."}
