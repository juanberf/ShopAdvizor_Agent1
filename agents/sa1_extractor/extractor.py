import anthropic
import json
from pathlib import Path

from config.settings import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, INTERMEDIATE_DIR
from models.session import SessionConfig
from tools.excel_reader import read_excel_sheets
from tools.pdf_reader import read_pdf_text
from tools.json_writer import save_json


SYSTEM_PROMPT = """Eres un experto en análisis de campañas de producto de Shopadvizor.
Tu tarea es extraer y estructurar los datos de una campaña a partir de:
1. Los datos brutos del Excel (Pre y Post evaluaciones por segmento)
2. El texto extraído del PDF de resultados (KPIs, benchmark, análisis cualitativo)

IMPORTANTE:
- El Excel tiene una estructura irregular: las preguntas son filas, 
  los segmentos son columnas en pares (nº absoluto, porcentaje)
- Los segmentos son siempre: Tous, Homme, Femme, 18-24, 25-34, 35-44, 
  45-54, +54, Sin hijos, Con hijos, y regiones geográficas
- El PDF contiene KPIs globales, benchmarks vs categoría y análisis 
  cualitativo que NO están en el Excel
- Debes fusionar ambas fuentes en un único JSON estructurado

EXTRACCIÓN DE SEGMENTOS - MUY IMPORTANTE:
- Para CADA pregunta del Excel debes extraer los datos de TODOS los segmentos
  disponibles, no solo "Tous"
- Los segmentos están en las columnas del Excel en pares: 
  primera columna = número absoluto, segunda columna = porcentaje
- Usa SIEMPRE el porcentaje (%), no el número absoluto
- Si un segmento no tiene datos para una pregunta, usa null
- Los nombres de segmento en el JSON deben ser exactamente los del Excel

Responde ÚNICAMENTE con el JSON, sin explicaciones ni texto adicional.
El JSON debe seguir exactamente el esquema que se te proporcionará."""


def run(
    session: SessionConfig,
    excel_path: Path,
    pdf_path: Path,
    skip_source_validation: bool = False,
    progress_callback=None,
) -> dict:

    def notify(message):
        print(f"[SA1] {message}")
        if progress_callback:
            progress_callback("sa1", message, 10)

    print(f"[SA1] Iniciando extracción para sesión {session.session_id}")

    notify("📖 Leyendo Excel...")
    excel_data = read_excel_sheets(excel_path)
    excel_sheets = _excel_to_text_by_sheet(excel_data)
    excel_full = _excel_to_text(excel_data)

    notify("📄 Leyendo PDF...")
    pdf_text = read_pdf_text(pdf_path)

    pre_sheet_text = excel_sheets.get("Pre-évaluations", "")
    post_sheet_text = excel_sheets.get("Post-évaluations", "")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    if not skip_source_validation:
        notify("🔍 Verificando que Excel y PDF son de la misma campaña...")
        _validate_sources_match(client, excel_full, pdf_text)

    notify("🤖 Extrayendo metadatos y KPIs (1/5)...")
    part1 = _extract_part1(client, excel_full, pdf_text)

    notify("🤖 Extrayendo pre-evaluación (2/5)...")
    part2 = _extract_part2(client, pre_sheet_text)

    notify("🤖 Extrayendo post-evaluación (3/5)...")
    part3 = _extract_part3(client, post_sheet_text)

    notify("🤖 Extrayendo análisis cualitativo (4/5)...")
    part4 = _extract_part4(client, pdf_text)

    notify("🤖 Extrayendo atributos del producto (5/5)...")
    part5 = _extract_part5(client, post_sheet_text)

    campaign_data = {**part1, **part2, **part3, **part4, **part5}

    output_path = INTERMEDIATE_DIR / session.session_id / "raw.json"
    save_json(campaign_data, output_path)
    print(f"[SA1] raw.json guardado en {output_path}")

    return campaign_data


def _extract_part1(client, excel_text: str, pdf_text: str) -> dict:
    """Llamada 1: campaign_metadata + kpis + competitive"""

    schema_part1 = """
{
  "campaign_metadata": {
    "product_name": "string",
    "brand": "string",
    "category": "string",
    "campaign_date": "string",
    "campaign_price": "number",
    "ean": "string",
    "testers_count": "number",
    "products_returned": "number"
  },
  "kpis": {
    "saz_score": {"value": "number", "benchmark_min": "number", "benchmark_max": "number", "rank": "number", "total_products": "number"},
    "rating": {"value": "number", "reviews_count": "number", "rank": "number", "benchmark_min": "number", "benchmark_max": "number"},
    "nps": {"value": "number", "rank": "number", "benchmark_min": "number", "benchmark_max": "number"},
    "purchase_intent": {"value": "number", "rank": "number", "benchmark_min": "number", "benchmark_max": "number"},
    "notoriete": {"value": "number", "rank": "number"},
    "price_sensitivity": {"value": "number", "rank": "number"},
    "innovation": {"value": "number", "rank": "number"},
    "packaging": {"value": "number", "rank": "number"}
  },
  "competitive": {
    "category_rankings": {
      "kpi_name": {
        "our_rank": "number",
        "total_products": "number",
        "our_value": "number",
        "category_avg": "number",
        "category_max": "number",
        "category_min": "number"
      }
    },
    "brands_purchased": {
      "brand_name": {"purchased_12m": "number", "habitual": "number"}
    },
    "consumer_loyalty": {"fideles": "number", "non_fideles": "number"},
    "tester_profile": {
      "gender": {"homme": "number", "femme": "number"},
      "age_groups": {
        "18-24": "number",
        "25-34": "number",
        "35-44": "number",
        "45-54": "number",
        "55+": "number"
      }
    }
  }
}"""

    message = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"""Extrae ÚNICAMENTE: campaign_metadata, kpis y competitive.

## DATOS DEL EXCEL:
{excel_text}

## DATOS DEL PDF:
{pdf_text}

## ESQUEMA:
{schema_part1}

Responde ÚNICAMENTE con el JSON."""}]
    )
    return _parse_response(message.content[0].text, "parte 1")


