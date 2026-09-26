"""The merchant's only channel to the issuer: two server-to-server calls.

This is the whole merchant integration (CLAUDE.md §1.1). The merchant sends
an amount and an instruction_id, and gets back {verified, transaction_id}.
It never sends who the shopper is and never receives how they were verified.
"""
import httpx

from api.config import ISSUER_TIMEOUT_S, ISSUER_URL

APPROVAL_KEYS = {"verified", "transaction_id"}

# Module-level so tests can swap in a TestClient bound to the issuer app.
client = httpx.Client(base_url=ISSUER_URL, timeout=ISSUER_TIMEOUT_S)


class IssuerError(RuntimeError):
    """The issuer was unreachable or answered with something unexpected."""


def _post(path: str, body: dict) -> dict:
    try:
        res = client.post(path, json=body)
    except httpx.HTTPError as exc:
        raise IssuerError(f"issuer {path} unreachable: {exc!r}") from exc
    if res.status_code != 200:
        raise IssuerError(f"issuer {path} returned HTTP {res.status_code}: {res.text}")
    return res.json()


def create_session(instruction_id: str, amount_cents: int, merchant_id: str) -> str:
    data = _post("/v1/sessions", {
        "instruction_id": instruction_id,
        "amount_cents": amount_cents,
        "merchant_id": merchant_id,
    })
    return data["session_id"]


def approve(instruction_id: str) -> dict:
    data = _post("/v1/approve", {"instruction_id": instruction_id})
    # Defense in depth for §2.5: refuse anything beyond the two agreed keys.
    if set(data) != APPROVAL_KEYS:
        raise IssuerError(f"issuer /v1/approve returned keys {sorted(data)}, expected {sorted(APPROVAL_KEYS)}")
    return data
