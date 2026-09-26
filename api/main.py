"""Merchant service (port MERCHANT_PORT). Owns catalog, cart pricing, orders,
and the shopping intent layer. Learns only {verified, transaction_id} from
the issuer (non-negotiable §2.5).
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.agentic_shopping import router as agentic_shopping_router
from api.catalog import router as catalog_router
from api.checkout import router as checkout_router
from api.config import WEB_ORIGIN
from api.db import init_db
from api.shopping import router as shopping_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Timbre merchant (Seaside Market)", lifespan=lifespan)
app.include_router(catalog_router)
app.include_router(checkout_router)
app.include_router(shopping_router)
app.include_router(agentic_shopping_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[WEB_ORIGIN],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
