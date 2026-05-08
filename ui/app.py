import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import tempfile
import shutil

from orchestrator.orchestrator import Orchestrator
from config.settings import INPUTS_DIR

hide_elements = """
    <style>
    #GithubIcon {visibility: hidden;}
    a[href*="github"] {display: none;}
    </style>
"""
st.markdown(hide_elements, unsafe_allow_html=True)

# ── Configuración de página ───────────────────────────────────
st.set_page_config(
    page_title="ShopAdvizor Reporting Agent",
    page_icon="⭐",
    layout="centered",
)

# ── CSS corporativo ───────────────────────────────────────────
st.markdown("""
<style>
    .main { background-color: #FFFFFF; }
    .stButton > button {
        background-color: #4A90D9;
        color: white;
        border-radius: 6px;
        border: none;
        padding: 10px 24px;
        font-weight: bold;
    }
    .stButton > button:hover {
        background-color: #357ABD;
    }
    .header-container {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 8px;
    }
    .insight-box {
        background: #F5F7FA;
        border-left: 4px solid #4A90D9;
        padding: 12px 16px;
        margin-bottom: 8px;
        border-radius: 0 4px 4px 0;
    }
    .chat-msg-user {
        background: #E8F4FD;
        border-radius: 8px;
        padding: 10px 14px;
        margin: 6px 0;
        text-align: right;
    }
    .chat-msg-agent {
        background: #F5F5F5;
        border-radius: 8px;
        padding: 10px 14px;
        margin: 6px 0;
    }
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────
st.markdown("""
<div class="header-container">
    <span style="font-size:28px;"><img src="https://i0.wp.com/shopadvizor.io/wp-content/uploads/2022/09/cropped-favicon.png?fit=270%2C270&ssl=1" 
     alt="Shopadvizor" 
     style="width:28px; height:28px; vertical-align:middle;"></span>
    <span style="font-size:22pt; font-weight:bold; color:#4A90D9;">ShopAdvizor</span>
    <span style="font-size:22pt; color:#F5A623;">·</span>
    <span style="font-size:14pt; color:#666;">Reporting Agent</span>
</div>
<hr style="border-top: 2px solid #4A90D9; margin-bottom: 24px;" />
""", unsafe_allow_html=True)

# ── Estado de la sesión ───────────────────────────────────────
if "orchestrator" not in st.session_state:
    st.session_state.orchestrator = Orchestrator()
if "stage" not in st.session_state:
    st.session_state.stage = "config"  # config → running → results
if "insights_text" not in st.session_state:
    st.session_state.insights_text = ""
if "insights_path" not in st.session_state:
    st.session_state.insights_path = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "pipeline_result" not in st.session_state:
    st.session_state.pipeline_result = None


# ══════════════════════════════════════════════════════════════
# STAGE 1 — CONFIGURACIÓN Y SUBIDA DE ARCHIVOS
# ══════════════════════════════════════════════════════════════
if st.session_state.stage == "config":

    st.markdown("### 📋 Configuración del análisis")
    st.markdown("Completa los siguientes campos para generar el informe de insights.")

    col1, col2 = st.columns(2)

    with col1:
        language = st.selectbox(
            "🌍 Idioma del informe",
            options=["es", "fr"],
            format_func=lambda x: "🇪🇸 Español" if x == "es" else "🇫🇷 Français",
        )

    with col2:
        tone = st.selectbox(
            "🎯 Tono del análisis",
            options=["ejecutivo", "técnico", "comercial"],
            format_func=lambda x: x.capitalize(),
        )

    st.markdown("---")
    st.markdown("### 📁 Archivos de campaña")

    col3, col4 = st.columns(2)

    with col3:
        excel_file = st.file_uploader(
            "📊 Excel de resultados (.xlsx)",
            type=["xlsx"],
            help="Archivo Excel con las evaluaciones Pre y Post de la campaña",
        )

    with col4:
        pdf_file = st.file_uploader(
            "📄 PDF de campaña (.pdf)",
            type=["pdf"],
            help="PDF con KPIs, benchmarks y análisis de Shopadvizor",
        )

    st.markdown("---")

    # Botón de lanzamiento
    ready = excel_file is not None and pdf_file is not None
    if not ready:
        st.info("📎 Sube el Excel y el PDF para continuar.")

    if st.button("🚀 Generar Informe de Insights", disabled=not ready):
        # Guardar archivos temporalmente
        session_inputs = INPUTS_DIR / "upload_temp"
        session_inputs.mkdir(parents=True, exist_ok=True)

        excel_path = session_inputs / excel_file.name
        pdf_path = session_inputs / pdf_file.name

        with open(excel_path, "wb") as f:
            f.write(excel_file.getbuffer())
        with open(pdf_path, "wb") as f:
            f.write(pdf_file.getbuffer())

        # Guardar configuración en el estado
        st.session_state.excel_path = excel_path
        st.session_state.pdf_path = pdf_path
        st.session_state.language = language
        st.session_state.tone = tone
        st.session_state.stage = "running"
        st.rerun()


# ══════════════════════════════════════════════════════════════
# STAGE 2 — EJECUCIÓN DEL PIPELINE
# ══════════════════════════════════════════════════════════════
elif st.session_state.stage == "running":

    st.markdown("### ⚙️ Generando informe...")

    progress_bar = st.progress(0)
    status_text = st.empty()

    steps_log = st.container()
    log_messages = []

    def progress_callback(step: str, message: str, percent: int):
        progress_bar.progress(percent / 100)
        status_text.markdown(f"**{message}**")
        log_messages.append(f"{'✅' if percent > 0 else '❌'} {message}")

    # Ejecutar pipeline
    result = st.session_state.orchestrator.run_pipeline(
    user_id="streamlit_user",
    excel_path=st.session_state.excel_path,
    pdf_path=st.session_state.pdf_path,
    tone=st.session_state.tone,
    language=st.session_state.language,
    progress_callback=progress_callback,
    skip_source_validation=st.session_state.get("skip_source_validation", False),
)

# Limpiar el flag después de usarlo
    st.session_state.skip_source_validation = False

    st.session_state.pipeline_result = result

    if result["status"] == "success":
        # Leer el .txt generado
        txt_path = result["onepager_path"]
        if txt_path and Path(txt_path).exists():
            st.session_state.insights_text = Path(txt_path).read_text(encoding="utf-8")
            st.session_state.insights_path = txt_path

        progress_bar.progress(1.0)
        status_text.markdown("**✅ Informe generado correctamente**")
        st.session_state.stage = "results"
        st.rerun()

    else:
        progress_bar.progress(0)
        error = result.get("error", "Error desconocido")

        if result["status"] == "source_mismatch_error":
            st.warning("⚠️ Los archivos pueden no ser de la misma campaña")
            #st.markdown(f"> {result.get('error', '')}")
            st.markdown("Verifica que has subido el Excel y PDF correctos antes de continuar.")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("✅ Continuar igualmente"):
            # Relanzar pipeline saltando la validación cruzada
            st.session_state.skip_source_validation = True
            st.session_state.stage = "running"
            st.rerun()

    with col2:
        if st.button("⬅️ Volver a cargar archivos"):
            st.session_state.orchestrator.reset()
            st.session_state.stage = "config"
            st.rerun()


# ══════════════════════════════════════════════════════════════
# STAGE 3 — RESULTADOS Y MODO CONVERSACIONAL
# ══════════════════════════════════════════════════════════════
elif st.session_state.stage == "results":

    result = st.session_state.pipeline_result
    metadata = {}
    if st.session_state.orchestrator.validated_data:
        metadata = st.session_state.orchestrator.validated_data.get(
            "campaign_metadata", {}
        )

    # Cabecera de resultados
    product_name = metadata.get("product_name", "Campaña")
    campaign_date = metadata.get("campaign_date", "")

    st.markdown(f"### 📊 Informe: {product_name}")
    if campaign_date:
        st.markdown(f"*Campaña: {campaign_date}*")

    # Warnings si los hay
    warnings = result.get("warnings", [])
    if warnings:
        with st.expander(f"⚠️ {len(warnings)} advertencia(s) en los datos"):
            for w in warnings:
                st.markdown(f"- {w}")

    st.markdown("---")

    # ── Insights ─────────────────────────────────────────────
    st.markdown("#### 💡 Insights")

    insights_text = st.session_state.insights_text
    if insights_text:
        # Mostrar en un área de texto legible
        st.text_area(
            label="Insights generados",
            value=insights_text,
            height=400,
            disabled=True,
            label_visibility="collapsed",
        )

        # Botón de descarga
        st.download_button(
            label="📥 Descargar insights (.txt)",
            data=insights_text.encode("utf-8"),
            file_name=f"insights_{product_name.replace(' ', '_')}.txt",
            mime="text/plain",
        )

    st.markdown("---")

    # ── Modo conversacional ───────────────────────────────────
    st.markdown("#### 💬 Preguntas sobre la campaña")
    st.markdown(
        "Puedes hacer preguntas sobre los resultados de la campaña. "
        "El agente tiene acceso a todos los datos analizados."
    )

    # Mostrar historial de chat
    for msg in st.session_state.chat_history:
        if msg["role"] == "user":
            st.markdown(
                f'<div class="chat-msg-user">👤 {msg["content"]}</div>',
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                f'<div class="chat-msg-agent">🤖 {msg["content"]}</div>',
                unsafe_allow_html=True
            )
            if msg.get("type") == "pptx" and msg.get("path"):
                pptx_path = Path(msg["path"])
                if pptx_path.exists():
                    with open(pptx_path, "rb") as f:
                        st.download_button(
                            label="📥 Descargar PowerPoint (.pptx)",
                            data=f.read(),
                            file_name="presentacion.pptx",
                            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                            key=f"pptx_{msg['path']}",
                        )

    # Input del usuario (fuera del bucle for)
    user_input = st.chat_input("Escribe tu pregunta aquí...")

    if user_input:
        with st.spinner("Consultando los datos de la campaña..."):
            response = st.session_state.orchestrator.chat(user_input)

        st.session_state.chat_history.append({
            "role": "user",
            "content": user_input,
            "type": "text",
        })
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": response.get("content", ""),
            "type": response.get("type", "text"),
            "path": response.get("path", None),
        })
        st.rerun()

    st.markdown("---")

    # Botón para nueva campaña
    if st.button("🔄 Analizar nueva campaña"):
        st.session_state.orchestrator.reset()
        st.session_state.stage = "config"
        st.session_state.insights_text = ""
        st.session_state.insights_path = None
        st.session_state.chat_history = []
        st.session_state.pipeline_result = None
        st.rerun()
