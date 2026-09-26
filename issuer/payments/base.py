"""PaymentProvider interface (docs/ALGORITHM.md §9.3). DO NOT BYPASS.

Concrete providers live beside this file and are never imported from outside
issuer/payments/. Get one through issuer.payments.get_provider().
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class TokenRef:      # opaque handle to a stored payment credential
    value: str
    last_four: str
    nickname: str    # "blue Chase card"


@dataclass(frozen=True)
class AuthResult:
    ok: bool
    auth_id: str | None
    decline_reason: str | None


@dataclass(frozen=True)
class CaptureResult:
    ok: bool
    transaction_id: str | None


class PaymentProvider(ABC):
    @abstractmethod
    def create_token(self, user_id: str, test_card: str) -> TokenRef:
        """Tokenize a sandbox test card. `test_card` is used once and never
        persisted (non-negotiable §2.2)."""

    @abstractmethod
    def authorize(self, token: TokenRef, amount_cents: int,
                  merchant_id: str, instruction_id: str) -> AuthResult: ...

    @abstractmethod
    def capture(self, auth_id: str) -> CaptureResult: ...

    @abstractmethod
    def report_outcome(self, instruction_id: str, outcome: dict) -> None: ...
