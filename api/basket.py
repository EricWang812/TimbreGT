"""A whole spoken basket: several named items, and meals.

Each named item runs through the single-item policy unchanged (ADR 10):
clarification, finalization, and catalog search. Meals are different: the
model chose those products, not the shopper, so their ids are checked against
the catalog here and the basket is shown for confirmation before it is added.

One budget can cover everything ("keep it all under $20"). Items with a fixed
quantity and meal ingredients are counted first, in spoken order; items asked
for as "as many as fit" then share what is left.

Nothing here creates an order, contacts the issuer, or pays. The result is a
server-priced cart proposal, like prepare_commerce_cart.
"""
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from api.ambiguity_resolution import (
    Clarification,
    ClarificationAnswer,
    ClarificationState,
    ResolutionError,
    apply_clarification_answer,
    build_clarification_state,
)
from api.cart import CartError, price_cart
from api.catalog import list_catalog
from api.checkout import CartLine
from api.commerce_agent import (
    CatalogProduct,
    CommerceError,
    _dollars,
    _label,
    _unverified_preferences,
    search_products,
)
from api.config import AGENTIC_MAX_BASKET_ITEMS, MAX_CART_LINES, MAX_QUANTITY
from api.llm import words
from api.final_intent import FinalIntentError, FinalShoppingIntent, finalize_shopping_intent
from api.openai_intent import BasketIntent, ShoppingIntent

NO_LIMIT_ASSUMPTION = "No price limit, since you did not name one."


class BasketAnswer(ClarificationAnswer):
    item: int = Field(ge=0)


class BasketQuestion(Clarification):
    item: int
    itemLabel: str


class BasketState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rawTranscript: str
    extractedRequest: BasketIntent
    itemAnswers: list[dict[str, ClarificationAnswer]] = Field(default_factory=list)
    items: list[ClarificationState] = Field(default_factory=list)
    pendingClarifications: list[BasketQuestion] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    complete: bool = False


class BasketPrepareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: BasketState
    existingItems: list[CartLine] = Field(default_factory=list, max_length=MAX_CART_LINES)
    skip: list[int] = Field(default_factory=list)   # proposed lines the shopper removed


class ProposedLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    source: Literal["request", "meal"]
    request: str                     # what was asked for: "greek yogurt", "tuna (tuna salad)"
    product: CatalogProduct | None
    quantity: int                    # 0 when nothing fits
    lineCents: int
    note: str
    skipped: bool = False


class BasketResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["cart_ready", "needs_confirmation", "no_matches"]
    message: str
    lines: list[ProposedLine]
    notCarried: list[str]
    items: list[CartLine]
    quote: dict | None
    assumptions: list[str]
    unverified: list[str]


# --- Clarification across items ----------------------------------------------

def _item_label(item: ShoppingIntent, index: int) -> str:
    return item.product.value or f"item {index + 1}"


def _with_basket_budget(item: ShoppingIntent, request: BasketIntent) -> ShoppingIntent:
    """"As many as fit" with no limit of its own counts against the basket budget,
    so it does not ask for a budget the shopper already gave."""
    budget = request.totalBudget
    if item.quantity.mode == "fill_budget" and item.maxPrice.value is None and budget.value is not None:
        return item.model_copy(update={"maxPrice": budget.model_copy(update={"per": "total"})})
    return item


def build_basket_state(raw: str, request: BasketIntent,
                       item_answers: list[dict[str, ClarificationAnswer]] | None = None) -> BasketState:
    """Recompute every item's clarification state from the immutable request."""
    if len(request.items) > AGENTIC_MAX_BASKET_ITEMS:
        raise ResolutionError(f"Ask for at most {AGENTIC_MAX_BASKET_ITEMS} items at a time")
    answers = list(item_answers or [])
    if len(answers) > len(request.items):
        raise ResolutionError("An answer refers to an item that was not asked for")
    answers += [{} for _ in range(len(request.items) - len(answers))]

    states = [build_clarification_state(raw, _with_basket_budget(item, request), answers[i])
              for i, item in enumerate(request.items)]
    pending, by_text = [], {}
    for i, (item, state) in enumerate(zip(request.items, states)):
        label = _item_label(item, i)
        pending += [BasketQuestion(**q.model_dump(), item=i, itemLabel=label) for q in state.pendingClarifications]
        for text in state.assumptions:
            if text == NO_LIMIT_ASSUMPTION and request.totalBudget.value is not None:
                continue   # the basket budget covers this item
            by_text.setdefault(text, []).append(label)
    # Said once when it holds for every item, otherwise per item.
    assumptions = [text if len(labels) == len(request.items) else f"{', '.join(labels)}: {text}"
                   for text, labels in by_text.items()]
    return BasketState(
        rawTranscript=raw,
        extractedRequest=request,
        itemAnswers=[state.clarificationAnswers for state in states],
        items=states,
        pendingClarifications=pending,
        assumptions=assumptions,
        complete=not pending,
    )


