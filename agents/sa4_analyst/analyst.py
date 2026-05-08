import anthropic
import json
from pathlib import Path

from config.settings import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, INTERMEDIATE_DIR
from models.session import SessionConfig
from tools.json_writer import save_json, load_json


SYSTEM_PROMPT = """Eres un experto Research Director especializado en análisis de campañas 
de producto de Shopadvizor. Tu trabajo es analizar en profundidad los datos de una campaña 
y generar conclusiones accionables para el equipo de marketing y la dirección.

CONTEXTO DEL SISTEMA:
- Los datos vienen de encuestas de consumidores que han probado el producto
- El Excel contiene evaluaciones Pre (antes de probar) y Post (después de probar) por segmento
- El PDF contiene KPIs globales con benchmarks vs la categoría
- Las alertas ya han sido calculadas automáticamente por el sistema

TU ANÁLISIS DEBE:
1. Ser riguroso y basado únicamente en los datos proporcionados
2. Identificar patrones entre segmentos sociodemográficos
3. Evaluar el impacto real de la prueba del producto (Pre vs Post)
4. Contextualizar los resultados vs el benchmark de la categoría
5. Generar recomendaciones concretas y accionables
6. Usar el tono indicado en la SessionConfig

IMPORTANTE:
- No inventes datos que no estén en el JSON
- Si un dato no está disponible, indícalo explícitamente
- Las recomendaciones deben derivarse directamente del análisis
- Responde ÚNICAMENTE con el JSON, sin texto adicional"""


OUTPUT_SCHEMA = """
{
"executive_summary": "Párrafo de 3-4 líneas con la síntesis ejecutiva de la campaña",

"kpi_analysis": {
    "highlights": ["Lista de puntos fuertes basados en KPIs"],
    "concerns": ["Lista de puntos débiles o áreas de mejora"],
    "benchmark_context": "Párrafo explicando la posición del producto vs categoría"
},

"segment_analysis": {
    "best_performing_segments": [
    {
        "segment": "nombre del segmento",
        "insight": "por qué destaca este segmento"
    }
    ],
    "worst_performing_segments": [
    {
        "segment": "nombre del segmento", 
        "insight": "por qué tiene peor rendimiento"
    }
    ],
    "key_insights": ["insights relevantes del análisis cross-segmento"]
},

"pre_post_analysis": {
    "summary": "Resumen del impacto de la prueba del producto",
    "key_improvements": ["Aspectos que mejoraron significativamente tras la prueba"],
    "stable_aspects": ["Aspectos que no variaron significativamente"],
    "concerns": ["Aspectos que empeoraron o mejoraron menos de lo esperado"]
},

"competitive_analysis": {
    "positioning": "Párrafo sobre el posicionamiento vs categoría",
    "strengths_vs_category": ["Ventajas competitivas identificadas"],
    "weaknesses_vs_category": ["Desventajas o áreas de riesgo vs categoría"]
},

"qualitative_analysis": {
    "main_drivers": ["Principales drivers de satisfacción según los reviews"],
    "main_barriers": ["Principales barreras o frenos identificados"],
    "sentiment_interpretation": "Interpretación del perfil de sentimiento"
},

"recommendations": [
    {
    "priority": "alta/media/baja",
    "area": "área de acción (precio/comunicación/producto/distribución...)",
    "recommendation": "descripción concreta de la recomendación",
    "rationale": "justificación basada en los datos"
    }
]
}
"""


def run(session: SessionConfig, validated_data: dict, alerts_data: dict) -> dict:
    """
    Ejecuta SA4: analiza los datos validados y las alertas
    y genera un analysis.json con conclusiones estructuradas.

    Args:
        session: Configuración de la sesión del usuario
        validated_data: Diccionario validado generado por SA2
        alerts_data: Diccionario de alertas generado por SA3

    Returns:
        dict con el análisis completo estructurado
    """
    print(f"[SA4] Iniciando análisis para sesión {session.session_id}")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Preparar contexto de sesión
    session_context = f"""
PARÁMETROS DE LA SESIÓN:
- Tono del análisis: {session.tone}
- Idioma del one-pager: {session.language}
- Segmentos de foco: {', '.join(session.focus_segments) if session.focus_segments else 'Todos los segmentos'}
"""

    # Preparar resumen de alertas para el prompt
    alerts_summary = _format_alerts_for_prompt(alerts_data)

    # Preparar datos relevantes (sin pre/post completo para no saturar el contexto)
    analysis_data = _prepare_analysis_data(validated_data)

    print("[SA4] Enviando a Claude para análisis...")

    message = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"""Analiza en profundidad esta campaña de Shopadvizor y genera 
conclusiones accionables.

{session_context}

## DATOS DE LA CAMPAÑA:
{json.dumps(analysis_data, ensure_ascii=False, indent=2)}

## ALERTAS IDENTIFICADAS:
{alerts_summary}

## ESQUEMA DE RESPUESTA:
{OUTPUT_SCHEMA}

INSTRUCCIONES:
- Analiza todos los bloques de datos disponibles
- Cruza segmentos para identificar patrones (género, edad, región)
- Contextualiza siempre los KPIs con su benchmark de categoría
- Genera las recomendaciones que los datos justifiquen, sin límite predefinido
- Usa tono {session.tone} en todo el análisis
- Responde ÚNICAMENTE con el JSON"""
        }]
    )

    response_text = message.content[0].text
    analysis_data_result = _parse_response(response_text)

    # Guardar analysis.json
    output_path = INTERMEDIATE_DIR / session.session_id / "analysis.json"
    save_json(analysis_data_result, output_path)
    print(f"[SA4] analysis.json guardado en {output_path}")

    recs = len(analysis_data_result.get("recommendations", []))
    print(f"[SA4] ✅ Análisis completado — {recs} recomendaciones generadas")

    return analysis_data_result


