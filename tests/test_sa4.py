import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.session import SessionConfig
from agents.sa2_validator.validator import run as run_sa2
from agents.sa3_alerts.alert_calculator import run as run_sa3
from agents.sa4_analyst.analyst import run as run_sa4
from tools.json_writer import load_json

session = SessionConfig(user_id="test_user", session_id="8ea9a0af")

raw_json_path = Path(__file__).parent.parent / "data" / "intermediate" / "8ea9a0af" / "raw.json"
raw_data = load_json(raw_json_path)

print("--- Ejecutando SA2 ---")
validated_data = run_sa2(session, raw_data)

print("\n--- Ejecutando SA3 ---")
alerts_data = run_sa3(session, validated_data)

print("\n--- Ejecutando SA4 ---")
result = run_sa4(session, validated_data, alerts_data)

print("\n📋 Executive Summary:")
print(result.get("executive_summary"))

print("\n💡 Recomendaciones:")
for rec in result.get("recommendations", []):
    print(f"  [{rec.get('priority').upper()}] {rec.get('area')}: {rec.get('recommendation')}")