"""Shopping tests use text and silence, never imitated disabled speech."""
import io

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from api import llm, shopping
from api.main import app

CATALOG = [
    {"id": "milk", "name": "Whole Milk", "brand": "Dairy"},
    {"id": "oat", "name": "Oat Milk", "brand": "Other"},
    {"id": "apple", "name": "Apples", "brand": "Orchard"},
]


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(llm, "LLM_API_KEY", "")
    monkeypatch.setattr(shopping, "list_catalog", lambda: CATALOG)


def test_keyword_repair_and_explicit_confirmation():
    assert llm.rerank(["whole milk please"], CATALOG)["product_id"] == "milk"
    assert llm.rerank(["milk"], CATALOG)["needs_repair"]
    assert llm.rerank(["unrelated"], CATALOG)["product_id"] is None
    assert llm.rerank(["apples"], CATALOG)["needs_confirmation"]


@pytest.mark.parametrize("response", [
    '{"product_id":"invented","confidence":1}',
    '{"product_id":"milk","confidence":2}',
    '{"product_id":"milk","confidence":NaN}',
    '{"product_id":"milk","confidence":true}',
    '{"product_id":"milk","confidence":0.9,"charge":true}',
    'not JSON',
])
def test_invalid_llm_output_falls_back(monkeypatch, response):
    monkeypatch.setattr(llm, "LLM_API_KEY", "fake-test-key")
    monkeypatch.setattr(llm, "_request", lambda *_: response)
    result = llm.rerank(["apples"], CATALOG)
    assert result["product_id"] == "apple" and result["method"] == "keyword"


def test_llm_valid_output_and_network_failure(monkeypatch):
    monkeypatch.setattr(llm, "LLM_API_KEY", "fake-test-key")
    monkeypatch.setattr(llm, "_request", lambda *_: '{"product_id":"oat","confidence":0.8}')
    assert llm.rerank(["out milk"], CATALOG)["method"] == "llm"
    def unavailable(*_):
        raise TimeoutError("offline")
    monkeypatch.setattr(llm, "_request", unavailable)
    assert llm.rerank(["apples"], CATALOG)["method"] == "keyword"


def wav(samples, rate=16000):
    result = io.BytesIO()
    sf.write(result, samples, rate, format="WAV")
    return result.getvalue()


def test_shopping_routes_and_audio_validation(monkeypatch):
    client = TestClient(app)
    assert client.post("/shopping/text", json={"text": "apples"}).json()["product_id"] == "apple"
    assert client.post("/shopping/text", json={"text": "apples", "price": 1}).status_code == 422
    assert client.post("/shopping/voice", files={"audio": ("take.wav", b"invalid")}).status_code == 400
    assert client.post("/shopping/voice", files={"audio": ("take.wav", wav(np.zeros(100), 8000))}).status_code == 400
    response = client.post("/shopping/voice", files={"audio": ("take.wav", wav(np.zeros(16000)))})
    assert response.json()["product_id"] is None
    monkeypatch.setattr(shopping.asr, "hypotheses", lambda _: ["apples", "apple"])
    response = client.post("/shopping/voice", files={"audio": ("take.wav", wav(np.ones(16000) * .1))})
    assert response.json()["product_id"] == "apple"
    def unavailable(_):
        raise shopping.asr.ASRUnavailable("Type an item instead")
    monkeypatch.setattr(shopping.asr, "hypotheses", unavailable)
    assert client.post("/shopping/voice", files={"audio": ("take.wav", wav(np.ones(16000) * .1))}).status_code == 503


def test_short_clip_is_padded_to_one_encoder_window(monkeypatch):
    # The real encoder rejects anything but 3000 mel frames; a fake model
    # records what hypotheses() hands it, so no model download is needed.
    import faster_whisper.tokenizer
    from faster_whisper.feature_extractor import FeatureExtractor
    from types import SimpleNamespace

    seen = {}

    class FakeTokenizer:
        def __init__(self, *_, **__):
            self.sot_sequence, self.no_timestamps = [1], 2

        def decode(self, tokens):
            return "apples"

    def encode(features):
        seen["shape"] = features.shape
        return features

    result = SimpleNamespace(no_speech_prob=0.0, sequences_ids=[[5], [6]])
    model = SimpleNamespace(
        hf_tokenizer=None, feature_extractor=FeatureExtractor(), encode=encode,
        model=SimpleNamespace(is_multilingual=False, generate=lambda *_, **__: [result]),
    )
    monkeypatch.setattr(faster_whisper.tokenizer, "Tokenizer", FakeTokenizer)
    monkeypatch.setattr(shopping.asr, "_model", lambda: model)
    assert shopping.asr.hypotheses(np.ones(16000 * 2, dtype=np.float32) * .1) == ["apples"]
    assert seen["shape"] == (80, 3000)


