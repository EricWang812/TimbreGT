"""Static checks for non-negotiables that a code review could miss.

§2.1: nothing under issuer/ imports an ASR model.
§2.2: no card number (PAN) appears anywhere in source, fixtures included.
"""
import re
import subprocess
import sys

from ml.constants import REPO_ROOT

SOURCE_DIRS = ("api", "issuer", "ml", "scripts", "tests", "web/src")
SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".json", ".sql", ".md", ".html", ".css"}
ASR_MODULES = ("faster_whisper", "whisper", "ctranslate2")
ASR_IMPORT = re.compile(rf"^\s*(import|from)\s+({'|'.join(ASR_MODULES)})\b", re.M)
# Card numbers never begin with 0 (ISO/IEC 7812 major industry identifier 0 is
# not a card network), but UPC/EAN product barcodes often do, and some of those
# pass Luhn by chance (the Quaker Oats barcode in scripts/seed_catalog.json).
DIGIT_RUN = re.compile(r"(?<!\d)[1-9]\d{12,18}(?!\d)")
# Packages the bank's code may use: third-party libraries, never storefront code.
ISSUER_ALLOWED_PACKAGES = {"react", "@simplewebauthn/browser"}
# The only issuer components the storefront may mount (the bank's two surfaces).
ISSUER_ENTRY_POINTS = ("issuer/ApprovalWidget.jsx", "issuer/EnrollPage.jsx")
JS_IMPORT = re.compile(r"""^\s*import\s+(?:[^'"]*?\s+from\s+)?["']([^"']+)["']""", re.M)
CONCRETE_PROVIDER_IMPORT = re.compile(
    r"^\s*(from|import)\s.*\b((fake|stripe|visa)_provider|(Fake|Stripe|Visa)Provider)\b", re.M
)


def _source_files(*dirs: str):
    for d in dirs:
        root = REPO_ROOT / d
        if root.exists():
            yield from (p for p in root.rglob("*") if p.suffix in SOURCE_SUFFIXES and p.is_file())


def _luhn_valid(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
    return total % 10 == 0


def test_luhn_helper_detects_known_test_pan():
    # Built at runtime so the literal never appears in source.
    test_pan = "42" * 8
    assert _luhn_valid(test_pan)
    assert DIGIT_RUN.fullmatch(test_pan)                   # still in scope for the scan
    assert DIGIT_RUN.fullmatch("0" + "3" * 12) is None     # leading-zero barcodes are not


def test_issuer_never_imports_asr():
    offenders = [str(p) for p in _source_files("issuer") if ASR_IMPORT.search(p.read_text("utf-8"))]
    assert offenders == []


def test_issuer_never_loads_asr_transitively():
    # A fresh interpreter, because this pytest process may have imported the
    # merchant (which legitimately uses ASR). Catches issuer -> ml -> whisper.
    probe = (
        "import sys, issuer.main; "
        f"print([m for m in {ASR_MODULES!r} if m in sys.modules])"
    )
    out = subprocess.run(
        [sys.executable, "-c", probe], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "[]"


def test_concrete_providers_stay_inside_payments_package():
    # CLAUDE.md §6: concrete providers are reached only through get_provider().
    payments_dir = REPO_ROOT / "issuer" / "payments"
    offenders = [
        str(p.relative_to(REPO_ROOT)) for p in _source_files(*SOURCE_DIRS)
        if p.suffix == ".py" and payments_dir not in p.parents
        and CONCRETE_PROVIDER_IMPORT.search(p.read_text("utf-8"))
    ]
    assert offenders == []


def test_issuer_widget_is_isolated_from_the_storefront():
    # ADR 2, browser half: web/src/issuer/ behaves as if served by the bank.
    # It imports only React and its own folder, and the storefront reaches it
    # only by mounting ApprovalWidget, never by calling the issuer API itself.
    web_src = REPO_ROOT / "web" / "src"
    issuer_dir = web_src / "issuer"
    offenders = []
    for path in _source_files("web/src"):
        if path.suffix not in {".js", ".jsx"}:
            continue
        rel = path.relative_to(REPO_ROOT)
        for spec in JS_IMPORT.findall(path.read_text("utf-8")):
            if issuer_dir in path.parents:
                if not (spec in ISSUER_ALLOWED_PACKAGES or (spec.startswith("./") and "/" not in spec[2:])):
                    offenders.append(f"{rel} imports {spec}")
            elif "issuer/" in spec and not spec.endswith(ISSUER_ENTRY_POINTS):
                offenders.append(f"{rel} imports {spec}")
    assert offenders == []


def test_no_pan_in_source():
    offenders = []
    for path in _source_files(*SOURCE_DIRS):
        for match in DIGIT_RUN.finditer(path.read_text("utf-8")):
            if _luhn_valid(match.group()):
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {match.group()[-4:]}")
    assert offenders == []


def test_issuer_never_loads_candidate_encoders():
    # ADR 8: candidates are evaluation-only; the issuer's encoder is ml/encoder.py alone (§6).
    probe = ("import sys, issuer.main; "
             "print([m for m in ('ml.candidate_encoders', 'onnxruntime', 'ml.variants') if m in sys.modules])")
    out = subprocess.run([sys.executable, "-c", probe], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"
