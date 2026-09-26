"""Issuer service (port ISSUER_PORT). Owns identity, tokens, and payment calls.

Non-negotiable §2.1: nothing under issuer/ may import an ASR model.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from issuer.approvals import router as approvals_router
from issuer.config import WEB_ORIGIN
from issuer.db import init_db
from issuer.enrollment import router as enrollment_router  # imports ml.encoder: the model loads here, once
from issuer.payments import get_provider
from issuer.webauthn_routes import router as passkey_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    app.state.provider = get_provider()
    yield


app = FastAPI(title="Timbre issuer", lifespan=lifespan)
app.include_router(approvals_router)
app.include_router(enrollment_router)
app.include_router(passkey_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[WEB_ORIGIN],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.get("/healthz")
def healthz() -> dict:
    # Reaching this handler means ml.encoder imported, so the model is resident
    # and warmed. Hit this before a demo (docs/DEMO.md).
    return {"status": "ok", "encoder": "resident"}