def _extract_part2(client, pre_sheet_text: str) -> dict:
    """Llamada 2: pre_evaluation completa con todos los segmentos"""

    schema_part2 = """
{
  "pre_evaluation": {
    "segments": ["lista de todos los segmentos del Excel"],
    "questions": [
      {
        "question_id": "pre_q1",
        "question_text": "string",
        "responses": {
          "Tous": {"response_label": "percentage"},
          "Homme": {"response_label": "percentage"},
          "Femme": {"response_label": "percentage"},
          "Entre 18 et 24 ans": {"response_label": "percentage"},
          "Entre 25 et 34 ans": {"response_label": "percentage"},
          "Entre 35 et 44 ans": {"response_label": "percentage"},
          "Entre 45 et 54 ans": {"response_label": "percentage"},
          "Plus de 54 ans": {"response_label": "percentage"},
          "Sans enfants": {"response_label": "percentage"},
          "Avec enfant(s)": {"response_label": "percentage"},
          "Nord Est": {"response_label": "percentage"},
          "Nord Ouest": {"response_label": "percentage"},
          "Sud Est": {"response_label": "percentage"},
          "Sud Ouest": {"response_label": "percentage"},
          "Région Parisienne": {"response_label": "percentage"}
        }
      }
    ]
  }
}"""

    message = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"""Extrae ÚNICAMENTE la hoja Pre-évaluations con TODOS los segmentos.

## DATOS DE LA HOJA Pre-évaluations:
{pre_sheet_text}

## ESQUEMA:
{schema_part2}

CRÍTICO: 
- Extrae TODAS las preguntas de esta hoja
- Para cada pregunta extrae datos de TODOS los segmentos disponibles
- Usa siempre porcentajes, nunca números absolutos
- Responde ÚNICAMENTE con el JSON."""}]
    )
    return _parse_response(message.content[0].text, "parte 2")


def _extract_part3(client, post_sheet_text: str) -> dict:
    """Llamada 3: post_evaluation completa con todos los segmentos"""

    schema_part3 = """
{
  "post_evaluation": {
    "segments": ["lista de todos los segmentos del Excel"],
    "questions": [
      {
        "question_id": "post_q1",
        "question_text": "string",
        "responses": {
          "Tous": {"response_label": "percentage"},
          "Homme": {"response_label": "percentage"},
          "Femme": {"response_label": "percentage"},
          "Entre 18 et 24 ans": {"response_label": "percentage"},
          "Entre 25 et 34 ans": {"response_label": "percentage"},
          "Entre 35 et 44 ans": {"response_label": "percentage"},
          "Entre 45 et 54 ans": {"response_label": "percentage"},
          "Plus de 54 ans": {"response_label": "percentage"},
          "Sans enfants": {"response_label": "percentage"},
          "Avec enfant(s)": {"response_label": "percentage"},
          "Nord Est": {"response_label": "percentage"},
          "Nord Ouest": {"response_label": "percentage"},
          "Sud Est": {"response_label": "percentage"},
          "Sud Ouest": {"response_label": "percentage"},
          "Région Parisienne": {"response_label": "percentage"}
        }
      }
    ]
  }
}"""

    message = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"""Extrae ÚNICAMENTE la hoja Post-évaluations con TODOS los segmentos.

## DATOS DE LA HOJA Post-évaluations:
{post_sheet_text}

## ESQUEMA:
{schema_part3}

CRÍTICO:
- Extrae TODAS las preguntas de la hoja Post-évaluations
- Para cada pregunta extrae datos de TODOS los segmentos disponibles
- Usa siempre porcentajes, nunca números absolutos
- Responde ÚNICAMENTE con el JSON."""}]
    )
    return _parse_response(message.content[0].text, "parte 3")


