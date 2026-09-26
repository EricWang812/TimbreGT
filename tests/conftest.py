"""Point both services at throwaway databases before any config module loads.

pytest imports conftest.py before collecting test modules, and load_dotenv
never overrides a variable that is already set, so these win over .env.
"""
import os
import shutil
import tempfile

_TMP_DIR = tempfile.mkdtemp(prefix="timbre-test-")
os.environ["MERCHANT_DB"] = os.path.join(_TMP_DIR, "merchant.db")
os.environ["ISSUER_DB"] = os.path.join(_TMP_DIR, "issuer.db")
# Tests never call real Stripe, even when .env holds a key: an empty key
# selects the in-process FakeProvider (issuer/payments/__init__.py).
os.environ["STRIPE_SECRET_KEY"] = ""


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TMP_DIR)


import pytest

@pytest.fixture(scope="session", autouse=True)
def merchant_schema():
    # Pure shopping services now read persisted market metadata too.
    from api.db import init_db
    init_db()
