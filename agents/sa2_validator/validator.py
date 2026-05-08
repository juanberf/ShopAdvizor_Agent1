from pathlib import Path

from config.settings import INTERMEDIATE_DIR
from models.session import SessionConfig
from tools.json_writer import save_json, load_json


# ── Campos obligatorios ───────────────────────────────────────────
REQUIRED_TOP_LEVEL = [
    "campaign_metadata",
    "kpis",
    "pre_evaluation",
    "post_evaluation",
    "product_attributes",
    "qualitative",
    "competitive",
]

REQUIRED_METADATA = [
    "product_name",
    "brand",
    "category",
    "campaign_date",
    "campaign_price",
]

REQUIRED_KPIS = [
    "saz_score",
    "rating",
    "nps",
    "purchase_intent",
    "price_sensitivity",
]

# ── Rangos válidos de KPIs ────────────────────────────────────────
KPI_RANGES = {
    "saz_score":        (0, 100),
    "rating":           (0, 5),
    "nps":              (-100, 100),
    "purchase_intent":  (0, 100),
    "notoriete":        (0, 100),
    "price_sensitivity":(-100, 100),
    "innovation":       (0, 100),
    "packaging":        (0, 10),
}


class ValidationError(Exception):
    """Error crítico que detiene el pipeline."""
    pass


def run(session: SessionConfig, raw_data: dict) -> dict:
    """
    Ejecuta SA2: valida el raw.json generado por SA1.

    Args:
        session: Configuración de la sesión del usuario
        raw_data: Diccionario con los datos brutos de SA1

    Returns:
        validated_data: raw_data con campo 'validation' añadido

    Raises:
        ValidationError: Si hay errores críticos que impiden continuar
    """
    print(f"[SA2] Iniciando validación para sesión {session.session_id}")

    errors = []
    warnings = []

    # 1. Validar campos de primer nivel
    _validate_top_level(raw_data, errors)

    # Si faltan campos críticos, detener ya — el resto de validaciones fallarían
    if errors:
        _fail(session, errors, warnings)

    # 2. Validar campaign_metadata
    _validate_metadata(raw_data["campaign_metadata"], errors, warnings)

    # 3. Validar KPIs
    _validate_kpis(raw_data["kpis"], errors, warnings)

    # 4. Validar evaluaciones
    _validate_evaluations(raw_data["pre_evaluation"], "pre_evaluation", errors, warnings)
    _validate_evaluations(raw_data["post_evaluation"], "post_evaluation", errors, warnings)

    # 5. Validar consistencia entre pre y post
    _validate_segment_consistency(raw_data, warnings)

    # 6. Validar qualitative
    _validate_qualitative(raw_data["qualitative"], errors, warnings)

    # Si hay errores críticos, detener el pipeline
    if errors:
        _fail(session, errors, warnings)

    # Todo correcto — guardar validated.json
    status = "ok" if not warnings else "ok_with_warnings"
    validated_data = {
        **raw_data,
        "validation": {
            "status": status,
            "warnings": warnings,
            "errors": [],
        }
    }

    output_path = INTERMEDIATE_DIR / session.session_id / "validated.json"
    save_json(validated_data, output_path)
    print(f"[SA2] validated.json guardado en {output_path}")

    if warnings:
        print(f"[SA2] ⚠️  {len(warnings)} warning(s):")
        for w in warnings:
            print(f"       - {w}")

    print(f"[SA2] ✅ Validación completada — status: {status}")
    return validated_data


# ── Funciones de validación ───────────────────────────────────────

def _validate_top_level(data: dict, errors: list):
    """Verifica que existen todos los bloques principales del JSON."""
    for field in REQUIRED_TOP_LEVEL:
        if field not in data or data[field] is None:
            errors.append(f"Campo obligatorio ausente o nulo: '{field}'")


def _validate_metadata(metadata: dict, errors: list, warnings: list):
    """Valida los metadatos de la campaña."""
    for field in REQUIRED_METADATA:
        if field not in metadata or metadata[field] is None:
            errors.append(f"Metadato obligatorio ausente: 'campaign_metadata.{field}'")

    # campaign_price debe ser número positivo
    price = metadata.get("campaign_price")
    if price is not None:
        if not isinstance(price, (int, float)):
            errors.append("'campaign_metadata.campaign_price' debe ser un número")
        elif price <= 0:
            warnings.append("'campaign_metadata.campaign_price' es 0 o negativo")

    # testers_count debe ser número positivo
    testers = metadata.get("testers_count")
    if testers is not None:
        if not isinstance(testers, (int, float)):
            warnings.append("'campaign_metadata.testers_count' no es un número")
        elif testers < 30:
            warnings.append(f"Muestra pequeña: solo {testers} testeurs")


