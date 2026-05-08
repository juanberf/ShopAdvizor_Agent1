import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.session import SessionConfig
from agents.sa2_validator.validator import run
from tools.json_writer import load_json

session = SessionConfig(user_id="test_user", session_id="2a5ab6aa")

raw_json_path = Path(__file__).parent.parent / "data" / "intermediate" / "8ea9a0af" / "raw.json"

print(f"Existe: {raw_json_path.exists()}")

raw_data = load_json(raw_json_path)
result = run(session, raw_data)

print("✅ Status:", result["validation"]["status"])
print("✅ Warnings:", result["validation"]["warnings"])
print("✅ Errors:", result["validation"]["errors"])