"""Catalog and cart adapter for finalized agentic-shopping requests.

Selection is deterministic and catalog-bound. The agent can prepare a priced
browser cart, but it cannot create an order, contact the issuer, or pay.
"""
import re
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from api.cart import CartError, price_cart
from api.catalog import list_catalog
from api.checkout import CartLine
from api.config import MAX_CART_LINES, MAX_QUANTITY, MERCHANT_ID
from api.final_intent import FinalShoppingIntent, FinalizedShoppingRequest
from api.llm import words


# Price language describes how to rank matching products. It is not product
# metadata, so a catalog item never has to contain words such as "cheap" in
# its name. Keep this deterministic because model output can place the same
# phrase in importantRequirements even when preferCheapest is already true.
_PRICE_PHRASES = re.compile(
    r"\b(?:budget[ -]?friendly|low[ -]?cost|lowest[ -]?price|best[ -]?price|"
    r"least[ -]?expensive|most[ -]?affordable|cheap(?:est)?|affordable|"
    r"inexpensive|economical|budget)\b",
    re.IGNORECASE,
)
_PRICE_INTENSIFIERS = re.compile(r"\b(?:very|really|super|most|more)\b", re.IGNORECASE)


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
    quantity: int = Field(default=1, ge=1)   # units to add: the request's, or as many as fit


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


def _unverified_preferences(intent: FinalShoppingIntent, selected: CatalogProduct | None = None) -> list[str]:
    """Soft preferences the catalog cannot confirm for the chosen product."""
    result = []
    if intent.color and (selected is None or not words(intent.color) <= _searchable_words(selected)):
        result.append(f"color: {intent.color}")
    if intent.useCase:
        result.append(f"use case: {intent.useCase}")
    result.extend(f"preference: {item}" for item in intent.optionalPreferences)
    return result


def _searchable_words(product: CatalogProduct) -> set[str]:
    return words(f"{product.name} {product.category} {product.brand}")


def _without_price_language(requirement: str) -> tuple[str | None, bool]:
    """Return any real product requirement left after price language.

    "very cheap" becomes no hard requirement. "cheap organic" still requires
    organic. Phrases such as "low sodium" remain untouched.
    """
    stripped, count = _PRICE_PHRASES.subn(" ", requirement)
    if count == 0:
        return requirement, False
    stripped = _PRICE_INTENSIFIERS.sub(" ", stripped)
    stripped = " ".join(stripped.split())
    return stripped or None, True


def _coverage(requested: str, available: set[str]) -> float:
    """Share of the requested words the product explains. Two heard words
    that form one catalog word ("gold fish" for Goldfish) count as a match."""
    tokens = [t for t in re.findall(r"[A-Za-z0-9]+", requested) if words(t)]
    seq = [next(iter(words(t))) for t in tokens]
    if not seq:
        return 0.0
    matched: set[int] = set()
    for i, word in enumerate(seq):
        if word in available:
            matched.add(i)
        elif i + 1 < len(seq) and words(tokens[i] + tokens[i + 1]) & available:
            matched |= {i, i + 1}
    return len(matched) / len(seq)


def _dollars(cents: int) -> str:
    return f"${cents / 100:.2f}"


def _label(product: CatalogProduct) -> str:
    """ "Coca-Cola Mini Cans", not "Coca-Cola Coca-Cola Mini Cans"."""
    if words(product.brand) <= words(product.name):
        return product.name
    return f"{product.brand} {product.name}"


