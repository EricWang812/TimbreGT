"""Finalize resolved agentic-shopping state into a commerce request."""
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from api.ambiguity_resolution import (
    MANDATORY_FIELDS,
    ClarificationAnswer,
    ClarificationState,
    build_clarification_state,
)
from api.openai_intent import ShoppingIntent, TextField


class FinalIntentError(ValueError):
    """Clarification state cannot yet become a safe shopping request."""


class FinalShoppingIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["shop"] = "shop"
    product: str
    brand: str | None = None
    maxPrice: float = Field(ge=0)
    currency: str | None = None
    quantity: int = Field(ge=1)
    size: str | None = None
    color: str | None = None
    merchantPreference: str | None = None
    useCase: str | None = None
    importantRequirements: list[str] = Field(default_factory=list)
    optionalPreferences: list[str] = Field(default_factory=list)


class FinalizedShoppingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rawTranscript: str
    extractedIntent: ShoppingIntent
    clarificationAnswers: dict[str, ClarificationAnswer]
    finalIntent: FinalShoppingIntent


def _confirmed_text(
    field: str,
    extracted: TextField,
    resolved: dict[str, str | int | float],
) -> str | None:
    if field in resolved:
        value = resolved[field]
        if not isinstance(value, str) or not value:
            raise FinalIntentError(f"Resolved {field} must be text")
        return value
    if extracted.confidence != "high":
        return None
    return extracted.value


def _final_list_field(state: ClarificationState, field: str, original: list[str]) -> list[str]:
    if field not in state.resolvedValues:
        return list(original)

    answer = state.clarificationAnswers.get(field)
    has_original_ambiguity = any(
        ambiguity.field == field and ambiguity.material
        for ambiguity in state.extractedIntent.ambiguities
    )
    if answer is not None and answer.action == "confirm" and not has_original_ambiguity:
        return list(original)

    values = list(original)
    for ambiguity in state.extractedIntent.ambiguities:
        if ambiguity.field != field or not ambiguity.material:
            continue
        values = [
            item for item in values
            if item not in {ambiguity.heard, ambiguity.proposed}
        ]
    resolved = state.resolvedValues[field]
    if not isinstance(resolved, str):
        raise FinalIntentError(f"Resolved {field} must be text")
    if resolved not in values:
        values.append(resolved)
    return values


def finalize_shopping_intent(state: ClarificationState) -> FinalizedShoppingRequest:
    """Recompute state and emit only confirmed or high-confidence facts."""
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
    if current.extractedIntent.intent != "shop":
        raise FinalIntentError("The request is not confirmed as a shopping request")

    unknown_missing = [
        field for field in current.extractedIntent.missingInformation
        if field in MANDATORY_FIELDS and field not in current.resolvedValues
    ]
    if unknown_missing:
        raise FinalIntentError(f"Resolve missing information before shopping: {unknown_missing[0]}")

    intent = current.extractedIntent
    resolved = current.resolvedValues
    product = _confirmed_text("product", intent.product, resolved)
    if product is None:
        raise FinalIntentError("Confirm the product before shopping")

    max_price = resolved.get("maxPrice")
    if max_price is None and intent.maxPrice.confidence == "high":
        max_price = intent.maxPrice.value
    if max_price is None:
        raise FinalIntentError("Confirm the maximum price before shopping")
    if max_price is not None and (
        isinstance(max_price, bool)
        or not isinstance(max_price, (int, float))
        or not math.isfinite(max_price)
    ):
        raise FinalIntentError("Resolved maximum price must be numeric")

    quantity = resolved.get("quantity")
    if quantity is None and intent.quantity.confidence == "high":
        quantity = intent.quantity.value
    if quantity is None:
        raise FinalIntentError("Confirm the quantity before shopping")
    if quantity is not None and (isinstance(quantity, bool) or not isinstance(quantity, int)):
        raise FinalIntentError("Resolved quantity must be a whole number")

    final = FinalShoppingIntent(
        product=product,
        brand=_confirmed_text("brand", intent.brand, resolved),
        maxPrice=float(max_price),
        currency=(
            intent.maxPrice.currency
            if intent.maxPrice.confidence == "high"
            else None
        ),
        quantity=quantity,
        size=_confirmed_text("size", intent.size, resolved),
        color=_confirmed_text("color", intent.color, resolved),
        merchantPreference=_confirmed_text("merchantPreference", intent.merchantPreference, resolved),
        useCase=_confirmed_text("useCase", intent.useCase, resolved),
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
        finalIntent=final,
    )
