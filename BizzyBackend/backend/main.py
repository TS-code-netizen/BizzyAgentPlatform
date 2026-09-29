from __future__ import annotations

import os
import logging

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router as api_router
from backend.audit.store import AuditUnavailable
from backend.security.auth import auth_required
from backend.tools import demo_data

# Load environment variables from .env file
load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

app = FastAPI(title="BizzyBee Backend", version="0.1.0")
if auth_required():
    for required in ("COGNITO_ISSUER", "COGNITO_CLIENT_ID", "BIZZY_AUDIT_TABLE", "CORS_ORIGINS"):
        if not os.getenv(required):
            raise RuntimeError(f"{required} is required outside development/test.")

# Enable direct browser requests from configured frontends.
cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]
if auth_required() and any(not origin.startswith("https://") or "*" in origin for origin in cors_origins):
    raise RuntimeError("Deployed CORS origins must be explicit HTTPS origins.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.exception_handler(AuditUnavailable)
async def audit_unavailable_handler(request, exc):
    return JSONResponse(status_code=503, content={"detail": "Audit storage unavailable; no action executed."})

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, str]:
    required = ("sales", "products", "inventory", "inventory_history", "invoices", "customer_feedback", "customer_enquiries", "returns", "refunds")
    if any(not (demo_data.DATA_DIR / f"{name}.csv").is_file() for name in required):
        raise HTTPException(503, "Packaged data is unavailable.")
    return {"status": "ready", "as_of": demo_data.as_of_date().isoformat()}
