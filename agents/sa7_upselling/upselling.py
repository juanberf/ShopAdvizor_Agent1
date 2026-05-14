import anthropic
import json
import yaml
from pathlib import Path
 
from config.settings import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, INTERMEDIATE_DIR, OUTPUTS_DIR
from models.session import SessionConfig
 
 
SYSTEM_PROMPT = """Eres un experto consultor de Shopadvizor especializado en recomendar
los servicios más adecuados para cada marca según los resultados de su campaña.
 
Tu tarea es analizar los resultados de una campaña MALRG y recomendar 2-3 servicios
del catálogo de Shopadvizor que sean el siguiente paso lógico para esta marca.
 
PRINCIPIOS DE RECOMENDACIÓN:
- Las recomendaciones deben derivarse DIRECTAMENTE de los datos de la campaña
- Cada recomendación debe explicar con precisión POR QUÉ encaja con ESTA campaña específica
- Usa los datos concretos de la campaña para justificar cada recomendación
- No recomiendas todos los servicios — solo los 2-3 más relevantes
- El orden importa: el primero es el más urgente/prioritario
 
REGLAS ABSOLUTAS:
- NUNCA menciones posiciones exactas en rankings
- Usa referencias relativas: 'parte alta de la categoría', 'por encima de la media'
- No menciones competidores por nombre
- El lenguaje debe ser comercial pero basado en datos
 
FORMATO DE RESPUESTA — responde ÚNICAMENTE con este JSON:
{
  "recomendaciones": [
    {
      "producto_id": "ID del producto del catálogo (S1, S2, S3_ESSENTIEL, S3_NOTORIETE, S3_INFLUENCE)",
      "producto_nombre": "Nombre del servicio",
      "precio": "Precio del servicio",
      "por_que_encaja": "2-3 frases explicando por qué ESTE servicio es el paso lógico para ESTA campaña específica, con datos concretos",
      "problema_que_resuelve": "El problema o oportunidad concreta que aborda, en 1 frase",
      "call_to_action": "CTA personalizado para esta campaña específica"
    }
  ],
  "mensaje_cierre": "Párrafo ejecutivo de cierre con la lógica global de las recomendaciones"
}"""
 
 
def run(
    session: SessionConfig,
    analysis_data: dict,
    alerts_data: dict,
    insights_text: str,
    validated_data: dict,
) -> dict:
    """
    Ejecuta SA7: genera recomendaciones de productos Shopadvizor
    basadas en los resultados de la campaña.
 
    Args:
        session: Configuración de la sesión
        analysis_data: Análisis de SA4
        alerts_data: Alertas de SA3
        insights_text: Insights generados por SA5
        validated_data: Datos validados de SA2
 
    Returns:
        dict con las recomendaciones de upselling
    """
    print(f"[SA7] Iniciando recomendaciones de upselling para sesión {session.session_id}")
 
    # 1. Cargar catálogo de productos
    catalog = _load_catalog()
    print(f"[SA7] Catálogo cargado — {len(catalog.get('productos', []))} productos")
 
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
 
    # 2. Preparar datos de la campaña
    campaign_data = _prepare_campaign_data(validated_data, analysis_data, alerts_data)
 
    lang_instruction = (
        "Genera todas las recomendaciones en ESPAÑOL."
        if session.language == "es"
        else "Génère toutes les recommandations en FRANÇAIS."
    )
 
    print("[SA7] Generando recomendaciones con Claude...")
 
    message = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=3000,
        temperature=0,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"""{lang_instruction}
 
## RESULTADOS DE LA CAMPAÑA:
{json.dumps(campaign_data, ensure_ascii=False, indent=2)}
 
## INSIGHTS GENERADOS:
{insights_text}
 
## CATÁLOGO DE PRODUCTOS SHOPADVIZOR:
{json.dumps(catalog.get('productos', []), ensure_ascii=False, indent=2)}
 
Analiza los resultados de esta campaña y recomienda los 2-3 servicios
del catálogo que sean el siguiente paso lógico más relevante.
Justifica cada recomendación con datos concretos de esta campaña.
Responde ÚNICAMENTE con el JSON."""
        }]
    )
 
    response_text = message.content[0].text.strip()
    if response_text.startswith("```"):
        response_text = response_text.split("```")[1]
        if response_text.startswith("json"):
            response_text = response_text[4:]
    if response_text.endswith("```"):
        response_text = response_text[:-3].strip()
 
    try:
        recommendations = json.loads(response_text)
    except json.JSONDecodeError:
        from json_repair import repair_json
        recommendations = json.loads(repair_json(response_text))
 
    # 3. Guardar next_steps.json
    output_path = INTERMEDIATE_DIR / session.session_id / "next_steps.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(recommendations, f, ensure_ascii=False, indent=2)
 
    n_recs = len(recommendations.get("recomendaciones", []))
    print(f"[SA7] ✅ {n_recs} recomendaciones generadas")
 
    return recommendations
 
 
def _load_catalog() -> dict:
    """Carga el catálogo de productos desde assets/products_catalog.yaml."""
    assets_path = Path(__file__).parent.parent.parent / "assets" / "products_catalog.yaml"
    if assets_path.exists():
        with open(assets_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
 
    raise FileNotFoundError(
        f"Catálogo de productos no encontrado en {assets_path}. "
        "Crea assets/products_catalog.yaml con el catálogo de productos."
    )
 
 
def _prepare_campaign_data(
    validated_data: dict,
    analysis_data: dict,
    alerts_data: dict,
) -> dict:
    """Prepara un resumen de los datos más relevantes para el matching."""
    metadata = validated_data.get("campaign_metadata", {})
    kpis = validated_data.get("kpis", {})
 
    # Extraer valores de KPIs
    kpi_values = {}
    for kpi_name, kpi_data in kpis.items():
        if isinstance(kpi_data, dict):
            kpi_values[kpi_name] = {
                "value": kpi_data.get("value"),
                "benchmark_avg": kpi_data.get("benchmark_avg"),
                "rank": kpi_data.get("rank"),
                "total_products": kpi_data.get("total_products"),
            }
 
    # Resumen de alertas
    alerts_summary = alerts_data.get("summary", {})
    critical_alerts = [
        a["message"] for a in alerts_data.get("alerts", [])
        if a["level"] == "critical"
    ]
    positive_alerts = [
        a["message"] for a in alerts_data.get("alerts", [])
        if a["level"] == "positive"
    ]
 
    return {
        "campaign_metadata": metadata,
        "kpis": kpi_values,
        "alerts_summary": alerts_summary,
        "critical_alerts": critical_alerts[:5],
        "positive_alerts": positive_alerts[:5],
        "executive_summary": analysis_data.get("executive_summary", ""),
        "recommendations": analysis_data.get("recommendations", [])[:5],
        "competitive_positioning": analysis_data.get("competitive_analysis", {}).get("positioning", ""),
    }