def _prepare_analysis_data(validated_data: dict) -> dict:
    """
    Prepara un subconjunto de datos optimizado para el análisis.
    Incluye metadata, KPIs, competitivo, cualitativo y atributos completos.
    Para pre/post incluye solo un resumen de las preguntas clave
    para no saturar el contexto de Claude.
    """
    data = {
        "campaign_metadata": validated_data.get("campaign_metadata", {}),
        "kpis": validated_data.get("kpis", {}),
        "competitive": validated_data.get("competitive", {}),
        "qualitative": validated_data.get("qualitative", {}),
        "product_attributes": validated_data.get("product_attributes", {}),
    }

    # Para pre/post incluir solo preguntas clave con todos sus segmentos
    pre_eval = validated_data.get("pre_evaluation", {})
    post_eval = validated_data.get("post_evaluation", {})

    data["pre_evaluation_summary"] = {
        "segments": pre_eval.get("segments", []),
        "questions": _extract_key_questions(pre_eval.get("questions", [])),
    }

    data["post_evaluation_summary"] = {
        "segments": post_eval.get("segments", []),
        "questions": _extract_key_questions(post_eval.get("questions", [])),
    }

    return data


def _extract_key_questions(questions: list) -> list:
    """
    Extrae las preguntas más relevantes para el análisis.
    Prioriza intención de compra, NPS y preguntas de evaluación global.
    Incluye todas si son pocas, o las más relevantes si son muchas.
    """
    if len(questions) <= 10:
        return questions

    # Palabras clave para priorizar preguntas relevantes
    priority_keywords = [
        "intention", "achat", "recommander", "satisfaction",
        "global", "qualité", "prix", "marque", "probabilité"
    ]

    priority = []
    others = []

    for q in questions:
        text = q.get("question_text", "").lower()
        if any(kw in text for kw in priority_keywords):
            priority.append(q)
        else:
            others.append(q)

    # Devolver prioritarias + primeras del resto hasta 15 preguntas
    return priority + others[:max(0, 15 - len(priority))]


def _format_alerts_for_prompt(alerts_data: dict) -> str:
    """
    Formatea las alertas en texto legible para el prompt de Claude.
    """
    lines = []
    summary = alerts_data.get("summary", {})
    lines.append(f"Total: {summary.get('total', 0)} alertas "
                f"({summary.get('critical', 0)} críticas, "
                f"{summary.get('warning', 0)} de atención, "
                f"{summary.get('positive', 0)} positivas)")
    lines.append("")

    for alert in alerts_data.get("alerts", []):
        level = alert.get("level", "")
        emoji = {"critical": "🔴", "warning": "🟡", "positive": "🟢"}.get(level, "⚪")
        lines.append(f"{emoji} [{alert.get('kpi')}] {alert.get('message')}")

    return "\n".join(lines)


def _parse_response(response_text: str) -> dict:
    """Parsea y limpia la respuesta JSON de Claude."""
    from json_repair import repair_json

    response_text = response_text.strip()

    if response_text.startswith("```"):
        response_text = response_text.split("```")[1]
        if response_text.startswith("json"):
            response_text = response_text[4:]
    if response_text.endswith("```"):
        response_text = response_text[:-3].strip()

    try:
        return json.loads(response_text)
    except json.JSONDecodeError as e:
        print(f"[SA4] ⚠️ Error parseando respuesta: {e}")
        print(f"[SA4] Intentando reparar con json_repair...")
        repaired = repair_json(response_text)
        return json.loads(repaired)