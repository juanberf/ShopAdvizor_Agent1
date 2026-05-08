import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator.orchestrator import Orchestrator

FIXTURES_DIR = Path(__file__).parent / "fixtures"

excel_path = FIXTURES_DIR / "202603_Result_Detail_79d75deac0.xlsx"
pdf_path = FIXTURES_DIR / "Résultats_de_la_campagne_Shopadvizor1.pdf"

# Crear orquestador
orchestrator = Orchestrator()

# Ejecutar pipeline completo
print("=" * 60)
print("🚀 Ejecutando pipeline completo...")
print("=" * 60)

result = orchestrator.run_pipeline(
    user_id="test_user",
    excel_path=excel_path,
    pdf_path=pdf_path,
    tone="ejecutivo",
    language="es",
    focus_segments=[],
)

print("\n" + "=" * 60)
print("📊 Resultado del pipeline:")
print("=" * 60)
print(f"Status: {result['status']}")
print(f"Session ID: {result['session_id']}")
print(f"One-Pager: {result['onepager_path']}")

if result['warnings']:
    print(f"\n⚠️  Warnings ({len(result['warnings'])}):")
    for w in result['warnings']:
        print(f"   - {w}")

if result['status'] != 'success':
    print(f"\n❌ Error: {result.get('error')}")
    sys.exit(1)

# Modo conversacional
print("\n" + "=" * 60)
print("💬 Iniciando modo conversacional...")
print("=" * 60)

preguntas = [
    "¿Cuál es el KPI más destacable de esta campaña?",
    "¿Qué segmento tiene mejor intención de compra?",
    "¿Por qué hay alerta en el precio?",
]

for pregunta in preguntas:
    print(f"\n👤 Usuario: {pregunta}")
    respuesta = orchestrator.chat(pregunta)
    print(f"🤖 Agente: {respuesta}")
    print("-" * 40)