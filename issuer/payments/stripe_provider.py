"""Stripe test-mode PaymentProvider (docs/ALGORITHM.md §9.2, §9.3).

Tokens are created from Stripe's named test PaymentMethods (`pm_card_visa`,
`pm_card_mastercard`), attached to a Stripe Customer, and stored as the
opaque reference "cus_...:pm_...". No card number ever reaches this code
(non-negotiable §2.2).

authorize() places a manual-capture PaymentIntent; capture() completes it,
and cancels the authorization if capture fails, so no hold is left open.
Network or authentication errors are raised, not converted to declines:
the caller releases the payment claim and the failure is visible.

Refuses to run with a live key: Timbre only ever uses Stripe test mode.
"""
import logging

import stripe

from issuer.payments.base import AuthResult, CaptureResult, PaymentProvider, TokenRef

log = logging.getLogger(__name__)

CURRENCY = "usd"


class StripeProvider(PaymentProvider):
    def __init__(self, secret_key: str):
        if not secret_key.startswith("sk_test_"):
            raise RuntimeError("STRIPE_SECRET_KEY must be a test-mode key (sk_test_...); Timbre never uses live keys")
        self._key = secret_key  # passed per call: no process-global stripe.api_key

    def create_token(self, user_id: str, test_card: str) -> TokenRef:
        customer = stripe.Customer.create(
            api_key=self._key, description=f"Timbre demo cardholder {user_id}", metadata={"timbre_user": user_id})
        method = stripe.PaymentMethod.attach(test_card, customer=customer.id, api_key=self._key)
        return TokenRef(value=f"{customer.id}:{method.id}", last_four=method.card.last4,
                        nickname=method.card.brand.title())

    def authorize(self, token: TokenRef, amount_cents: int,
                  merchant_id: str, instruction_id: str) -> AuthResult:
        customer_id, method_id = token.value.split(":", 1)
        try:
            intent = stripe.PaymentIntent.create(
                api_key=self._key, amount=amount_cents, currency=CURRENCY,
                customer=customer_id, payment_method=method_id,
                confirm=True, off_session=True, capture_method="manual",
                description=f"Timbre demo purchase at {merchant_id}",
                metadata={"instruction_id": instruction_id, "merchant_id": merchant_id},
            )
        except stripe.CardError as exc:
            return AuthResult(ok=False, auth_id=None, decline_reason=exc.code or "card_declined")
        if intent.status != "requires_capture":
            return AuthResult(ok=False, auth_id=None, decline_reason=f"unexpected status {intent.status}")
        return AuthResult(ok=True, auth_id=intent.id, decline_reason=None)

    def capture(self, auth_id: str) -> CaptureResult:
        try:
            intent = stripe.PaymentIntent.capture(auth_id, api_key=self._key)
        except stripe.StripeError as exc:
            log.error("capture failed for %s: %s; cancelling the authorization", auth_id, exc)
            self._cancel(auth_id)
            return CaptureResult(ok=False, transaction_id=None)
        if intent.status != "succeeded":
            log.error("capture of %s ended in status %s; cancelling the authorization", auth_id, intent.status)
            self._cancel(auth_id)
            return CaptureResult(ok=False, transaction_id=None)
        return CaptureResult(ok=True, transaction_id=intent.id)

    def report_outcome(self, instruction_id: str, outcome: dict) -> None:
        # Stripe needs no outcome report; kept for the Visa Intelligent
        # Commerce mapping (commerce signals, docs/DECISIONS.md ADR 1).
        log.info("outcome %s %s", instruction_id, outcome)

    def _cancel(self, auth_id: str) -> None:
        try:
            stripe.PaymentIntent.cancel(auth_id, api_key=self._key)
        except stripe.StripeError as exc:
            log.error("could not cancel authorization %s; it will expire on its own: %s", auth_id, exc)