def apply_basket_answer(state: BasketState, answer: BasketAnswer) -> BasketState:
    """Apply one answer to one item; every other item is untouched."""
    current = build_basket_state(state.rawTranscript, state.extractedRequest, state.itemAnswers)
    if answer.item >= len(current.items):
        raise ResolutionError(f"No item {answer.item + 1} in this request")
    updated = apply_clarification_answer(
        current.items[answer.item],
        ClarificationAnswer(field=answer.field, action=answer.action, value=answer.value),
    )
    answers = list(current.itemAnswers)
    answers[answer.item] = updated.clarificationAnswers
    return build_basket_state(current.rawTranscript, current.extractedRequest, answers)


# --- Choosing products and pricing the proposal --------------------------------

def _cents(dollars: float) -> int:
    # A maximum must never be rounded upward beyond what the user said.
    return int(Decimal(str(dollars)) * 100)


def prepare_basket(body: BasketPrepareRequest) -> BasketResult:
    state = build_basket_state(body.state.rawTranscript, body.state.extractedRequest, body.state.itemAnswers)
    if state.pendingClarifications:
        raise CommerceError("Answer the open question before shopping")
    request = state.extractedRequest
    if request.intent == "not_shopping":
        raise CommerceError("That did not sound like a shopping request. Say what you would like to buy, "
                            "or a dish you want to make.")
    if not request.items and not request.meals:
        raise CommerceError("Tell Timbre the items or a dish, for example "
                            "\"what I need for tuna salad\" or \"milk and eggs\".")

    catalog = list_catalog()
    by_id = {p["id"]: CatalogProduct.model_validate(p) for p in catalog}
    skip = set(body.skip)
    in_cart = {line.product_id: line.quantity for line in body.existingItems}
    if len(in_cart) != len(body.existingItems):
        raise CommerceError("Combine duplicate existing cart lines before agentic shopping")
    added: dict[str, int] = {}
    budget = request.totalBudget
    limit_cents = _cents(budget.value) if budget.value is not None else None
    spent = 0
    lines: dict[int, ProposedLine] = {}
    unverified: list[str] = []
    not_carried: list[str] = []

    def room(product_id: str) -> int:
        return MAX_QUANTITY - in_cart.get(product_id, 0) - added.get(product_id, 0)

    def take(index: int, source: str, asked: str, product: CatalogProduct, quantity: int, note: str) -> None:
        nonlocal spent
        skipped = index in skip
        quantity = max(min(quantity, room(product.id)), 0)
        if quantity < 1:
            note = f"Your cart already has the most allowed of {_label(product)}."
        elif not skipped:
            added[product.id] = added.get(product.id, 0) + quantity
            spent += product.price_cents * quantity
        lines[index] = ProposedLine(index=index, source=source, request=asked, product=product,
                                    quantity=quantity, lineCents=product.price_cents * quantity,
                                    note=note, skipped=skipped)

    def missing(index: int, asked: str, note: str) -> None:
        lines[index] = ProposedLine(index=index, source="request", request=asked, product=None,
                                    quantity=0, lineCents=0, note=note, skipped=index in skip)

    finals: list[tuple[int, str, FinalShoppingIntent | None, str]] = []
    for i, item_state in enumerate(state.items):
        asked = _item_label(request.items[i], i)
        try:
            finals.append((i, asked, finalize_shopping_intent(item_state).finalIntent, ""))
        except FinalIntentError as exc:
            finals.append((i, asked, None, str(exc)))

    # 1. Named items with a fixed quantity, in spoken order.
    for i, asked, final, error in finals:
        if final is None:
            missing(i, asked, error)
            continue
        if final.quantityMode == "fill_budget":
            continue
        matches, reason = search_products(final, catalog, {**in_cart, **added})
        if not matches:
            missing(i, asked, reason or "Nothing in the store matches.")
            continue
        # An "item" whose words the shopper never said was chosen by the model
        # (a dish's ingredients filed as items): it is reviewed like a meal line.
        said = request.items[i].product.sourceText
        source = "request" if said and words(said) <= words(state.rawTranscript) else "meal"
        take(i, source, asked, matches[0].product, matches[0].quantity,
             "" if source == "request" else "Timbre chose this.")
        unverified += _unverified_preferences(final, matches[0].product)

    # 2. Meals: the model's picks, but only products this store actually has.
    index = len(request.items)
    for meal in request.meals:
        ingredient_names = {i.need.strip().lower() for i in meal.ingredients}
        unverified += [f"{need} ({meal.goal})" for need in meal.cannotVerify
                       if need.strip().lower() not in ingredient_names]
        for ingredient in meal.ingredients:
            asked = f"{ingredient.need} ({meal.goal})"
            product = by_id.get(ingredient.productId) if ingredient.productId else None
            if product is None:
                not_carried.append(asked)
                continue
            take(index, "meal", asked, product, min(ingredient.quantity, MAX_QUANTITY), ingredient.reason)
            index += 1

    # 3. "As many as fit" items share what is left of the basket budget.
    for i, asked, final, _ in finals:
        if final is None or final.quantityMode != "fill_budget":
            continue
        own = _cents(final.maxPrice)   # finalization guarantees a limit for "as many as fit"
        cap = own if limit_cents is None else min(own, limit_cents - spent)
        if cap <= 0:
            missing(i, asked, f"Nothing is left of your {_dollars(limit_cents)} budget for {asked}.")
            continue
        matches, reason = search_products(final.model_copy(update={"maxPrice": cap / 100}),
                                          catalog, {**in_cart, **added})
        if not matches:
            missing(i, asked, reason or "Nothing in the store matches.")
            continue
        take(i, "request", asked, matches[0].product, matches[0].quantity, f"As many as fit in {_dollars(cap)}.")

    ordered = [lines[i] for i in sorted(lines)]
    chosen = [line for line in ordered if line.product and line.quantity and not line.skipped]
    if not chosen:
        return BasketResult(status="no_matches", message=_nothing_message(ordered, not_carried),
                            lines=ordered, notCarried=not_carried, items=body.existingItems, quote=None,
                            assumptions=state.assumptions, unverified=unverified)

    quantities = dict(in_cart)
    for product_id, quantity in added.items():
        quantities[product_id] = quantities.get(product_id, 0) + quantity
    if len(quantities) > MAX_CART_LINES:
        raise CommerceError("The cart has too many different products")
    items = [CartLine(product_id=pid, quantity=qty) for pid, qty in quantities.items()]
    try:
        quote = price_cart([(line.product_id, line.quantity) for line in items])
    except CartError as exc:
        raise CommerceError(str(exc)) from exc

    over = limit_cents is not None and spent > limit_cents
    agent_chose = any(line.source == "meal" for line in chosen)
    status = "needs_confirmation" if (agent_chose or over) else "cart_ready"
    message = _summary(chosen, status)
    if over:
        message += (f" These come to {_dollars(spent)}, over your {_dollars(limit_cents)} limit. "
                    "Remove something before adding.")
    return BasketResult(status=status, message=message, lines=ordered, notCarried=not_carried,
                        items=items, quote=quote, assumptions=state.assumptions, unverified=unverified)


def _summary(chosen: list[ProposedLine], status: str) -> str:
    parts = [f"{line.quantity} × {_label(line.product)}" for line in chosen]
    listed = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + f" and {parts[-1]}"
    if status == "needs_confirmation":
        return f"Timbre picked {listed}. Check the list, then add it to your cart."
    return f"Added {listed} to your cart."


def _nothing_message(lines: list[ProposedLine], not_carried: list[str]) -> str:
    notes = [line.note for line in lines if line.note and not line.skipped]
    if notes:
        return " ".join(dict.fromkeys(notes))
    if not_carried:
        return "This store does not sell anything on that list. Your cart was not changed."
    return "Nothing was added. Your cart was not changed."
