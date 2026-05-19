import anthropic
import json
import concurrent.futures
from pathlib import Path

from config.settings import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, INTERMEDIATE_DIR
from models.session import SessionConfig
from tools.json_writer import save_json


SYSTEM_PROMPT = """Eres un experto Research Director especializado en análisis de campañas 
de producto de Shopadvizor. Tu trabajo es analizar en profundidad los datos de una campaña 
y generar conclusiones accionables para el equipo de marketing y la dirección.

CONTEXTO DEL SISTEMA:
- Los datos vienen de encuestas de consumidores que han probado el producto
- El Excel contiene evaluaciones Pre (antes de probar) y Post (después de probar) por segmento
- El PDF contiene KPIs globales con benchmarks vs la categoría
- Las alertas ya han sido calculadas automáticamente por el sistema

IMPORTANTE:
- No inventes datos que no estén en el JSON
- Si un dato no está disponible, indícalo explícitamente
- Las recomendaciones deben derivarse directamente del análisis
- Responde ÚNICAMENTE con el JSON, sin texto adicional
- NUNCA menciones posiciones exactas en rankings
- Usa referencias relativas: parte alta, media o baja de la categoría"""


def run(session: SessionConfig, validated_data: dict, alerts_data: dict) -> dict:
    """
    Ejecuta SA4 con 4 llamadas paralelas a Claude.
    """
    print(f"[SA4] Iniciando análisis para sesión {session.session_id}")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    analysis_input = _prepare_analysis_data(validated_data)
    alerts_summary = _format_alerts_for_prompt(alerts_data)
    session_context = f"Tono: {session.tone} | Idioma: {session.language} | Segmentos: {', '.join(session.focus_segments) if session.focus_segments else 'Todos'}"

    print("[SA4] Lanzando 4 análisis en paralelo...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        future_kpis = executor.submit(
            _analyze_kpis,
            client, analysis_input, alerts_summary, session_context
        )
        future_segments = executor.submit(
            _analyze_segments,
            client, analysis_input, alerts_summary, session_context
        )
        future_prepost = executor.submit(
            _analyze_prepost_qualitative,
            client, analysis_input, alerts_summary, session_context
        )
        future_recs = executor.submit(
            _analyze_recommendations,
            client, analysis_input, alerts_summary, session_context
        )

        kpis_result = future_kpis.result()
        print("[SA4] ✅ KPIs y competitivo completado")

        segments_result = future_segments.result()
        print("[SA4] ✅ Segmentos completado")

        prepost_result = future_prepost.result()
        print("[SA4] ✅ Pre/Post y cualitativo completado")

        recs_result = future_recs.result()
        print("[SA4] ✅ Recomendaciones completado")

    # Fusionar resultados
    analysis_data = {
        "executive_summary": kpis_result.get("executive_summary", ""),
        "kpi_analysis": kpis_result.get("kpi_analysis", {}),
        "competitive_analysis": kpis_result.get("competitive_analysis", {}),
        "segment_analysis": segments_result.get("segment_analysis", {}),
        "pre_post_analysis": prepost_result.get("pre_post_analysis", {}),
        "qualitative_analysis": prepost_result.get("qualitative_analysis", {}),
        "recommendations": recs_result.get("recommendations", []),
    }

    output_path = INTERMEDIATE_DIR / session.session_id / "analysis.json"
    save_json(analysis_data, output_path)
    print(f"[SA4] analysis.json guardado en {output_path}")

    recs = len(analysis_data.get("recommendations", []))
    print(f"[SA4] ✅ Análisis completado — {recs} recomendaciones generadas")

    return analysis_data


def _analyze_kpis(client, analysis_data: dict, alerts_summary: str, session_context: str) -> dict:
    """Llamada 1: executive summary + KPIs + competitivo."""
    message = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=3000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"""{session_context}

Analiza los KPIs principales y el posicionamiento competitivo.

## DATOS:
{json.dumps({
    "campaign_metadata": analysis_data.get("campaign_metadata", {}),
    "kpis": analysis_data.get("kpis", {}),
    "competitive": analysis_data.get("competitive", {}),
}, ensure_ascii=False, indent=2)}

## ALERTAS:
{alerts_summary}

Responde ÚNICAMENTE con este JSON:
{{
  "executive_summary": "párrafo de 3-4 líneas con síntesis ejecutiva",
  "kpi_analysis": {{
    "highlights": ["puntos fuertes basados en KPIs"],
    "concerns": ["puntos débiles o áreas de mejora"],
    "benchmark_context": "posición relativa vs categoría"
  }},
  "competitive_analysis": {{
    "positioning": "posicionamiento vs categoría",
    "strengths_vs_category": ["ventajas competitivas"],
    "weaknesses_vs_category": ["desventajas vs categoría"]
  }}
}}"""}]
    )
    return _parse_response(message.content[0].text, "KPIs")


