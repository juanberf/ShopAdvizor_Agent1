import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.session import SessionConfig
from agents.sa2_validator.validator import run as run_sa2
from agents.sa3_alerts.alert_calculator import run as run_sa3
from agents.sa4_analyst.analyst import run as run_sa4
from agents.sa5_redactor.redactor import run as run_sa5
from tools.json_writer import load_json

session = SessionConfig(user_id="test_user", session_id="a514e6c0")

raw_json_path = Path(__file__).parent.parent / "data" / "intermediate" / "a514e6c0" / "raw.json"
raw_data = load_json(raw_json_path)

print("--- Ejecutando SA2 ---")
validated_data = run_sa2(session, raw_data)

print("\n--- Ejecutando SA3 ---")
alerts_data = run_sa3(session, validated_data)

print("\n--- Ejecutando SA4 ---")
analysis_data = run_sa4(session, validated_data, alerts_data)

print("\n--- Ejecutando SA5 ---")
pdf_path = run_sa5(session, analysis_data, validated_data, alerts_data)

print(f"\n✅ One-Pager generado en: {pdf_path}")