def test_nbest_keeps_distinct_wordings_only(monkeypatch):
    import faster_whisper.tokenizer
    from faster_whisper.feature_extractor import FeatureExtractor
    from types import SimpleNamespace

    words = {5: "Doug.", 6: "doug", 7: "Dug", 8: "Dug!", 9: "Duck", 10: "Dog"}

    class FakeTokenizer:
        def __init__(self, *_, **__):
            self.sot_sequence, self.no_timestamps = [1], 2

        def decode(self, tokens):
            return words[tokens[0]]

    result = SimpleNamespace(no_speech_prob=0.0, sequences_ids=[[k] for k in words])
    model = SimpleNamespace(
        hf_tokenizer=None, feature_extractor=FeatureExtractor(), encode=lambda f: f,
        model=SimpleNamespace(is_multilingual=False, generate=lambda *_, **__: [result]),
    )
    monkeypatch.setattr(faster_whisper.tokenizer, "Tokenizer", FakeTokenizer)
    monkeypatch.setattr(shopping.asr, "_model", lambda: model)
    assert shopping.asr.hypotheses(np.ones(16000, dtype=np.float32) * .1) == ["Doug.", "Dug", "Duck"]


STORE = [
    {"id": "bread", "name": "21 Whole Grains and Seeds Bread", "brand": "Dave's Killer Bread"},
    {"id": "chobani", "name": "Greek Yogurt, Nonfat Plain", "brand": "Chobani"},
    {"id": "fage", "name": "Total 0% Greek Yogurt", "brand": "Fage"},
    {"id": "bananas", "name": "Organic Bananas", "brand": "Dole"},
    {"id": "coffee", "name": "Espresso Ground Coffee", "brand": "Café Bustelo"},
    {"id": "cabot", "name": "Seriously Sharp Cheddar", "brand": "Cabot Creamery"},
    {"id": "puffs", "name": "Aged White Cheddar Puffs", "brand": "Pirate's Booty"},
]


@pytest.mark.parametrize("said, expected, confident", [
    ("whole milk", None, False),            # one shared word ("whole") is not a match
    ("chobani yogurt", "chobani", True),    # brand words count
    ("yogurt please", None, False),         # two yogurts tie: resolved below, never guessed
    ("a banana", "bananas", True),          # plural and filler words
    ("cafe bustelo", "coffee", True),       # accents folded
])
def test_keyword_fallback_needs_most_of_what_was_said(said, expected, confident):
    result = llm.keyword_match([said], STORE)
    if said == "yogurt please":
        assert result.product_id in {"chobani", "fage"} and result.confidence < 0.7
        return
    assert result.product_id == expected
    assert (result.confidence >= 0.7) == confident


def test_a_word_shared_by_several_products_is_never_confident():
    result = llm.keyword_match(["cheddar"], STORE)
    assert result.product_id in {"cabot", "puffs"} and result.confidence < 0.7


def test_store_info_serves_the_free_delivery_threshold():
    from api.catalog import market_records
    from api.config import FREE_SHIPPING_MIN_CENTS
    assert TestClient(app).get("/store").json() == {
        "free_shipping_min_cents": FREE_SHIPPING_MIN_CENTS, "markets": market_records()}


def test_every_seeded_product_has_a_photo_and_a_real_shop():
    # The boardwalk shops share one catalog; a product in an unknown shop, or
    # one whose photo is missing, would show broken on the page.
    import json
    from scripts.seed_demo import MARKET_IDS
    from ml.constants import REPO_ROOT
    products = json.loads((REPO_ROOT / "scripts" / "seed_catalog.json").read_text("utf-8"))
    photos = REPO_ROOT / "web" / "public" / "products"
    assert [p["id"] for p in products if not (photos / f"{p['barcode']}.jpg").exists()] == []
    assert {p.get("market", "grocer") for p in products} == MARKET_IDS   # every shop has stock


def test_naming_a_shop_limits_the_search_to_it(monkeypatch):
    from api import catalog
    monkeypatch.setattr(catalog, "market_records", lambda: [{"id": "persisted-id", "name": "Actual Shop"}])
    assert catalog.merchant_scope("Actual Shop") == (True, "persisted-id")
    assert catalog.merchant_scope("Seaside Tech") == (False, None)
    assert catalog.merchant_scope("Amazon") == (False, None)
