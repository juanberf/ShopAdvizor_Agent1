import anthropic
import json
from pathlib import Path

from config.settings import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, INTERMEDIATE_DIR, INPUTS_DIR, OUTPUTS_DIR
from models.session import SessionConfig
from agents.sa1_extractor.extractor import run as run_sa1, SourceMismatchError
from agents.sa2_validator.validator import run as run_sa2, ValidationError
from agents.sa3_alerts.alert_calculator import run as run_sa3
from agents.sa4_analyst.analyst import run as run_sa4
from agents.sa5_redactor.redactor import run as run_sa5
from agents.sa7_upselling.upselling import run as run_sa7
from tools.json_writer import save_json, load_json


CONVERSATION_SYSTEM_PROMPT = """Eres un experto Research Director de Shopadvizor con acceso 
completo a los datos de una campaña que acaba de ser analizada.

Tu rol en esta fase es responder preguntas del usuario sobre los resultados de la campaña 
de forma clara, precisa y accionable.

DATOS DISPONIBLES:
- Datos validados de la campaña (KPIs, evaluaciones pre/post, atributos, competitivo)
- Alertas calculadas por el sistema
- Análisis completo generado por el agente
- Insights generados

CÓMO RESPONDER:
- Basa SIEMPRE tus respuestas en los datos disponibles
- Si el usuario pregunta por un segmento específico, busca los datos exactos
- Si el usuario pregunta por una recomendación, explícala con datos que la justifiquen
- Si el usuario pide comparativas, calcula o extrae los datos relevantes
- Si algo no está en los datos disponibles, dilo claramente
- Usa el tono y idioma configurados en la sesión
- Sé conciso pero completo
- NUNCA menciones posiciones exactas en rankings
- Usa referencias relativas: 'parte alta de la categoría', 'por encima de la media', etc."""


