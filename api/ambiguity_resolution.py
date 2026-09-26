"""Deterministic clarification policy for agentic shopping.

Ask only when a wrong guess would put the wrong thing in the cart:
- values the model heard clearly (confidence high) are accepted without a
  question;
- a missing quantity means AGENTIC_DEFAULT_QUANTITY and a missing budget
  means no price limit, and both assumptions are disclosed to the shopper;
- only the product is required, and it is asked for only when absent;
- uncertain values (medium or low) and model-flagged material ambiguities
  get one Yes/No question each;
- a heard word that sounds like a store brand ("boys" for Bose) is proposed
  as that brand once, never accepted without a Yes, and the same words are
  not also asked about as another field.

The client carries this state using the application's existing local state
pattern. The raw transcript and the model's interpretation stay immutable;
answers, accepted values, assumptions, and set-aside words are stored
separately, and the state is recomputed from them on every call.
"""
import difflib
import math
import re
import unicodedata
from dataclasses import dataclass, field as dc_field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.catalog import list_catalog
from api.config import AGENTIC_BRAND_MATCH_RATIO, AGENTIC_DEFAULT_QUANTITY
from api.llm import words
from api.openai_intent import Ambiguity, ShoppingIntent

ClarificationAction = Literal["confirm", "reject", "correct"]
ResolvedValue = str | int | float
REQUIRED_FIELDS = ("product",)
UNCERTAIN = {"medium", "low"}
TEXT_FIELDS = ("product", "brand", "size", "color", "merchantPreference", "useCase")
# Words that never stand for a brand on their own.
_FILLER = {"for", "the", "and", "with", "my", "some", "any", "one", "two", "under", "over", "a", "an"}

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


class SetAside(BaseModel):
    """Words the model filed under one field that were re-read as a brand."""
    model_config = ConfigDict(extra="forbid")

    field: str
    text: str


class ClarificationState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rawTranscript: str
    extractedIntent: ShoppingIntent
    clarificationAnswers: dict[str, ClarificationAnswer] = Field(default_factory=dict)
    resolvedValues: dict[str, ResolvedValue] = Field(default_factory=dict)
    acceptedValues: dict[str, ResolvedValue] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)
    setAside: list[SetAside] = Field(default_factory=list)
    pendingClarifications: list[Clarification] = Field(default_factory=list)
    complete: bool = False


# --- Store vocabulary --------------------------------------------------------

@dataclass(frozen=True)
class StoreVocabulary:
    brands: tuple[str, ...]
    product_words: frozenset[str]   # descriptive words ("organic", "vanilla") are never brand guesses


def store_vocabulary() -> StoreVocabulary:
    catalog = list_catalog()
    descriptive = set()
    for product in catalog:
        descriptive |= words(f"{product['name']} {product['category']} {product['size']}")
    return StoreVocabulary(
        brands=tuple(sorted({product["brand"] for product in catalog})),
        product_words=frozenset(descriptive),
    )


