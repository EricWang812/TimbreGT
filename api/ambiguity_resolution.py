"""Deterministic ambiguity resolution for additive agentic shopping.

The client carries this state using the application's existing local state
pattern. Raw transcription and model interpretation remain immutable while
answers and resolved values are stored separately.
"""
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.openai_intent import Ambiguity, ShoppingIntent

ClarificationAction = Literal["confirm", "reject", "correct"]
ResolvedValue = str | int | float
MANDATORY_FIELDS = ("product", "maxPrice", "quantity")

FIELD_LABELS = {
    "product": "product",
    "brand": "brand",
    "maxPrice": "maximum price",
    "quantity": "quantity",
    "size": "size",
    "color": "color",
    "merchantPreference": "merchant",
    "useCase": "use case",
    "importantRequirements": "requirement",
    "optionalPreferences": "optional preference",
}


class ResolutionError(ValueError):
    """Resolution state or an answer cannot be applied safely."""


class ClarificationOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    action: Literal["confirm", "reject"]


class Clarification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    question: str
    heard: str | None
    proposed: str | None
    options: list[ClarificationOption]
    allowsCorrection: bool = True


class ClarificationAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    action: ClarificationAction
    value: ResolvedValue | None = None

    @model_validator(mode="after")
    def validate_action_value(self):
        if self.action == "correct":
            if self.value is None or isinstance(self.value, bool):
                raise ValueError("a correction requires a value")
            if isinstance(self.value, str) and not self.value.strip():
                raise ValueError("a correction cannot be empty")
        elif self.value is not None:
            raise ValueError("only a correction may include a value")
        return self


class ClarificationState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rawTranscript: str
    extractedIntent: ShoppingIntent
    clarificationAnswers: dict[str, ClarificationAnswer] = Field(default_factory=dict)
    resolvedValues: dict[str, ResolvedValue] = Field(default_factory=dict)
    pendingClarifications: list[Clarification] = Field(default_factory=list)
    complete: bool = False


def _question_for(ambiguity: Ambiguity, rejected: bool) -> Clarification:
    label = FIELD_LABELS[ambiguity.field]
    if rejected or ambiguity.proposed is None:
        return Clarification(
            field=ambiguity.field,
            question=f"What {label} did you mean?",
            heard=ambiguity.heard,
            proposed=None,
            options=[],
        )
    return Clarification(
        field=ambiguity.field,
        question=ambiguity.question,
        heard=ambiguity.heard,
        proposed=ambiguity.proposed,
        options=[
            ClarificationOption(label="Yes", action="confirm"),
            ClarificationOption(label="No", action="reject"),
        ],
    )


def _material_questions(intent: ShoppingIntent) -> dict[str, Ambiguity]:
    questions: dict[str, Ambiguity] = {}
    for ambiguity in intent.ambiguities:
        if not ambiguity.material:
            continue
        if ambiguity.field not in FIELD_LABELS:
            raise ResolutionError(f"Unsupported ambiguous field: {ambiguity.field}")
        questions.setdefault(ambiguity.field, ambiguity)

    mandatory_values = {
        "product": intent.product.value,
        "maxPrice": intent.maxPrice.value,
        "quantity": intent.quantity.value,
    }
    missing_fields = [field for field in MANDATORY_FIELDS if mandatory_values[field] is None]
    for field in missing_fields:
        if intent.intent not in {"shop", "unclear"} or field in questions:
            continue
        questions[field] = Ambiguity(
            field=field,
            kind="ambiguous",
            heard=None,
            proposed=None,
            question=f"What {FIELD_LABELS[field]} do you need?",
            material=True,
        )

    if intent.intent in {"shop", "unclear"}:
        text_fields = {
            "product": intent.product,
            "brand": intent.brand,
            "size": intent.size,
            "color": intent.color,
            "merchantPreference": intent.merchantPreference,
            "useCase": intent.useCase,
        }
        for field, extracted in text_fields.items():
            if field in questions or extracted.value is None:
                continue
            question = (
                f"Are you looking to buy {extracted.value}?"
                if field == "product"
                else f"Should I use {FIELD_LABELS[field]} {extracted.value}?"
            )
            questions[field] = Ambiguity(
                field=field,
                kind="ambiguous",
                heard=extracted.sourceText,
                proposed=extracted.value,
                question=question,
                material=True,
            )

        if "maxPrice" not in questions and intent.maxPrice.value is not None:
            currency = f" {intent.maxPrice.currency}" if intent.maxPrice.currency else ""
            value = f"{intent.maxPrice.value:g}"
            questions["maxPrice"] = Ambiguity(
                field="maxPrice",
                kind="ambiguous",
                heard=intent.maxPrice.sourceText,
                proposed=value,
                question=f"Is your maximum price {value}{currency}?",
                material=True,
            )
        if "quantity" not in questions and intent.quantity.value is not None:
            value = str(intent.quantity.value)
            questions["quantity"] = Ambiguity(
                field="quantity",
                kind="ambiguous",
                heard=intent.quantity.sourceText,
                proposed=value,
                question=f"Do you want quantity {value}?",
                material=True,
            )
        list_fields = {
            "importantRequirements": intent.importantRequirements,
            "optionalPreferences": intent.optionalPreferences,
        }
        for field, values in list_fields.items():
            if field in questions or not values:
                continue
            proposed = "; ".join(values)
            questions[field] = Ambiguity(
                field=field,
                kind="ambiguous",
                heard=None,
                proposed=proposed,
                question=f"Should I include these {FIELD_LABELS[field]}s: {proposed}?",
                material=True,
            )

    # Keep questions in the same stable order as the final request fields.
    return {field: questions[field] for field in FIELD_LABELS if field in questions}


