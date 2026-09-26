"""# STUB: in-process payment provider. Approves everything, moves no money.

Exists only so the approval flow can be built before Stripe test keys are in
.env (Phase 5). get_provider() logs a warning on every startup while this is
in use, and it must not be reachable once STRIPE_SECRET_KEY is set.

Accepts the same named test tokens Stripe does (never a card number), so the
seed data does not change when the real provider replaces this one.
"""
import logging
import uuid

from issuer.payments.base import AuthResult, CaptureResult, PaymentProvider, TokenRef

log = logging.getLogger(__name__)

# Stripe's named test PaymentMethods and the last four digits Stripe reports for them.
TEST_TOKENS = {
    "pm_card_visa": ("4242", "Visa"),
    "pm_card_mastercard": ("4444", "Mastercard"),
}


class FakeProvider(PaymentProvider):
    def create_token(self, user_id: str, test_card: str) -> TokenRef:
        if test_card not in TEST_TOKENS:
            raise ValueError(f"unknown test token {test_card!r}; expected one of {sorted(TEST_TOKENS)}")
        last_four, brand = TEST_TOKENS[test_card]
        return TokenRef(value=f"fake_tok_{uuid.uuid4().hex}", last_four=last_four, nickname=brand)

    def authorize(self, token: TokenRef, amount_cents: int,
                  merchant_id: str, instruction_id: str) -> AuthResult:
        return AuthResult(ok=True, auth_id=f"fake_auth_{uuid.uuid4().hex}", decline_reason=None)

    def capture(self, auth_id: str) -> CaptureResult:
        return CaptureResult(ok=True, transaction_id=f"fake_txn_{uuid.uuid4().hex}")

    def report_outcome(self, instruction_id: str, outcome: dict) -> None:
        log.info("STUB report_outcome %s %s", instruction_id, outcome)
