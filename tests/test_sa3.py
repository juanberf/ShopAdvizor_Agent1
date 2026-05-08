import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.session import SessionConfig
from agents.sa2_validator.validator import run as run_sa2
from agents.sa3_alerts.alert_calculator import run as run_sa3
from tools.json_writer import load_json

session = SessionConfig(user_id="test_user", session_id="8ea9a0af")

raw_json_path = Path(__file__).parent.parent / "data" / "intermediate" / "8ea9a0af" / "raw.json"

raw_data = load_json(raw_json_path)

print("--- Ejecutando SA2 ---")
validated_data = run_sa2(session, raw_data)

print("\n--- Ejecutando SA3 ---")
result = run_sa3(session, validated_data)

print("\n📊 Resumen de alertas:")
print(f"  🔴 Críticas: {result['summary']['critical']}")
print(f"  🟡 Atención: {result['summary']['warning']}")
print(f"  🟢 Positivos: {result['summary']['positive']}")
print("\n📋 Detalle:")
for alert in result["alerts"]:
    emoji = {"critical": "🔴", "warning": "🟡", "positive": "🟢"}[alert["level"]]
    print(f"  {emoji} [{alert['kpi']}] {alert['message']}")