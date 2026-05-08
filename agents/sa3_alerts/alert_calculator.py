from pathlib import Path
import yaml

from config.settings import INTERMEDIATE_DIR, RULES_DIR, ENVIRONMENT
from models.session import SessionConfig
from tools.json_writer import save_json


def run(session: SessionConfig, validated_data: dict) -> dict:
    """
    Ejecuta SA3: aplica las reglas YAML sobre el validated.json
    y genera un alerts.json con las alertas categorizadas.

    Args:
        session: Configuración de la sesión del usuario
        validated_data: Diccionario validado generado por SA2

    Returns:
        dict con las alertas generadas
    """
    print(f"[SA3] Iniciando cálculo de alertas para sesión {session.session_id}")

    # 1. Cargar reglas YAML
    rules = _load_rules()
    print(f"[SA3] Reglas cargadas — versión {rules.get('version', 'N/A')}")

    alerts = []

    # 2. Aplicar reglas de KPI
    kpis = validated_data.get("kpis", {})
    kpi_rules = rules.get("kpi_rules", {})
    _apply_kpi_rules(kpis, kpi_rules, alerts)

    # 3. Aplicar reglas de ranking
    competitive = validated_data.get("competitive", {})
    ranking_rules = rules.get("ranking_rules", {})
    _apply_ranking_rules(competitive, ranking_rules, alerts)

    # 4. Aplicar reglas Pre vs Post
    pre_eval = validated_data.get("pre_evaluation", {})
    post_eval = validated_data.get("post_evaluation", {})
    pre_post_rules = rules.get("pre_post_rules", {})
    _apply_pre_post_rules(pre_eval, post_eval, pre_post_rules, alerts)

    # 5. Resumen
    critical = [a for a in alerts if a["level"] == "critical"]
    warnings = [a for a in alerts if a["level"] == "warning"]
    positives = [a for a in alerts if a["level"] == "positive"]

    print(f"[SA3] 🔴 Alertas críticas: {len(critical)}")
    print(f"[SA3] 🟡 Alertas de atención: {len(warnings)}")
    print(f"[SA3] 🟢 Positivos destacables: {len(positives)}")

    alerts_data = {
        "session_id": session.session_id,
        "summary": {
            "total": len(alerts),
            "critical": len(critical),
            "warning": len(warnings),
            "positive": len(positives),
        },
        "alerts": alerts,
    }

    # 6. Guardar alerts.json
    output_path = INTERMEDIATE_DIR / session.session_id / "alerts.json"
    save_json(alerts_data, output_path)
    print(f"[SA3] alerts.json guardado en {output_path}")

    return alerts_data


# ── Carga de reglas ───────────────────────────────────────────────

def _load_rules() -> dict:
    """Carga el YAML de reglas desde local (development) o Drive (production)."""
    if ENVIRONMENT == "production":
        return _load_rules_from_drive()
    else:
        return _load_rules_from_local()