def _letters(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", folded)


def _sound_key(letters: str) -> str:
    """A rough sound-alike key: first letter, then consonants, repeats collapsed.
    "boys" and "bose" both give "bs"; "sunny" and "sony" both give "sn"."""
    text = letters.replace("ph", "f").replace("ck", "k").replace("q", "k").replace("z", "s")
    if not text:
        return ""
    tail = re.sub(r"[aeiouyhw]", "", text[1:])
    return re.sub(r"(.)\1+", r"\1", text[0] + tail)


def is_store_brand(value: str, vocabulary: StoreVocabulary) -> bool:
    return any(_letters(value) == _letters(brand) for brand in vocabulary.brands)


def _phrases(heard: str) -> list[str]:
    tokens = [t for t in re.findall(r"[A-Za-z0-9']+", heard) if _letters(t) not in _FILLER]
    return tokens + [f"{a} {b}" for a, b in zip(tokens, tokens[1:])]


def _likeness(heard_letters: str, brand: str) -> float:
    """1.0 for the brand itself, else spelling similarity, lifted to 0.9 when it sounds the same."""
    best = 0.0
    for candidate in {_letters(brand)} | {w for w in map(_letters, brand.split()) if len(w) >= 3}:
        if heard_letters == candidate:
            return 1.0
        score = difflib.SequenceMatcher(None, heard_letters, candidate).ratio()
        key = _sound_key(candidate)
        if len(key) >= 2 and key == _sound_key(heard_letters):
            score = max(score, 0.9)
        best = max(best, score)
    return best


def closest_store_brand(heard: str, vocabulary: StoreVocabulary) -> str | None:
    """The store brand these words most likely were, or None. Exact brand
    names return None: that is the brand itself, not a mishearing."""
    best, best_score = None, 0.0
    for phrase in _phrases(heard):
        heard_letters = _letters(phrase)
        if len(heard_letters) < 3 or heard_letters in vocabulary.product_words:
            continue
        for brand in vocabulary.brands:
            score = _likeness(heard_letters, brand)
            if score == 1.0:
                return None
            if score > best_score:
                best, best_score = brand, score
    return best if best_score >= AGENTIC_BRAND_MATCH_RATIO else None


def brand_was_said(heard: str | None, brand: str, vocabulary: StoreVocabulary) -> bool:
    """False when a store brand was inferred from the product ("OJ" as Simply
    Orange) rather than said or misheard ("boys" as Bose, "jiffy" as Jif)."""
    if not is_store_brand(brand, vocabulary):
        return True   # not the store's to infer; the catalog check handles it
    return any(len(_letters(p)) >= 2 and _likeness(_letters(p), brand) >= AGENTIC_BRAND_MATCH_RATIO
               for p in _phrases(heard or ""))


# --- The plan: which questions, which repairs -------------------------------

@dataclass
class _Plan:
    questions: dict[str, Ambiguity] = dc_field(default_factory=dict)
    # A brand proposed from words filed under other fields: field -> those words.
    repairs: dict[str, list[SetAside]] = dc_field(default_factory=dict)
    # Fields the model filled from the catalog, not from anything said.
    ignored: set[str] = dc_field(default_factory=set)


def _wording(field: str, heard: str | None, proposed: str | None) -> str:
    """Short, uniform questions, whatever wording the model suggested."""
    if proposed is None:
        return f"What {FIELD_LABELS[field]} did you mean?"
    if field == "brand":
        differs = heard and _letters(heard) != _letters(proposed)
        return f'I heard "{heard}". Did you mean {proposed}?' if differs else f"Did you mean {proposed}?"
    if field == "product":
        return f"Did you want {proposed}?"
    if field == "maxPrice":
        return f"Is your limit ${proposed}?"
    if field == "quantity":
        return f"Did you want {proposed}?"
    return f"Should I use {FIELD_LABELS[field]} {proposed}?"


def _ask(field: str, heard: str | None, proposed: str | None, question: str,
         kind: str = "ambiguous") -> Ambiguity:
    return Ambiguity(field=field, kind=kind, heard=heard, proposed=proposed, question=question, material=True)


def _span(text: str | None) -> str:
    return " ".join(sorted(words(text or "")))


def _brand_repair(intent: ShoppingIntent, vocabulary: StoreVocabulary) -> tuple[Ambiguity, list[SetAside]] | None:
    """Propose a store brand for words that sound like one, or None. Every
    field holding the same words is set aside with it."""
    brand = intent.brand
    candidates: list[tuple[str, str]] = []
    if brand.value is not None:
        if is_store_brand(brand.value, vocabulary):
            return None
        candidates.append(("brand", brand.sourceText or brand.value))
    else:
        for name in ("useCase", "merchantPreference", "size", "color"):
            extracted = getattr(intent, name)
            if extracted.value is not None:
                candidates.append((name, extracted.sourceText or extracted.value))
        candidates += [("optionalPreferences", item) for item in intent.optionalPreferences]
        candidates += [("importantRequirements", item) for item in intent.importantRequirements]
    for origin, text in candidates:
        match = closest_store_brand(text, vocabulary)
        if match:
            question = _ask("brand", text, match, f'I heard "{text}". Did you mean {match}?',
                            kind="possible_transcription_error")
            same_words = [SetAside(field=name, text=other) for name, other in candidates
                          if name != "brand" and _span(other) == _span(text)]
            return question, same_words
    return None


def _plan(intent: ShoppingIntent, vocabulary: StoreVocabulary) -> _Plan:
    plan = _Plan()
    if intent.intent not in {"shop", "unclear"}:
        return plan
    spans: set[str] = set()

    def add(question: Ambiguity) -> bool:
        if question.field in plan.questions or (question.heard and _span(question.heard) in spans):
            return False  # one question per field, and one per span of words
        plan.questions[question.field] = question
        if question.heard:
            spans.add(_span(question.heard))
        return True

    # 1. Words that sound like a store brand. First, so the same words are
    #    not also asked about as a use case or preference.
    for ambiguity in intent.ambiguities:
        if ambiguity.field not in FIELD_LABELS:
            raise ResolutionError(f"Unsupported ambiguous field: {ambiguity.field}")
    repair = _brand_repair(intent, vocabulary)
    if repair:
        question, set_aside = repair
        if add(question) and set_aside:
            plan.repairs["brand"] = set_aside

    # A store brand the speaker never said (inferred from the product, as
    # "OJ" for Simply Orange) is neither asked about nor used: the store
    # chooses among brands itself.
    if intent.brand.value is not None and not brand_was_said(
            intent.brand.sourceText, intent.brand.value, vocabulary):
        plan.ignored.add("brand")

    # 2. Material ambiguities the model flagged. A proposed brand the store
    #    does not carry is swapped for the closest store brand, if any.
    for ambiguity in intent.ambiguities:
        if not ambiguity.material:
            continue
        proposed = ambiguity.proposed
        if ambiguity.field == "brand" and proposed:
            if not is_store_brand(proposed, vocabulary):
                proposed = closest_store_brand(ambiguity.heard or proposed, vocabulary) or proposed
            if not brand_was_said(ambiguity.heard, proposed, vocabulary):
                continue
        if ambiguity.field in plan.ignored:
            continue
        add(_ask(ambiguity.field, ambiguity.heard, proposed,
                 _wording(ambiguity.field, ambiguity.heard, proposed), kind=ambiguity.kind))

    # 3. The product: asked for only when absent or uncertain.
    product = intent.product
    if product.value is None:
        add(_ask("product", None, None, "What would you like to buy?"))
    elif product.confidence in UNCERTAIN or intent.intent == "unclear":
        add(_ask("product", product.sourceText, product.value,
                 _wording("product", product.sourceText, product.value)))

    # 4. Other values the model was unsure of.
    for name in TEXT_FIELDS[1:]:
        extracted = getattr(intent, name)
        if extracted.value is not None and extracted.confidence in UNCERTAIN and name not in plan.ignored:
            add(_ask(name, extracted.sourceText, extracted.value,
                     _wording(name, extracted.sourceText, extracted.value)))
    price = intent.maxPrice
    fill = intent.quantity.mode == "fill_budget"
    if fill and price.value is None:
        # "As many as I can" needs a budget to count against; it is the one thing to ask.
        add(_ask("maxPrice", None, None, "How much do you want to spend in total?"))
    if price.value is not None and price.confidence in UNCERTAIN:
        add(_ask("maxPrice", price.sourceText, f"{price.value:g}",
                 _wording("maxPrice", price.sourceText, f"{price.value:g}")))
    quantity = intent.quantity
    # An unsure "1" ("some ice cream") is the default anyway: disclose it, do not ask.
    if (not fill and quantity.value is not None and quantity.confidence in UNCERTAIN
            and quantity.value != AGENTIC_DEFAULT_QUANTITY):
        add(_ask("quantity", quantity.sourceText, str(quantity.value),
                 _wording("quantity", quantity.sourceText, str(quantity.value))))

    # Stable order, matching the final request fields.
    plan.questions = {name: plan.questions[name] for name in FIELD_LABELS if name in plan.questions}
    return plan


def _question_for(ambiguity: Ambiguity, rejected: bool) -> Clarification:
    label = FIELD_LABELS[ambiguity.field]
    if rejected or ambiguity.proposed is None:
        return Clarification(
            field=ambiguity.field,
            question=f"What {label} did you mean?" if rejected else ambiguity.question,
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


def _accepted(intent: ShoppingIntent, asked: set[str],
              set_aside: list[SetAside]) -> tuple[dict[str, ResolvedValue], list[str]]:
    """Clearly heard values, plus disclosed defaults for what was not said."""
    aside = {item.field for item in set_aside}
    accepted: dict[str, ResolvedValue] = {}
    for name in TEXT_FIELDS:
        extracted = getattr(intent, name)
        if name in asked or name in aside or extracted.confidence != "high":
            continue
        if extracted.value is not None and extracted.value.strip():
            accepted[name] = extracted.value.strip()
    assumptions: list[str] = []
    # A value marked missing is missing, whatever number came with it.
    if intent.quantity.mode == "fill_budget":
        accepted["quantityMode"] = "fill_budget"   # the store counts how many fit
    elif "quantity" not in asked:
        if intent.quantity.value is not None and intent.quantity.confidence == "high":
            accepted["quantity"] = intent.quantity.value
        else:
            accepted["quantity"] = AGENTIC_DEFAULT_QUANTITY
            assumptions.append(f"Quantity {AGENTIC_DEFAULT_QUANTITY}, since you did not say how many.")
    if "maxPrice" not in asked:
        if intent.maxPrice.value is not None and intent.maxPrice.confidence == "high":
            accepted["maxPrice"] = float(intent.maxPrice.value)
            if intent.maxPrice.per == "each":
                accepted["pricePer"] = "each"
        else:
            assumptions.append("No price limit, since you did not name one.")
    return accepted, assumptions


def build_clarification_state(
    raw_transcript: str,
    intent: ShoppingIntent,
    answers: dict[str, ClarificationAnswer] | None = None,
) -> ClarificationState:
    """Return pending questions, answers, and accepted values, recomputed."""
    saved_answers = dict(answers or {})
    plan = _plan(intent, store_vocabulary())
    questions = plan.questions
    unknown = set(saved_answers) - set(questions)
    if unknown:
        raise ResolutionError(f"No active clarification for: {sorted(unknown)[0]}")

    pending: list[Clarification] = []
    resolved: dict[str, ResolvedValue] = {}
    set_aside: list[SetAside] = []
    declined_repairs: set[str] = set()
    for name, ambiguity in questions.items():
        answer = saved_answers.get(name)
        repair = plan.repairs.get(name)
        if answer is None:
            pending.append(_question_for(ambiguity, rejected=False))
        elif answer.action == "confirm":
            if ambiguity.proposed is None:
                raise ResolutionError(f"The {FIELD_LABELS[name]} has no proposed value to confirm")
            resolved[name] = _coerce_resolved_value(name, ambiguity.proposed)
        elif answer.action == "correct":
            if answer.value is None:
                raise ResolutionError(f"The {FIELD_LABELS[name]} correction needs a value")
            resolved[name] = _coerce_resolved_value(name, answer.value)
        elif repair is not None:
            # A declined brand repair asks nothing more: the words keep their first meaning.
            declined_repairs.add(name)
        else:
            if ambiguity.proposed is None:
                raise ResolutionError(f"The {FIELD_LABELS[name]} needs a correction")
            pending.append(_question_for(ambiguity, rejected=True))
        if repair is not None and name not in declined_repairs:
            set_aside.extend(repair)

    accepted, assumptions = _accepted(intent, (set(questions) - declined_repairs) | plan.ignored, set_aside)
    return ClarificationState(
        rawTranscript=raw_transcript,
        extractedIntent=intent,
        clarificationAnswers=saved_answers,
        resolvedValues=resolved,
        acceptedValues=accepted,
        assumptions=assumptions,
        setAside=set_aside,
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