class Orchestrator:
    """
    Coordinador central del pipeline ShopAdvizor Reporting Agent.
    Gestiona el flujo completo desde la subida de archivos hasta
    el one-pager final, y mantiene el modo conversacional posterior.
    """

    def __init__(self):
        self.session: SessionConfig = None
        self.raw_data: dict = None
        self.validated_data: dict = None
        self.alerts_data: dict = None
        self.analysis_data: dict = None
        self.onepager_path: Path = None
        self.pdf_path: Path = None
        self.next_steps_data: dict = None
        self.conversation_history: list = []
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    def run_pipeline(
        self,
        user_id: str,
        excel_path: Path,
        pdf_path: Path,
        tone: str = "ejecutivo",
        language: str = "es",
        focus_segments: list = None,
        progress_callback=None,
        skip_source_validation: bool = False,
    ) -> dict:
        """
        Ejecuta el pipeline completo SA1 → SA5.

        Args:
            user_id: ID del usuario
            excel_path: Ruta al Excel de campaña
            pdf_path: Ruta al PDF de campaña
            tone: Tono del one-pager
            language: Idioma del one-pager
            focus_segments: Segmentos a destacar
            progress_callback: Función opcional para reportar progreso
            skip_source_validation: Si True, salta la validación cruzada

        Returns:
            dict con status, warnings, onepager_path y session_id
        """
        def notify(step, message, percent):
            print(f"[{percent}%] {message}")
            if progress_callback:
                if step == "sa1":
                    progress_callback(step, message, 10)
            else:
                progress_callback(step, message, percent)

        # Crear sesión
        self.pdf_path = pdf_path
        self.session = SessionConfig(
            user_id=user_id,
            tone=tone,
            language=language,
            focus_segments=focus_segments or [],
            campaign_files=[excel_path.name, pdf_path.name],
        )

        notify("init", f"Sesión iniciada: {self.session.session_id}", 0)

        try:
            # ── SA1: Extracción ───────────────────────────────────
            notify("sa1", "Extrayendo datos del Excel y PDF...", 10)
            self.raw_data = run_sa1(
                self.session,
                excel_path,
                pdf_path,
                skip_source_validation=skip_source_validation,
                progress_callback=progress_callback,
            )
            notify("sa1", "✅ Datos extraídos correctamente", 25)

            # ── SA2: Validación ───────────────────────────────────
            notify("sa2", "Validando datos extraídos...", 30)
            self.validated_data = run_sa2(self.session, self.raw_data)
            warnings = self.validated_data.get("validation", {}).get("warnings", [])
            if warnings:
                notify("sa2", f"✅ Validación completada con {len(warnings)} advertencia(s)", 45)
            else:
                notify("sa2", "✅ Validación completada sin advertencias", 45)

            # ── SA3: Alertas ──────────────────────────────────────
            notify("sa3", "Calculando alertas...", 50)
            self.alerts_data = run_sa3(self.session, self.validated_data)
            summary = self.alerts_data.get("summary", {})
            notify("sa3", f"✅ Alertas calculadas — "
                          f"🔴 {summary.get('critical', 0)} críticas, "
                          f"🟡 {summary.get('warning', 0)} atención, "
                          f"🟢 {summary.get('positive', 0)} positivas", 60)

            # ── SA4: Análisis ─────────────────────────────────────
            notify("sa4", "Analizando resultados...", 65)
            self.analysis_data = run_sa4(self.session, self.validated_data, self.alerts_data)
            recs = len(self.analysis_data.get("recommendations", []))
            notify("sa4", f"✅ Análisis completado — {recs} recomendaciones generadas", 80)

            # ── SA5: Insights ─────────────────────────────────────
            notify("sa5", "Generando insights...", 85)
            self.onepager_path = run_sa5(
                self.session,
                self.analysis_data,
                self.validated_data,
                self.alerts_data,
            )
            notify("sa5", "✅ Insights generados", 100)

            # Inicializar historial conversacional
            self._init_conversation_context()

            return {
                "status": "success",
                "session_id": self.session.session_id,
                "warnings": warnings,
                "onepager_path": self.onepager_path,
                "alerts_summary": summary,
            }

        except SourceMismatchError as e:
            notify("error", str(e), 0)
            return {
                "status": "source_mismatch_error",
                "session_id": self.session.session_id,
                "error": str(e),
                "onepager_path": None,
            }

        except ValidationError as e:
            notify("error", f"❌ Error de validación: {str(e)}", 0)
            return {
                "status": "validation_error",
                "session_id": self.session.session_id,
                "error": str(e),
                "onepager_path": None,
            }

        except Exception as e:
            error_str = str(e).lower()

            if "credit balance is too low" in error_str or "billing" in error_str:
                friendly_error = (
                    "El servicio de análisis no está disponible en este momento "
                    "por un problema de configuración interna. "
                    "Por favor contacta con el administrador del sistema."
                )
            elif "overloaded" in error_str or "529" in error_str:
                friendly_error = (
                    "El servicio de análisis está recibiendo muchas solicitudes "
                    "en este momento. Por favor espera unos minutos e inténtalo de nuevo."
                )
            elif "authentication" in error_str or "401" in error_str:
                friendly_error = (
                    "Error de autenticación con el servicio de análisis. "
                    "Por favor contacta con el administrador del sistema."
                )
            elif "timeout" in error_str:
                friendly_error = (
                    "El análisis está tardando más de lo esperado. "
                    "Por favor inténtalo de nuevo."
                )
            elif "file not found" in error_str or "filenotfounderror" in error_str:
                friendly_error = (
                    "No se encontró alguno de los archivos subidos. "
                    "Por favor vuelve atrás y sube de nuevo el Excel y el PDF."
                )
            else:
                friendly_error = (
                    "Ha ocurrido un error inesperado durante el análisis. "
                    "Por favor inténtalo de nuevo o contacta con el administrador."
                )

            notify("error", f"❌ {friendly_error}", 0)
            return {
                "status": "error",
                "session_id": self.session.session_id,
                "error": friendly_error,
                "onepager_path": None,
            }

    def chat(self, user_message: str) -> dict:
        """
        Modo conversacional. Detecta si el usuario pide un PowerPoint
        y lo genera, o responde preguntas con texto normal.

        Returns:
            dict con:
              - type: 'text' o 'pptx'
              - content: texto de respuesta
              - path: ruta al .pptx (solo si type='pptx')
        """
        if not self.session:
            return {
                "type": "text",
                "content": "No hay ninguna campaña cargada. Por favor sube primero los archivos."
            }

        if not self.analysis_data:
            return {
                "type": "text",
                "content": "El pipeline aún no ha completado el análisis. Por favor espera."
            }

        # ── Detectar petición de PowerPoint ──────────────────────
        pptx_keywords = [
            "powerpoint", "power point", "pptx", "presentación",
            "presentacion", "diapositivas", "slides", "ppt",
            "présentation",
        ]
        if any(kw in user_message.lower() for kw in pptx_keywords):
            return self._generate_powerpoint(user_message=user_message)

        # ── Respuesta conversacional normal ───────────────────────
        self.conversation_history.append({
            "role": "user",
            "content": user_message,
        })

        message = self.client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=2000,
            system=self._build_conversation_system_prompt(),
            messages=self.conversation_history,
        )

        response = message.content[0].text

        self.conversation_history.append({
            "role": "assistant",
            "content": response,
        })

        return {"type": "text", "content": response}

    def reset(self):
        """Reinicia el orquestador para una nueva campaña."""
        self.session = None
        self.raw_data = None
        self.validated_data = None
        self.alerts_data = None
        self.analysis_data = None
        self.onepager_path = None
        self.pdf_path = None
        self.next_steps_data = None
        self.conversation_history = []
        print("[Orchestrator] Sesión reiniciada")

    def _generate_powerpoint(self, user_message: str = "") -> dict:
        """Genera el PowerPoint de la campaña."""
        from agents.sa6_powerpoint.powerpoint_generator import run as run_sa6

        print("[Orchestrator] Generando PowerPoint...")
        try:
            pptx_path = run_sa6(
                session=self.session,
                validated_data=self.validated_data,
                raw_data=self.raw_data,
                analysis_data=self.analysis_data,
                alerts_data=self.alerts_data,
                insights_text=self._get_insights_text(),
                user_request=user_message,
                pdf_path=self.pdf_path,
            )
            return {
                "type": "pptx",
                "content": "He generado la presentación PowerPoint. Puedes descargarla con el botón que aparece a continuación.",
                "path": pptx_path,
            }
        except Exception as e:
            print(f"[Orchestrator] Error generando PowerPoint: {e}")
            return {
                "type": "text",
                "content": "No he podido generar el PowerPoint en este momento. Por favor inténtalo de nuevo.",
            }

    def _get_insights_text(self) -> str:
        """Recupera el texto de insights del archivo generado."""
        try:
            txt_path = OUTPUTS_DIR / self.session.session_id / "insights.txt"
            if txt_path.exists():
                return txt_path.read_text(encoding="utf-8")
        except Exception:
            pass
        return ""

    def generate_upselling(self) -> dict:
        """Genera recomendaciones de upselling bajo demanda."""
        print("[Orchestrator] Generando recomendaciones de upselling...")
        try:
            next_steps = run_sa7(
                session=self.session,
                analysis_data=self.analysis_data,
                alerts_data=self.alerts_data,
                insights_text=self._get_insights_text(),
                validated_data=self.validated_data,
            )
            self.next_steps_data = next_steps
            return {"status": "success", "data": next_steps}
        except Exception as e:
            print(f"[Orchestrator] Error en SA7: {e}")
            return {"status": "error", "error": str(e)}

    def _init_conversation_context(self):
        """
        Inicializa el historial conversacional con un mensaje
        de contexto que resume la campaña analizada.
        """
        metadata = self.validated_data.get("campaign_metadata", {})
        summary = self.alerts_data.get("summary", {})
        exec_summary = self.analysis_data.get("executive_summary", "")

        if self.session.language == "fr":
            lang_instruction = "Réponds TOUJOURS en français, quelle que soit la langue utilisée par l'utilisateur."
        else:
            lang_instruction = "Responde SIEMPRE en español, independientemente del idioma que use el usuario."

        context_message = f"""El pipeline ha completado el análisis de la campaña:

Producto: {metadata.get('product_name', 'N/A')}
Marca: {metadata.get('brand', 'N/A')}
Categoría: {metadata.get('category', 'N/A')}
Fecha: {metadata.get('campaign_date', 'N/A')}

Resumen ejecutivo: {exec_summary}

Alertas: {summary.get('critical', 0)} críticas, {summary.get('warning', 0)} de atención, {summary.get('positive', 0)} positivas.

Los insights han sido generados. Estoy listo para responder preguntas sobre los resultados
o generar una presentación PowerPoint si me lo pides."""

        self.conversation_history = [
            {
                "role": "user",
                "content": context_message,
            },
            {
                "role": "assistant",
                "content": "Perfecto, tengo todos los datos de la campaña cargados. "
                           "Puedo responder preguntas sobre los resultados o generar "
                           "una presentación PowerPoint. ¿En qué puedo ayudarte?",
            },
        ]

    def _build_conversation_system_prompt(self) -> str:
        """Construye el system prompt para el modo conversacional."""

        if self.session.language == "fr":
            lang_instruction = "Réponds TOUJOURS en français, quelle que soit la langue utilisée par l'utilisateur."
        else:
            lang_instruction = "Responde SIEMPRE en español, independientemente del idioma que use el usuario."

        kpis_summary = {}
        kpis = self.validated_data.get("kpis", {})
        for kpi_name, kpi_data in kpis.items():
            if isinstance(kpi_data, dict):
                kpis_summary[kpi_name] = kpi_data.get("value")

        alerts_detail = []
        for alert in self.alerts_data.get("alerts", []):
            alerts_detail.append(f"- [{alert['level'].upper()}] {alert['message']}")

        campaign_context = f"""
{lang_instruction}

CAMPAÑA ACTIVA:
{json.dumps(self.validated_data.get('campaign_metadata', {}), ensure_ascii=False, indent=2)}

KPIs PRINCIPALES:
{json.dumps(kpis_summary, ensure_ascii=False, indent=2)}

ALERTAS:
{chr(10).join(alerts_detail)}

ANÁLISIS COMPLETO:
{json.dumps(self.analysis_data, ensure_ascii=False, indent=2)}

CONFIGURACIÓN DE SESIÓN:
- Tono: {self.session.tone}
- Idioma: {self.session.language}
- Segmentos de foco: {', '.join(self.session.focus_segments) if self.session.focus_segments else 'Todos'}
"""
        return CONVERSATION_SYSTEM_PROMPT + "\n\n" + campaign_context