def _analyze_segments(client, analysis_data: dict, alerts_summary: str, session_context: str) -> dict:
    """Llamada 2: análisis por segmento."""
    message = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=3000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"""{session_context}

Analiza el rendimiento por segmentos sociodemográficos.

## DATOS:
{json.dumps({
    "campaign_metadata": analysis_data.get("campaign_metadata", {}),
    "pre_evaluation_summary": analysis_data.get("pre_evaluation_summary", {}),
    "post_evaluation_summary": analysis_data.get("post_evaluation_summary", {}),
}, ensure_ascii=False, indent=2)}

Responde ÚNICAMENTE con este JSON:
{{
  "segment_analysis": {{
    "best_performing_segments": [
      {{"segment": "nombre", "insight": "por qué destaca"}}
    ],
    "worst_performing_segments": [
      {{"segment": "nombre", "insight": "por qué tiene peor rendimiento"}}
    ],
    "key_insights": ["insights relevantes del análisis cross-segmento"]
  }}
}}"""}]
    )
    return _parse_response(message.content[0].text, "segmentos")


def _analyze_prepost_qualitative(client, analysis_data: dict, alerts_summary: str, session_context: str) -> dict:
    """Llamada 3: análisis pre/post + cualitativo."""
    message = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=3000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"""{session_context}

Analiza el impacto de la prueba (pre vs post) y el análisis cualitativo.

## DATOS:
{json.dumps({
    "campaign_metadata": analysis_data.get("campaign_metadata", {}),
    "pre_evaluation_summary": analysis_data.get("pre_evaluation_summary", {}),
    "post_evaluation_summary": analysis_data.get("post_evaluation_summary", {}),
    "qualitative": analysis_data.get("qualitative", {}),
    "product_attributes": analysis_data.get("product_attributes", {}),
}, ensure_ascii=False, indent=2)}

Responde ÚNICAMENTE con este JSON:
{{
  "pre_post_analysis": {{
    "summary": "resumen del impacto de la prueba",
    "key_improvements": ["aspectos que mejoraron significativamente"],
    "stable_aspects": ["aspectos que no variaron"],
    "concerns": ["aspectos que empeoraron o mejoraron menos de lo esperado"]
  }},
  "qualitative_analysis": {{
    "main_drivers": ["principales drivers de satisfacción"],
    "main_barriers": ["principales barreras identificadas"],
    "sentiment_interpretation": "interpretación del perfil de sentimiento"
  }}
}}"""}]
    )
    return _parse_response(message.content[0].text, "pre/post y cualitativo")


def _analyze_recommendations(client, analysis_data: dict, alerts_summary: str, session_context: str) -> dict:
    """Llamada 4: recomendaciones estratégicas."""
    message = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=3000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"""{session_context}

Genera recomendaciones estratégicas accionables basadas en los datos de la campaña.

## DATOS:
{json.dumps({
    "campaign_metadata": analysis_data.get("campaign_metadata", {}),
    "kpis": analysis_data.get("kpis", {}),
    "competitive": analysis_data.get("competitive", {}),
    "qualitative": analysis_data.get("qualitative", {}),
}, ensure_ascii=False, indent=2)}

## ALERTAS:
{alerts_summary}

Responde ÚNICAMENTE con este JSON:
{{
  "recommendations": [
    {{
      "priority": "alta/media/baja",
      "area": "área de acción",
      "recommendation": "descripción concreta",
      "rationale": "justificación basada en los datos"
    }}
  ]
}}"""}]
    )
    return _parse_response(message.content[0].text, "recomendaciones")


def _prepare_analysis_data(validated_data: dict) -> dict:
    """Prepara los datos para el análisis."""
    pre_eval = validated_data.get("pre_evaluation", {})
    post_eval = validated_data.get("post_evaluation", {})

    return {
        "campaign_metadata": validated_data.get("campaign_metadata", {}),
        "kpis": validated_data.get("kpis", {}),
        "competitive": validated_data.get("competitive", {}),
        "qualitative": validated_data.get("qualitative", {}),
        "product_attributes": validated_data.get("product_attributes", {}),
        "pre_evaluation_summary": {
            "segments": pre_eval.get("segments", []),
            "questions": _extract_key_questions(pre_eval.get("questions", [])),
        },
        "post_evaluation_summary": {
            "segments": post_eval.get("segments", []),
            "questions": _extract_key_questions(post_eval.get("questions", [])),
        },
    }


def _extract_key_questions(questions: list) -> list:
    """Extrae las preguntas más relevantes."""
    if len(questions) <= 10:
        return questions

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

    return priority + others[:max(0, 15 - len(priority))]


def _format_alerts_for_prompt(alerts_data: dict) -> str:
    """Formatea las alertas para el prompt."""
    lines = []
    summary = alerts_data.get("summary", {})
    lines.append(f"Total: {summary.get('total', 0)} alertas "
                f"({summary.get('critical', 0)} críticas, "
                f"{summary.get('warning', 0)} de atención, "
                f"{summary.get('positive', 0)} positivas)")

    for alert in alerts_data.get("alerts", []):
        level = alert.get("level", "")
        emoji = {"critical": "🔴", "warning": "🟡", "positive": "🟢"}.get(level, "⚪")
        lines.append(f"{emoji} [{alert.get('kpi')}] {alert.get('message')}")

    return "\n".join(lines)


def _parse_response(response_text: str, label: str) -> dict:
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
        print(f"[SA4] ⚠️ Error parseando {label}: {e}")
        repaired = repair_json(response_text)
        return json.loads(repaired)
