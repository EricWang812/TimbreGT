"""Catalog and cart adapter for finalized agentic-shopping requests.

Selection is deterministic and catalog-bound. The agent can prepare a priced
browser cart, but it cannot create an order, contact the issuer, or pay.
"""
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from api.cart import CartError, price_cart
from api.catalog import list_catalog
from api.checkout import CartLine
from api.config import MAX_CART_LINES, MAX_QUANTITY, MERCHANT_ID
from api.final_intent import FinalShoppingIntent, FinalizedShoppingRequest
from api.llm import words


class CommerceError(ValueError):
    """A finalized request cannot safely prepare a cart."""


class CommerceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finalizedRequest: FinalizedShoppingRequest
    existingItems: list[CartLine] = Field(default_factory=list, max_length=MAX_CART_LINES)


class CatalogProduct(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    brand: str
    size: str
    category: str
    price_cents: int
    image_url: str
    image_credit: str


class ProductMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product: CatalogProduct
    score: float


class CommerceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["cart_ready", "no_matches"]
    message: str
    selectedProduct: CatalogProduct | None
    rankedProducts: list[ProductMatch]
    addedQuantity: int
    items: list[CartLine]
    quote: dict | None
    unverifiedPreferences: list[str]


def _matches_words(requested: str, available: str) -> bool:
    requested_words = words(requested)
    return bool(requested_words) and requested_words <= words(available)


def _merchant_matches(requested: str) -> bool:
    available = f"{MERCHANT_ID} Seaside Market"
    requested_words = words(requested)
    available_words = words(available)
    return bool(requested_words) and (
        requested_words <= available_words or available_words <= requested_words
    )


def _unverified_preferences(intent: FinalShoppingIntent) -> list[str]:
    result = []
    if intent.useCase:
        result.append(f"use case: {intent.useCase}")
    result.extend(f"preference: {item}" for item in intent.optionalPreferences)
    return result


def search_products(intent: FinalShoppingIntent, catalog: list[dict]) -> tuple[list[ProductMatch], str | None]:
    """Filter hard constraints and rank soft preferences against catalog data."""
    if intent.merchantPreference and not _merchant_matches(intent.merchantPreference):
        return [], "The requested merchant is not this store."
    if intent.currency and intent.currency.upper() != "USD":
        return [], "This catalog is priced in USD, so Timbre will not convert the confirmed budget."
    if intent.color:
        return [], "This catalog does not describe product color, so Timbre will not guess a variant."

    product_words = words(intent.product)
    if not product_words:
        raise CommerceError("The finalized product is empty")
    # A maximum must never be rounded upward beyond what the user confirmed.
    max_line_cents = int(Decimal(str(intent.maxPrice)) * 100)
    matches: list[ProductMatch] = []

    for raw_product in catalog:
        product = CatalogProduct.model_validate(raw_product)
        searchable = f"{product.name} {product.category} {product.brand}"
        available_words = words(searchable)
        coverage = len(product_words & available_words) / len(product_words)
        if coverage <= 0.5:
            continue
        if intent.brand and not _matches_words(intent.brand, product.brand):
            continue
        if intent.size and not _matches_words(intent.size, product.size):
            continue
        if product.price_cents * intent.quantity > max_line_cents:
            continue
        if any(not _matches_words(requirement, searchable + " " + product.size)
               for requirement in intent.importantRequirements):
            continue

        soft_terms = ([intent.useCase] if intent.useCase else []) + intent.optionalPreferences
        soft_hits = sum(
            1 for term in soft_terms if words(term) & available_words
        )
        score = round(coverage * 100 + soft_hits, 3)
        matches.append(ProductMatch(product=product, score=score))

    matches.sort(key=lambda match: (-match.score, match.product.price_cents, match.product.id))
    return matches, None


def _merge_cart(existing: list[CartLine], product_id: str, quantity: int) -> list[CartLine]:
    if quantity > MAX_QUANTITY:
        raise CommerceError(f"Quantity cannot exceed {MAX_QUANTITY}")
    quantities = {line.product_id: line.quantity for line in existing}
    if len(quantities) != len(existing):
        raise CommerceError("Combine duplicate existing cart lines before agentic shopping")
    quantities[product_id] = quantities.get(product_id, 0) + quantity
    if quantities[product_id] > MAX_QUANTITY:
        raise CommerceError(f"Adding this request would exceed the maximum quantity of {MAX_QUANTITY}")
    if len(quantities) > MAX_CART_LINES:
        raise CommerceError("The cart has too many different products")
    return [CartLine(product_id=pid, quantity=qty) for pid, qty in quantities.items()]


def prepare_commerce_cart(body: CommerceRequest) -> CommerceResult:
    """Choose one matching product and return a server-priced cart payload."""
    intent = body.finalizedRequest.finalIntent
    matches, reason = search_products(intent, list_catalog())
    if not matches:
        return CommerceResult(
            status="no_matches",
            message=reason or "No catalog product satisfies all confirmed constraints.",
            selectedProduct=None,
            rankedProducts=[],
            addedQuantity=0,
            items=body.existingItems,
            quote=None,
            unverifiedPreferences=_unverified_preferences(intent),
        )

    selected = matches[0].product
    items = _merge_cart(body.existingItems, selected.id, intent.quantity)
    try:
        quote = price_cart([(line.product_id, line.quantity) for line in items])
    except CartError as exc:
        raise CommerceError(str(exc)) from exc
    return CommerceResult(
        status="cart_ready",
        message=f"Prepared {intent.quantity} {selected.name} in the cart.",
        selectedProduct=selected,
        rankedProducts=matches[:5],
        addedQuantity=intent.quantity,
        items=items,
        quote=quote,
        unverifiedPreferences=_unverified_preferences(intent),
    )
