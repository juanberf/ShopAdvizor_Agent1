import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))



from models.session import SessionConfig
from agents.sa1_extractor.extractor import run

# Rutas absolutas basadas en la ubicación del propio test
FIXTURES_DIR = Path(__file__).parent / "fixtures"

session = SessionConfig(user_id="test_user")

excel_path = FIXTURES_DIR / "202603_Result_Detail_2043b5701e.xlsx"
pdf_path = FIXTURES_DIR / "Résultats_de_la_campagne_Shopadvizor.pdf"

# Verificar que existen antes de ejecutar
print(f"Excel existe: {excel_path.exists()}")
print(f"PDF existe: {pdf_path.exists()}")

result = run(session, excel_path, pdf_path)

print("✅ campaign_metadata:", result.get("campaign_metadata"))
print("✅ kpis:", result.get("kpis"))
print("✅ qualitative:", result.get("qualitative"))