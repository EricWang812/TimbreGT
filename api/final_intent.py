"""Finalize resolved agentic-shopping state into a commerce request."""
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.ambiguity_resolution import (
    ClarificationAnswer,
    ClarificationState,
    build_clarification_state,
)
from api.openai_intent import ShoppingIntent

_USD = {"usd", "us", "dollar", "dollars", "us dollar", "us dollars", "$", "buck", "bucks"}


class FinalIntentError(ValueError):
    """Clarification state cannot yet become a safe shopping request."""


class FinalShoppingIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["shop"] = "shop"
    product: str
    brand: str | None = None
    maxPrice: float | None = Field(default=None, ge=0)   # None: the shopper named no limit
    pricePer: Literal["total", "each"] = "total"
    currency: str | None = None
    # None with quantityMode fill_budget: the store counts how many fit the limit.
    quantity: int | None = Field(default=None, ge=1)
    quantityMode: Literal["exact", "fill_budget"] = "exact"
    preferCheapest: bool = False
    size: str | None = None
    color: str | None = None
    merchantPreference: str | None = None
    useCase: str | None = None
    importantRequirements: list[str] = Field(default_factory=list)
    optionalPreferences: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def quantity_matches_mode(self):
        if self.quantityMode == "exact" and self.quantity is None:
            raise ValueError("an exact request needs a quantity")
        if self.quantityMode == "fill_budget" and (self.maxPrice is None or self.quantity is not None):
            raise ValueError("as many as fit needs a price limit and no fixed quantity")
        return self


class FinalizedShoppingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rawTranscript: str
    extractedIntent: ShoppingIntent
    clarificationAnswers: dict[str, ClarificationAnswer]
    assumptions: list[str] = Field(default_factory=list)
    finalIntent: FinalShoppingIntent


def normalize_currency(currency: str | None) -> str | None:
    """"dollars" and "$" are USD; anything else keeps its code for the catalog check."""
    if currency is None or not currency.strip():
        return None
    return "USD" if currency.strip().lower() in _USD else currency.strip().upper()


def _text(state: ClarificationState, field: str) -> str | None:
    value = state.resolvedValues.get(field, state.acceptedValues.get(field))
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise FinalIntentError(f"Resolved {field} must be text")
    return value


def _final_list_field(state: ClarificationState, field: str, original: list[str]) -> list[str]:
    aside = {item.text for item in state.setAside if item.field == field}
    values = [item for item in original if item not in aside]
    if field not in state.resolvedValues:
        return values

    answer = state.clarificationAnswers.get(field)
    has_original_ambiguity = any(
        ambiguity.field == field and ambiguity.material
        for ambiguity in state.extractedIntent.ambiguities
    )
    if answer is not None and answer.action == "confirm" and not has_original_ambiguity:
        return values

    for ambiguity in state.extractedIntent.ambiguities:
        if ambiguity.field != field or not ambiguity.material:
            continue
        values = [item for item in values if item not in {ambiguity.heard, ambiguity.proposed}]
    resolved = state.resolvedValues[field]
    if not isinstance(resolved, str):
        raise FinalIntentError(f"Resolved {field} must be text")
    if resolved not in values:
        values.append(resolved)
    return values


def finalize_shopping_intent(state: ClarificationState) -> FinalizedShoppingRequest:
    """Recompute state and emit only confirmed, clearly heard, or disclosed-default facts."""
    try:
        current = build_clarification_state(
            state.rawTranscript,
            state.extractedIntent,
            state.clarificationAnswers,
        )
    except ValueError as exc:
        raise FinalIntentError(str(exc)) from exc

    if current.pendingClarifications:
        field = current.pendingClarifications[0].field
        raise FinalIntentError(f"Resolve the {field} clarification before shopping")
    intent = current.extractedIntent
    # "unclear" becomes shopping only once the shopper has confirmed the product.
    if intent.intent == "not_shopping" or (intent.intent == "unclear" and "product" not in current.resolvedValues):
        raise FinalIntentError("That did not sound like a shopping request. Say what you would like to buy.")

    product = _text(current, "product")
    if product is None:
        raise FinalIntentError("Say what you would like to buy before shopping")

    max_price = current.resolvedValues.get("maxPrice", current.acceptedValues.get("maxPrice"))
    if max_price is not None and (
        isinstance(max_price, bool)
        or not isinstance(max_price, (int, float))
        or not math.isfinite(max_price)
    ):
        raise FinalIntentError("Resolved maximum price must be numeric")

    fill = current.acceptedValues.get("quantityMode") == "fill_budget"
    quantity = None if fill else current.resolvedValues.get("quantity", current.acceptedValues.get("quantity"))
    if fill and max_price is None:
        raise FinalIntentError("Say how much you want to spend before shopping")
    if not fill and (quantity is None or isinstance(quantity, bool) or not isinstance(quantity, int)):
        raise FinalIntentError("Resolved quantity must be a whole number")

    price_from_speech = "maxPrice" not in current.resolvedValues and max_price is not None
    final = FinalShoppingIntent(
        product=product,
        brand=_text(current, "brand"),
        maxPrice=None if max_price is None else float(max_price),
        pricePer="each" if price_from_speech and current.acceptedValues.get("pricePer") == "each" and not fill
        else "total",
        currency=normalize_currency(intent.maxPrice.currency) if price_from_speech else None,
        quantity=quantity,
        quantityMode="fill_budget" if fill else "exact",
        preferCheapest=intent.preferCheapest,
        size=_text(current, "size"),
        color=_text(current, "color"),
        merchantPreference=_text(current, "merchantPreference"),
        useCase=_text(current, "useCase"),
        importantRequirements=_final_list_field(
            current, "importantRequirements", intent.importantRequirements
        ),
        optionalPreferences=_final_list_field(
            current, "optionalPreferences", intent.optionalPreferences
        ),
    )
    return FinalizedShoppingRequest(
        rawTranscript=current.rawTranscript,
        extractedIntent=current.extractedIntent,
        clarificationAnswers=current.clarificationAnswers,
        assumptions=current.assumptions,
        finalIntent=final,
    )
