"""Provider selection. The only way code outside issuer/payments/ obtains a
PaymentProvider (docs/ALGORITHM.md §9.2)."""
import logging

from issuer.config import (CYBERSOURCE_HOST, CYBERSOURCE_KEY_ID, CYBERSOURCE_MERCHANT_ID, CYBERSOURCE_SECRET_KEY,
                           CYBERSOURCE_TIMEOUT_S, PAYMENT_PROVIDER, STRIPE_SECRET_KEY)
from issuer.payments.base import PaymentProvider

log = logging.getLogger(__name__)

# How each provider's stored card references begin, so re-seeding can replace
# a card tokenized by a different provider (in place: enrollments and passkeys stay).
_TOKEN_PREFIXES = {"visa": "cybs:", "stripe": "cus_", "fake": "fake_tok_"}


def active_provider_name() -> str:
    if PAYMENT_PROVIDER == "visa":
        return "visa"
    return "stripe" if STRIPE_SECRET_KEY else "fake"


def token_is_current(token_value: str) -> bool:
    return token_value.startswith(_TOKEN_PREFIXES[active_provider_name()])


def get_provider(*, transport=None) -> PaymentProvider:
    """`transport` is an httpx transport for tests (a mocked CyberSource); the
    app never passes one."""
    if PAYMENT_PROVIDER == "visa":
        # CyberSource, Visa's gateway, in its sandbox (ADR 13). Missing keys
        # raise at startup rather than falling back: the demo must not
        # silently switch rails.
        from issuer.payments.visa_provider import VisaProvider
        return VisaProvider(CYBERSOURCE_MERCHANT_ID, CYBERSOURCE_KEY_ID, CYBERSOURCE_SECRET_KEY,
                            host=CYBERSOURCE_HOST, timeout_s=CYBERSOURCE_TIMEOUT_S, transport=transport)
    if STRIPE_SECRET_KEY:
        from issuer.payments.stripe_provider import StripeProvider
        return StripeProvider(STRIPE_SECRET_KEY)
    # STUB: with no key (the test suite, or an offline demo with no network),
    # fall back to the in-process fake. Loud on every start so it is never
    # mistaken for real payments.
    from issuer.payments.fake_provider import FakeProvider
    log.warning("STUB: STRIPE_SECRET_KEY is empty, using FakeProvider. No money moves.")
    return FakeProvider()
