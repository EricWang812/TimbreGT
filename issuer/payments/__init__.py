"""Provider selection. The only way code outside issuer/payments/ obtains a
PaymentProvider (docs/ALGORITHM.md §9.2)."""
import logging

from issuer.config import PAYMENT_PROVIDER, STRIPE_SECRET_KEY
from issuer.payments.base import PaymentProvider

log = logging.getLogger(__name__)


def get_provider() -> PaymentProvider:
    if PAYMENT_PROVIDER == "visa":
        raise NotImplementedError("PAYMENT_PROVIDER=visa: visa_provider.py is not built (docs/ALGORITHM.md §9.2)")
    if STRIPE_SECRET_KEY:
        from issuer.payments.stripe_provider import StripeProvider
        return StripeProvider(STRIPE_SECRET_KEY)
    # STUB: with no key (the test suite, or an offline demo with no network),
    # fall back to the in-process fake. Loud on every start so it is never
    # mistaken for real payments.
    from issuer.payments.fake_provider import FakeProvider
    log.warning("STUB: STRIPE_SECRET_KEY is empty, using FakeProvider. No money moves.")
    return FakeProvider()
