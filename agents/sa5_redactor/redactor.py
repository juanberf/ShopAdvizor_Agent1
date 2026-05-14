import anthropic
import json
import base64
from pathlib import Path

from config.settings import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, OUTPUTS_DIR
from models.session import SessionConfig


SYSTEM_PROMPT = """Eres un experto Research Director especializado en análisis de campañas 
de producto de Shopadvizor. Tu tarea es redactar entre 3 y 10 insights ejecutivos sobre 
los resultados de una campaña.

FORMATO DE CADA INSIGHT:
Número. Dato clave con cifra concreta — explicación ejecutiva de 2-3 líneas que 
contextualiza el dato, lo compara con benchmarks cuando es relevante, y señala 
la implicación estratégica.

EJEMPLO DE INSIGHT BIEN REDACTADO:
"3. La prueba es la palanca comercial más potente — la intención de compra T2B pasa 
de 60% a 82% después del test (+22 pts). Cada contacto con el producto convierte. 
Esta es la métrica más accionable del estudio."

REGLAS ABSOLUTAS — NUNCA SE PUEDEN INCUMPLIR:
- MÁXIMO 10 insights — jamás generes más de 10 aunque haya más datos relevantes
- MÍNIMO 3 insights — nunca menos de 3
- Si hay más de 10 datos relevantes, selecciona los 10 más importantes y descarta el resto
- NUNCA menciones posiciones exactas en el ranking — ni #1, ni #2, ni posición 3 de 19,
  ni ningún número de posición. PROHIBIDO ABSOLUTAMENTE.
- En lugar de posiciones usa siempre: 'parte alta de la categoría', 'por encima de la media',
  'entre los mejores de su categoría', 'en el tramo superior', 'por debajo de la media',
  'en el tramo inferior', 'en torno a la media de categoría'
- NUNCA uses expresiones como 'líder de la categoría', 'el mejor de la categoría' o 
  'número uno de la categoría' sin contexto — esto puede confundirse con liderazgo 
  real de mercado
- Cuando un producto destaca en los rankings, especifica siempre el contexto:
  usa 'entre los productos testados en MALRG', 'en el panel de productos testados',
  'dentro de los productos evaluados en esta campaña', 'entre los referencias 
  analizadas en Carrefour Drive'
- Nunca impliques que los resultados del ranking representan el mercado completo

OTRAS REGLAS:
- Cada insight empieza con el dato más impactante, no con contexto
- Incluye siempre cifras concretas y comparativas (vs media, vs categoría, vs pre-test)
- Alterna fortalezas y alertas — no todo positivo ni todo negativo
- El último insight debe ser el más accionable estratégicamente
- No uses términos como 'fracaso', 'rechazo' o 'desastre'
- Los puntos débiles se formulan como 'áreas de fricción' u 'oportunidades de mejora'
- No menciones competidores por nombre
- No predices ventas reales — habla de potencial e intención
- Responde ÚNICAMENTE con los insights numerados, sin introducción ni conclusión"""


def run(session: SessionConfig, analysis_data: dict, validated_data: dict, alerts_data: dict) -> Path:
    """
    Ejecuta SA5: genera el documento de insights en formato .txt.

    Args:
        session: Configuración de la sesión del usuario
        analysis_data: Análisis generado por SA4
        validated_data: Datos validados de SA2
        alerts_data: Alertas generadas por SA3

    Returns:
        Path al archivo .txt generado
    """
    print(f"[SA5] Iniciando generación de insights para sesión {session.session_id}")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # 1. Preparar datos
    insights_data = _prepare_insights_data(validated_data, analysis_data, alerts_data)

    # 2. Idioma
    lang_instruction = (
        "Redacta todos los insights en ESPAÑOL."
        if session.language == "es"
        else "Rédige tous les insights en FRANÇAIS."
    )

    tone_instructions = {
        "ejecutivo": """TONO EJECUTIVO:
- Frases cortas y directas
- Empieza cada insight con el dato más impactante
- Sin jerga técnica de research
- El lector es un director que quiere el qué y el para qué""",

        "técnico": """TONO TÉCNICO:
- Usa terminología precisa: Top 2 Box, T2B, significatividad estadística
- Incluye metodología cuando sea relevante
- El lector es un analista que quiere entender los datos en profundidad
- Puedes usar términos como quintil, percentil, delta""",

        "comercial": """TONO COMERCIAL:
- Foco en oportunidades de mercado y argumentos de venta
- Énfasis en fortalezas y diferenciación competitiva
- Lenguaje orientado a acción: capitalizar, activar, convertir
- El lector es un account manager o director comercial""",
    }

    tone_instruction = tone_instructions.get(session.tone, tone_instructions["ejecutivo"])

    print("[SA5] Generando insights con Claude...")

    message = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"""{lang_instruction}
{tone_instruction}

## DATOS DE LA CAMPAÑA:
{json.dumps(insights_data, ensure_ascii=False, indent=2)}

Genera insights ejecutivos sobre esta campaña, SOLO los necesarios
Empieza directamente con el primer insight numerado."""
        }]
    )

    insights_text = message.content[0].text.strip()

    # 3. Construir contenido del .txt
    metadata = validated_data.get("campaign_metadata", {})
    product_name = metadata.get("product_name", "Campaña")
    category = metadata.get("category", "")
    campaign_date = metadata.get("campaign_date", "")
    campaign_price = metadata.get("campaign_price", "")
    ean = metadata.get("ean", "")

    # Contar insights generados
    lines = [l.strip() for l in insights_text.split("\n") if l.strip()]
    numbered = [l for l in lines if l and l[0].isdigit()]
    n_insights = len(numbered)

    separator = "=" * 60

    content = f"""{separator}
SHOPADVIZOR — TOP {n_insights} INSIGHTS
{separator}
Producto:  {product_name}
Categoría: {category}
Campaña:   {campaign_date}
Precio:    {campaign_price}€
EAN:   {ean}
{separator}

{insights_text}

{separator}
Shopadvizor | {campaign_date} 
{separator}
"""

    # 4. Guardar .txt
    session_outputs = OUTPUTS_DIR / session.session_id
    session_outputs.mkdir(parents=True, exist_ok=True)

    txt_path = session_outputs / "insights.txt"
    txt_path.write_text(content, encoding="utf-8")

    print(f"[SA5] ✅ Insights guardados en {txt_path}")
    return txt_path


def _prepare_insights_data(validated_data: dict, analysis_data: dict, alerts_data: dict) -> dict:
    """Prepara el subconjunto de datos necesario para generar los insights."""
    metadata = validated_data.get("campaign_metadata", {})
    kpis = validated_data.get("kpis", {})
    product_attrs = validated_data.get("product_attributes", {})

    alert_levels = {}
    for alert in alerts_data.get("alerts", []):
        kpi_name = alert.get("kpi", "")
        if not kpi_name.startswith("ranking_") and kpi_name != "pre_post_purchase_intent":
            alert_levels[kpi_name] = alert.get("level")

    kpis_enriched = {}
    for kpi_name, kpi_data in kpis.items():
        if isinstance(kpi_data, dict):
            kpis_enriched[kpi_name] = {
                **kpi_data,
                "alert_level": alert_levels.get(kpi_name, "ok")
            }
        else:
            kpis_enriched[kpi_name] = kpi_data

    return {
        "campaign_metadata": metadata,
        "kpis": kpis_enriched,
        "product_attributes": product_attrs,
        "alerts": alerts_data.get("alerts", []),
        "analysis": analysis_data,
    }