def _extract_part4(client, pdf_text: str) -> dict:
    """Llamada 4: qualitative únicamente"""

    message = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"""Extrae ÚNICAMENTE el análisis cualitativo.

## DATOS DEL PDF:
{pdf_text}

## ESQUEMA:
{{
  "qualitative": {{
    "strengths": ["lista de fortalezas del producto"],
    "improvements": ["lista de oportunidades de mejora"],
    "sentiment": {{
      "very_positive": "number",
      "positive": "number",
      "neutral": "number",
      "negative": "number",
      "very_negative": "number"
    }},
    "top_keywords": ["lista de palabras clave más frecuentes"]
  }}
}}

Responde ÚNICAMENTE con el JSON."""}]
    )
    return _parse_response(message.content[0].text, "parte 4")


def _extract_part5(client, post_sheet_text: str) -> dict:
    """Llamada 5: product_attributes únicamente"""

    message = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"""Extrae ÚNICAMENTE los atributos del producto.

## DATOS DE LA HOJA Post-évaluations:
{post_sheet_text}

## ESQUEMA:
{{
  "product_attributes": {{
    "organoleptiques": {{
      "nombre_atributo": {{
        "tres_bien": "number",
        "bien": "number",
        "ni_bien_ni_mal": "number",
        "pas_bien": "number",
        "pas_bien_du_tout": "number"
      }}
    }},
    "packaging_attrs": {{
      "nombre_atributo": {{
        "tres_bien": "number",
        "bien": "number",
        "ni_bien_ni_mal": "number",
        "pas_bien": "number"
      }}
    }},
    "pre_post_comparison": [
      {{"attribute": "string", "pre": "number", "post": "number", "delta": "number"}}
    ]
  }}
}}

Responde ÚNICAMENTE con el JSON."""}]
    )
    return _parse_response(message.content[0].text, "parte 5")


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
        print(f"[SA1] ⚠️ Error parseando {label}: {e}")
        print(f"[SA1] Intentando reparar con json_repair...")
        repaired = repair_json(response_text)
        return json.loads(repaired)


def _excel_to_text_by_sheet(excel_data: dict) -> dict:
    """Convierte cada hoja del Excel a texto por separado."""
    sheets_text = {}
    for sheet_name, rows in excel_data.items():
        text_parts = []
        for row in rows:
            clean_row = [str(cell) if cell is not None else "" for cell in row]
            if any(cell.strip() for cell in clean_row):
                text_parts.append("\t".join(clean_row))
        sheets_text[sheet_name] = "\n".join(text_parts)
    return sheets_text


def _excel_to_text(excel_data: dict) -> str:
    """Convierte el dict de hojas Excel a texto legible para Claude."""
    text_parts = []
    for sheet_name, rows in excel_data.items():
        text_parts.append(f"\n### Hoja: {sheet_name}")
        for row in rows:
            clean_row = [str(cell) if cell is not None else "" for cell in row]
            if any(cell.strip() for cell in clean_row):
                text_parts.append("\t".join(clean_row))
    return "\n".join(text_parts)


class SourceMismatchError(Exception):
    """Error cuando Excel y PDF no son de la misma campaña."""
    pass


def _validate_sources_match(client, excel_text: str, pdf_text: str):
    """
    Llamada 0 — verifica que Excel y PDF son de la misma campaña
    antes de gastar tokens en la extracción completa.
    Lanza SourceMismatchError si no coinciden.
    """
    message = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=200,
        system="Eres un asistente que extrae información de documentos. Responde ÚNICAMENTE con JSON.",
        messages=[{"role": "user", "content": f"""Extrae el nombre del producto de cada fuente.

## EXCEL (primeras líneas):
{excel_text[:3000]}

## PDF (primeras líneas):
{pdf_text[:3000]}

Responde ÚNICAMENTE con este JSON:
{{
  "product_name_from_excel": "nombre exacto del producto en el Excel",
  "product_name_from_pdf": "nombre exacto del producto en el PDF"
}}"""}]
    )

    response = _parse_response(message.content[0].text, "validación cruzada")
    name_excel = response.get("product_name_from_excel", "").lower().strip()
    name_pdf = response.get("product_name_from_pdf", "").lower().strip()

    print(f"[SA1] Excel: '{response.get('product_name_from_excel')}'")
    print(f"[SA1] PDF:   '{response.get('product_name_from_pdf')}'")

    if not name_excel or not name_pdf:
        print("[SA1] ⚠️ No se pudo identificar el producto en alguna fuente — continuando")
        return

    # Palabras genéricas a ignorar
    generic = {
        "de", "la", "le", "les", "pour", "el", "para", "con",
        "et", "y", "a", "en", "du", "des", "un", "une", "the",
        "for", "with", "and", "or", "du", "au"
    }

    words_excel = set(name_excel.split()) - generic
    words_pdf = set(name_pdf.split()) - generic

    if not words_excel or not words_pdf:
        return

    common = words_excel & words_pdf
    similarity = len(common) / max(len(words_excel), len(words_pdf))

    if similarity < 0.3:
        raise SourceMismatchError(
            f"[SA1] ❌ Los archivos no son de la misma campaña:\n"
            f"       Excel: '{response.get('product_name_from_excel')}'\n"
            f"       PDF:   '{response.get('product_name_from_pdf')}'\n"
        )

    print("[SA1] ✅ Fuentes verificadas — los archivos corresponden a la misma campaña")
