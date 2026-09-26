"""Merchant service (port MERCHANT_PORT). Owns catalog, cart pricing, orders,
and the shopping intent layer. Learns only {verified, transaction_id} from
the issuer (non-negotiable §2.5).
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.agentic_shopping import router as agentic_shopping_router
from api.buyer_auth import router as buyer_auth_router
from api.buyer_addresses import router as buyer_addresses_router
from api.catalog import router as catalog_router
from api.checkout import router as checkout_router
from api.config import WEB_ORIGIN
from api.db import init_db
from api.fulfillment_selection import router as fulfillment_selection_router
from api.market_auth import router as market_auth_router
from api.market_orders import owner_router as market_order_dashboard_router, router as market_orders_router
from api.market_products import router as market_products_router
from api.marketplace_catalog import router as marketplace_catalog_router
from api.markets import router as markets_router
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
app.include_router(market_auth_router)
app.include_router(buyer_auth_router)
app.include_router(buyer_addresses_router)
app.include_router(fulfillment_selection_router)
app.include_router(market_orders_router)
app.include_router(market_order_dashboard_router)
app.include_router(markets_router)
app.include_router(market_products_router)
app.include_router(marketplace_catalog_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[WEB_ORIGIN],
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
    allow_credentials=True,
)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