def _coerce_resolved_value(field: str, value: ResolvedValue) -> ResolvedValue:
    if isinstance(value, bool):
        raise ResolutionError(f"The {FIELD_LABELS[field]} correction is invalid")
    if field == "maxPrice":
        if isinstance(value, str):
            try:
                value = float(value.strip().removeprefix("$").replace(",", ""))
            except ValueError as exc:
                raise ResolutionError("The maximum price must be a number") from exc
        if not math.isfinite(value) or value < 0:
            raise ResolutionError("The maximum price must be finite and nonnegative")
        return float(value)
    if field == "quantity":
        if isinstance(value, str):
            try:
                value = float(value.strip())
            except ValueError as exc:
                raise ResolutionError("The quantity must be a whole number") from exc
        if not math.isfinite(value) or not float(value).is_integer() or value < 1:
            raise ResolutionError("The quantity must be a positive whole number")
        return int(value)
    if not isinstance(value, str) or not value.strip():
        raise ResolutionError(f"The {FIELD_LABELS[field]} must be text")
    return value.strip()


def build_clarification_state(
    raw_transcript: str,
    intent: ShoppingIntent,
    answers: dict[str, ClarificationAnswer] | None = None,
) -> ClarificationState:
    """Return pending questions and separately resolved values."""
    saved_answers = dict(answers or {})
    questions = _material_questions(intent)
    unknown = set(saved_answers) - set(questions)
    if unknown:
        raise ResolutionError(f"No active clarification for: {sorted(unknown)[0]}")

    pending: list[Clarification] = []
    resolved: dict[str, ResolvedValue] = {}
    for field, ambiguity in questions.items():
        answer = saved_answers.get(field)
        if answer is None:
            pending.append(_question_for(ambiguity, rejected=False))
        elif answer.action == "confirm":
            if ambiguity.proposed is None:
                raise ResolutionError(f"The {FIELD_LABELS[field]} has no proposed value to confirm")
            resolved[field] = _coerce_resolved_value(field, ambiguity.proposed)
        elif answer.action == "correct":
            if answer.value is None:
                raise ResolutionError(f"The {FIELD_LABELS[field]} correction needs a value")
            resolved[field] = _coerce_resolved_value(field, answer.value)
        else:
            if ambiguity.proposed is None:
                raise ResolutionError(f"The {FIELD_LABELS[field]} needs a correction")
            pending.append(_question_for(ambiguity, rejected=True))

    return ClarificationState(
        rawTranscript=raw_transcript,
        extractedIntent=intent,
        clarificationAnswers=saved_answers,
        resolvedValues=resolved,
        pendingClarifications=pending,
        complete=not pending,
    )


def apply_clarification_answer(
    state: ClarificationState,
    answer: ClarificationAnswer,
) -> ClarificationState:
    """Apply one field answer without restarting or changing prior stages."""
    current = build_clarification_state(
        state.rawTranscript,
        state.extractedIntent,
        state.clarificationAnswers,
    )
    pending = {item.field: item for item in current.pendingClarifications}
    question = pending.get(answer.field)
    if question is None:
        raise ResolutionError(f"No active clarification for: {answer.field}")
    if answer.action == "confirm" and question.proposed is None:
        raise ResolutionError(f"The {FIELD_LABELS[answer.field]} has no proposed value to confirm")
    if answer.action == "reject" and question.proposed is None:
        raise ResolutionError(f"The {FIELD_LABELS[answer.field]} needs a correction")

    updated_answers = dict(current.clarificationAnswers)
    updated_answers[answer.field] = answer
    return build_clarification_state(
        current.rawTranscript,
        current.extractedIntent,
        updated_answers,
    )