def search_products(intent: FinalShoppingIntent, catalog: list[dict],
                    in_cart: dict[str, int] | None = None) -> tuple[list[ProductMatch], str | None]:
    """Filter hard constraints, then rank. With no match, say which constraint
    ruled everything out, so the shopper can change just that."""
    if intent.merchantPreference and not _merchant_matches(intent.merchantPreference):
        return [], "The requested merchant is not this store."
    if intent.currency and intent.currency.upper() != "USD":
        return [], "This catalog is priced in USD, so Timbre will not convert the confirmed budget."

    product_words = words(intent.product)
    if not product_words:
        raise CommerceError("The finalized product is empty")

    products = [CatalogProduct.model_validate(raw) for raw in catalog]
    coverage = {p.id: _coverage(intent.product, _searchable_words(p)) for p in products}
    candidates = [p for p in products if coverage[p.id] > 0.5]
    if not candidates:
        return [], f"This store does not sell {intent.product}."
    candidates.sort(key=lambda p: (-coverage[p.id], p.price_cents, p.id))

    if intent.brand:
        branded = [p for p in candidates if _matches_words(intent.brand, p.brand)]
        if not branded:
            return [], (f"This store does not carry {intent.brand} {intent.product}. "
                        f"It has {_label(candidates[0])}.")
        candidates = branded
    if intent.size:
        # Pack sizes often live in the name ("Mini Cans, 6 Pack"), not the size column.
        sized = [p for p in candidates if _matches_words(intent.size, f"{p.size} {p.name}")]
        if not sized:
            sizes = ", ".join(sorted({p.size for p in candidates}))
            return [], f"No {intent.product} in size {intent.size}. This store has {sizes}."
        candidates = sized
    requirements: list[str] = []
    price_preference = intent.preferCheapest
    for requirement in intent.importantRequirements:
        catalog_requirement, mentions_price = _without_price_language(requirement)
        price_preference = price_preference or mentions_price
        if catalog_requirement:
            requirements.append(catalog_requirement)
    price_preference = price_preference or any(
        _without_price_language(preference)[1]
        for preference in intent.optionalPreferences
    )
    for requirement in requirements:
        meeting = [p for p in candidates
                   if _matches_words(requirement, f"{p.name} {p.category} {p.brand} {p.size}")]
        if not meeting:
            return [], f"No {intent.product} here is described as {requirement}."
        candidates = meeting
    in_cart = in_cart or {}
    units = {p.id: intent.quantity or 1 for p in candidates}
    if intent.maxPrice is not None:
        # A maximum must never be rounded upward beyond what the user confirmed.
        limit_cents = int(Decimal(str(intent.maxPrice)) * 100)
        if intent.quantityMode == "fill_budget":
            # As many as fit, within the store's per-item maximum.
            units = {p.id: min(limit_cents // p.price_cents, MAX_QUANTITY - in_cart.get(p.id, 0))
                     for p in candidates}
            affordable = [p for p in candidates if units[p.id] >= 1]
        elif intent.pricePer == "each":
            affordable = [p for p in candidates if p.price_cents <= limit_cents]
        else:
            affordable = [p for p in candidates if p.price_cents * units[p.id] <= limit_cents]
        if not affordable:
            cheapest = min(candidates, key=lambda p: p.price_cents)
            if intent.quantityMode == "fill_budget" and cheapest.price_cents <= limit_cents:
                return [], f"Your cart already has the most allowed of {_label(cheapest)}."
            count = units[cheapest.id] if intent.quantityMode == "exact" and intent.pricePer == "total" else 1
            each = " each" if intent.pricePer == "each" else ""
            return [], (f"The lowest-priced match, {_label(cheapest)}, costs "
                        f"{_dollars(cheapest.price_cents * count)}{f' for {count}' if count > 1 else ''}, "
                        f"over your {_dollars(limit_cents)}{each} limit.")
        candidates = affordable

    soft_terms = ([intent.useCase] if intent.useCase else []) + intent.optionalPreferences
    soft_terms += [intent.color] if intent.color else []
    matches: list[ProductMatch] = []
    tier: dict[str, tuple] = {}
    for product in candidates:
        available_words = _searchable_words(product)
        # Prefer names that are mostly the request: "peanut butter" is the jar,
        # not the peanut butter energy bar.
        name_words = words(product.name)
        precision = len(product_words & name_words) / len(name_words) if name_words else 0
        soft_hits = sum(1 for term in soft_terms if words(term) & available_words)
        score = round(coverage[product.id] * 100 + precision * 10 + soft_hits, 3)
        # "The cheapest" chooses by price, but only among real matches (the
        # jar, not the energy bar), so the relevance tier comes first.
        tier[product.id] = (-coverage[product.id], -(precision >= 0.5))
        matches.append(ProductMatch(product=product, score=score, quantity=units[product.id]))

    if price_preference:
        matches.sort(key=lambda m: (*tier[m.product.id], m.product.price_cents, -m.score, m.product.id))
    else:
        matches.sort(key=lambda m: (-m.score, m.product.price_cents, m.product.id))
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


def _added_message(intent: FinalShoppingIntent, product: CatalogProduct, units: int) -> str:
    line = f"Added {units} × {_label(product)} ({_dollars(product.price_cents)} each"
    if units > 1:
        line += f", {_dollars(product.price_cents * units)} total"
    line += ") to your cart."
    if intent.quantityMode == "fill_budget":
        limit_cents = int(Decimal(str(intent.maxPrice)) * 100)
        fits = limit_cents // product.price_cents
        why = ("the most allowed per item" if units < fits
               else f"as many as fit in {_dollars(limit_cents)}")
        line += f" That is {why}, before tax and delivery."
    return line


def prepare_commerce_cart(body: CommerceRequest) -> CommerceResult:
    """Choose one matching product and return a server-priced cart payload."""
    intent = body.finalizedRequest.finalIntent
    in_cart = {line.product_id: line.quantity for line in body.existingItems}
    matches, reason = search_products(intent, list_catalog(), in_cart)
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

    selected, units = matches[0].product, matches[0].quantity
    items = _merge_cart(body.existingItems, selected.id, units)
    try:
        quote = price_cart([(line.product_id, line.quantity) for line in items])
    except CartError as exc:
        raise CommerceError(str(exc)) from exc
    return CommerceResult(
        status="cart_ready",
        message=_added_message(intent, selected, units),
        selectedProduct=selected,
        rankedProducts=matches[:5],
        addedQuantity=units,
        items=items,
        quote=quote,
        unverifiedPreferences=_unverified_preferences(intent, selected),
    )
