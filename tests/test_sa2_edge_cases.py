import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import copy
from models.session import SessionConfig
from agents.sa2_validator.validator import run, ValidationError
from tools.json_writer import load_json

# Cargamos el raw.json bueno como base para modificarlo
BASE_JSON_PATH = Path(__file__).parent / "fixtures" / "raw.json"
base_data = load_json(BASE_JSON_PATH)


def run_test(name: str, data: dict, session_id: str) -> None:
    """Ejecuta un test y muestra el resultado."""
    print(f"\n{'='*60}")
    print(f"🧪 TEST: {name}")
    print('='*60)
    session = SessionConfig(user_id="test_user", session_id=session_id)
    try:
        result = run(session, data)
        status = result["validation"]["status"]
        warnings = result["validation"]["warnings"]
        print(f"✅ Pasó validación — Status: {status}")
        if warnings:
            print(f"⚠️  Warnings ({len(warnings)}):")
            for w in warnings:
                print(f"   - {w}")
    except ValidationError as e:
        print(f"❌ Pipeline detenido:")
        print(str(e))


# ── TEST 1: KPIs todos a cero ─────────────────────────────────────
data_zeros = copy.deepcopy(base_data)
for kpi_name in data_zeros["kpis"]:
    if isinstance(data_zeros["kpis"][kpi_name], dict):
        data_zeros["kpis"][kpi_name]["value"] = 0
run_test("KPIs todos a cero", data_zeros, "test_zeros")

# ── TEST 2: Strings en lugar de números ──────────────────────────
data_strings = copy.deepcopy(base_data)
data_strings["kpis"]["saz_score"]["value"] = "alto"
data_strings["kpis"]["rating"]["value"] = "muy bueno"
data_strings["kpis"]["nps"]["value"] = "positivo"
run_test("Strings en lugar de números en KPIs", data_strings, "test_strings")

# ── TEST 3: Campo obligatorio ausente — campaign_metadata ─────────
data_no_metadata = copy.deepcopy(base_data)
del data_no_metadata["campaign_metadata"]
run_test("Campo obligatorio ausente: campaign_metadata", data_no_metadata, "test_no_metadata")

# ── TEST 4: Campo obligatorio ausente — kpis ──────────────────────
data_no_kpis = copy.deepcopy(base_data)
del data_no_kpis["kpis"]
run_test("Campo obligatorio ausente: kpis", data_no_kpis, "test_no_kpis")

# ── TEST 5: KPI fuera de rango ────────────────────────────────────
data_out_of_range = copy.deepcopy(base_data)
data_out_of_range["kpis"]["rating"]["value"] = 7.5
data_out_of_range["kpis"]["nps"]["value"] = 150
run_test("KPIs fuera de rango (rating=7.5, nps=150)", data_out_of_range, "test_range")

# ── TEST 6: Segmentos inconsistentes ─────────────────────────────
data_inconsistent = copy.deepcopy(base_data)
data_inconsistent["pre_evaluation"]["segments"] = ["Tous", "Homme", "Femme"]
data_inconsistent["post_evaluation"]["segments"] = ["Tous", "Homme", "18-24"]
run_test("Segmentos inconsistentes entre pre y post", data_inconsistent, "test_segments")

# ── TEST 7: JSON vacío ────────────────────────────────────────────
run_test("JSON completamente vacío", {}, "test_empty")

# ── TEST 8: qualitative vacío ─────────────────────────────────────
data_no_qualitative = copy.deepcopy(base_data)
data_no_qualitative["qualitative"]["strengths"] = []
data_no_qualitative["qualitative"]["improvements"] = []
run_test("Qualitative vacío (strengths e improvements)", data_no_qualitative, "test_qualitative")

# ── TEST 9: precio negativo ───────────────────────────────────────
data_negative_price = copy.deepcopy(base_data)
data_negative_price["campaign_metadata"]["campaign_price"] = -5.99
run_test("Precio negativo", data_negative_price, "test_price")

# ── TEST 10: muestra muy pequeña ─────────────────────────────────
data_small_sample = copy.deepcopy(base_data)
data_small_sample["campaign_metadata"]["testers_count"] = 10
run_test("Muestra muy pequeña (10 testeurs)", data_small_sample, "test_sample")

print(f"\n{'='*60}")
print("✅ Todos los tests ejecutados")
print('='*60)