def _validate_kpis(kpis: dict, errors: list, warnings: list):
    """Valida los KPIs principales."""
    for kpi_name in REQUIRED_KPIS:
        if kpi_name not in kpis or kpis[kpi_name] is None:
            errors.append(f"KPI obligatorio ausente: 'kpis.{kpi_name}'")
            continue

        kpi = kpis[kpi_name]
        value = kpi.get("value") if isinstance(kpi, dict) else kpi

        if value is None:
            errors.append(f"'kpis.{kpi_name}.value' es nulo")
            continue

        if not isinstance(value, (int, float)):
            errors.append(f"'kpis.{kpi_name}.value' debe ser un número, recibido: {type(value)}")
            continue

        # Validar rango
        if kpi_name in KPI_RANGES:
            min_val, max_val = KPI_RANGES[kpi_name]
            if not (min_val <= value <= max_val):
                errors.append(
                    f"'kpis.{kpi_name}.value' fuera de rango: {value} "
                    f"(esperado entre {min_val} y {max_val})"
                )

        # ── NUEVO: Warning para KPIs críticos con valor 0 ──────────
        ZERO_SUSPICIOUS_KPIS = ["saz_score", "rating", "nps", "purchase_intent"]
        if value == 0 and kpi_name in ZERO_SUSPICIOUS_KPIS:
            warnings.append(
                f"'kpis.{kpi_name}.value' es 0 — "
                f"verifica que SA1 extrajo correctamente los datos"
            )


def _validate_evaluations(evaluation: dict, name: str, errors: list, warnings: list):
    """Valida la estructura de pre o post evaluación."""
    if not isinstance(evaluation, dict):
        errors.append(f"'{name}' debe ser un objeto")
        return

    if "segments" not in evaluation or not evaluation["segments"]:
        warnings.append(f"'{name}.segments' está vacío")

    if "questions" not in evaluation or not evaluation["questions"]:
        errors.append(f"'{name}.questions' está vacío — no hay preguntas")
        return

    if not isinstance(evaluation["questions"], list):
        errors.append(f"'{name}.questions' debe ser una lista")
        return

    # Verificar que las preguntas tienen estructura básica
    for i, q in enumerate(evaluation["questions"]):
        if not isinstance(q, dict):
            errors.append(f"'{name}.questions[{i}]' no es un objeto válido")
            continue
        if "question_text" not in q or not q.get("question_text"):
            warnings.append(f"'{name}.questions[{i}]' no tiene 'question_text'")
        if "responses" not in q or not q.get("responses"):
            warnings.append(f"'{name}.questions[{i}]' no tiene respuestas")
        elif "Tous" not in q["responses"]:
            warnings.append(f"'{name}.questions[{i}]' no tiene datos para el segmento 'Tous'")


def _validate_segment_consistency(data: dict, warnings: list):
    """Verifica que pre y post tienen los mismos segmentos."""
    pre_segments = set(data["pre_evaluation"].get("segments", []))
    post_segments = set(data["post_evaluation"].get("segments", []))

    if pre_segments != post_segments:
        only_pre = pre_segments - post_segments
        only_post = post_segments - pre_segments
        if only_pre:
            warnings.append(f"Segmentos solo en pre_evaluation: {only_pre}")
        if only_post:
            warnings.append(f"Segmentos solo en post_evaluation: {only_post}")


def _validate_qualitative(qualitative: dict, errors: list, warnings: list):
    """Valida el bloque qualitative."""
    if not isinstance(qualitative, dict):
        errors.append("'qualitative' debe ser un objeto")
        return

    if not qualitative.get("strengths"):
        warnings.append("'qualitative.strengths' está vacío")

    if not qualitative.get("improvements"):
        warnings.append("'qualitative.improvements' está vacío")

    sentiment = qualitative.get("sentiment")
    if sentiment:
        for key in ["very_positive", "positive", "neutral", "negative", "very_negative"]:
            val = sentiment.get(key)
            if val is not None and not isinstance(val, (int, float)):
                warnings.append(f"'qualitative.sentiment.{key}' no es un número")


def _fail(session: SessionConfig, errors: list, warnings: list):
    """Guarda el estado de error y lanza la excepción que detiene el pipeline."""
    error_data = {
        "validation": {
            "status": "failed",
            "warnings": warnings,
            "errors": errors,
        }
    }
    output_path = INTERMEDIATE_DIR / session.session_id / "validated.json"
    save_json(error_data, output_path)

    error_msg = f"[SA2] ❌ Validación fallida con {len(errors)} error(s):\n"
    for e in errors:
        error_msg += f"       - {e}\n"

    raise ValidationError(error_msg)