def _load_rules_from_local() -> dict:
    """Busca rules.yaml en assets/ o data/rules/"""
    # Intentar en assets/ primero (para Streamlit Cloud)
    assets_path = Path(__file__).parent.parent.parent / "assets" / "rules.yaml"
    if assets_path.exists():
        with open(assets_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    
    # Fallback a data/rules/ (para desarrollo local)
    rules_path = RULES_DIR / "rules.yaml"
    if not rules_path.exists():
        raise FileNotFoundError(
            f"Archivo de reglas no encontrado en {assets_path} ni en {rules_path}"
        )
    with open(rules_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_rules_from_drive() -> dict:
    """Carga las reglas desde Google Drive (production)."""
    from tools.drive_client import download_yaml_rules
    from config.settings import GOOGLE_DRIVE_FOLDER_ID
    yaml_content = download_yaml_rules(GOOGLE_DRIVE_FOLDER_ID)
    return yaml.safe_load(yaml_content)


# ── Aplicación de reglas ──────────────────────────────────────────

def _apply_kpi_rules(kpis: dict, kpi_rules: dict, alerts: list):
    """Evalúa cada KPI contra sus umbrales definidos en el YAML."""
    for kpi_name, rule in kpi_rules.items():
        if kpi_name not in kpis or kpis[kpi_name] is None:
            continue

        kpi = kpis[kpi_name]
        field = rule.get("field", "value")
        value = kpi.get(field) if isinstance(kpi, dict) else kpi

        if value is None:
            continue

        description = rule.get("description", kpi_name)
        critical_below = rule.get("critical_below")
        warning_below = rule.get("warning_below")
        good_above = rule.get("good_above")

        if critical_below is not None and value < critical_below:
            alerts.append(_make_alert(
                level="critical",
                kpi=kpi_name,
                value=value,
                threshold=critical_below,
                message=f"{description}: valor {value} por debajo del umbral crítico {critical_below}",
            ))
        elif warning_below is not None and value < warning_below:
            alerts.append(_make_alert(
                level="warning",
                kpi=kpi_name,
                value=value,
                threshold=warning_below,
                message=f"{description}: valor {value} en zona de atención (umbral: {warning_below})",
            ))
        elif good_above is not None and value >= good_above:
            alerts.append(_make_alert(
                level="positive",
                kpi=kpi_name,
                value=value,
                threshold=good_above,
                message=f"{description}: valor {value} por encima del umbral positivo {good_above}",
            ))


def _apply_ranking_rules(competitive: dict, ranking_rules: dict, alerts: list):
    """Evalúa la posición del producto en el ranking de la categoría."""
    category_rankings = competitive.get("category_rankings", {})

    for kpi_name, rule in ranking_rules.items():
        if kpi_name not in category_rankings:
            continue

        ranking = category_rankings[kpi_name]
        our_rank = ranking.get("our_rank")
        total_products = ranking.get("total_products")

        if our_rank is None or total_products is None or total_products == 0:
            continue

        # Calcular percentil (1 = mejor, 100 = peor)
        percentile = (our_rank / total_products) * 100
        description = rule.get("description", kpi_name)
        top_percentile = rule.get("top_percentile", 25)
        bottom_percentile = rule.get("bottom_percentile", 75)

        if percentile <= top_percentile:
            alerts.append(_make_alert(
                level="positive",
                kpi=f"ranking_{kpi_name}",
                value=our_rank,
                threshold=top_percentile,
                message=f"{description}: posición #{our_rank} de {total_products} productos (top {top_percentile}%)",
            ))
        elif percentile >= bottom_percentile:
            alerts.append(_make_alert(
                level="critical",
                kpi=f"ranking_{kpi_name}",
                value=our_rank,
                threshold=bottom_percentile,
                message=f"{description}: posición #{our_rank} de {total_products} productos (bottom {100 - bottom_percentile}%)",
            ))


def _apply_pre_post_rules(pre_eval: dict, post_eval: dict, pre_post_rules: dict, alerts: list):
    """Evalúa la variación entre pre y post evaluación."""
    if not pre_eval or not post_eval:
        return

    # Buscar intención de compra en pre y post
    if "purchase_intent" in pre_post_rules:
        rule = pre_post_rules["purchase_intent"]
        pre_intent = _find_purchase_intent(pre_eval)
        post_intent = _find_purchase_intent(post_eval)

        if pre_intent is not None and post_intent is not None:
            delta = post_intent - pre_intent
            description = rule.get("description", "Variación intención de compra")
            min_delta = rule.get("min_delta", 5)
            good_delta = rule.get("good_delta", 15)

            if delta >= good_delta:
                alerts.append(_make_alert(
                    level="positive",
                    kpi="pre_post_purchase_intent",
                    value=delta,
                    threshold=good_delta,
                    message=f"{description}: mejora de +{delta:.1f}pp entre pre ({pre_intent}%) y post ({post_intent}%)",
                ))
            elif delta < min_delta:
                alerts.append(_make_alert(
                    level="warning",
                    kpi="pre_post_purchase_intent",
                    value=delta,
                    threshold=min_delta,
                    message=f"{description}: variación de {delta:.1f}pp por debajo del mínimo esperado ({min_delta}pp)",
                ))


def _find_purchase_intent(evaluation: dict) -> float | None:
    """Busca el valor de intención de compra Top Box en una evaluación."""
    questions = evaluation.get("questions", [])
    for q in questions:
        text = q.get("question_text", "").lower()
        if "intention" in text and "achat" in text:
            responses = q.get("responses", {})
            tous = responses.get("Tous", {})
            if tous:
                # Top Box = "certainement" + "probablement"
                certainement = tous.get("Je l'achèterais certainement", 0) or 0
                probablement = tous.get("Je l'achèterais probablement", 0) or 0
                if certainement or probablement:
                    return certainement + probablement
    return None


# ── Helper ────────────────────────────────────────────────────────

def _make_alert(level: str, kpi: str, value: float, threshold: float, message: str) -> dict:
    """Crea un objeto de alerta estandarizado."""
    return {
        "level": level,
        "kpi": kpi,
        "value": value,
        "threshold": threshold,
        "message": message,
    }
