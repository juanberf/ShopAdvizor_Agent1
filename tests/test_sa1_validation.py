import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.session import SessionConfig
from agents.sa1_extractor.extractor import run, SourceMismatchError

FIXTURES_DIR = Path(__file__).parent / "fixtures"
session = SessionConfig(user_id="test_user")

# ── TEST 1: Archivos correctos (deben coincidir) ──────────────
print("\n🧪 TEST 1: Archivos de la misma campaña")
try:
    result = run(
        session,
        FIXTURES_DIR / "202603_Result_Detail_79d75deac0.xlsx",
        FIXTURES_DIR / "Résultats_de_la_campagne_Shopadvizor.pdf",
    )
    print("✅ Correcto — pipeline continuó normalmente")
except SourceMismatchError as e:
    print(f"❌ Falso positivo — {e}")

# ── TEST 2: Archivos distintos (deben fallar) ─────────────────
print("\n🧪 TEST 2: Archivos de campañas distintas")
try:
    result = run(
        session,
        FIXTURES_DIR / "202603_Result_Detail_2043b5701e.xlsx",
        FIXTURES_DIR / "One-Pager_Shopadvizor_-_Brocolis.pdf",
    )
    print("❌ Debería haber fallado pero no lo hizo")
except SourceMismatchError as e:
    print(f"✅ Correcto — detectó archivos distintos:")
    print(f"   {e}")