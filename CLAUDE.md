# ShopAdvizor Reporting Agent

## Qué es
Agente de reporting automatizado que procesa campañas de Shopadvizor
y genera insights ejecutivos en formato .txt y presentaciones PowerPoint.

## Pipeline
- SA1 (Claude): Extrae datos de Excel + PDF → raw.json
- SA2 (Python): Valida el JSON
- SA3 (Python): Aplica reglas YAML → alertas
- SA4 (Claude): Análisis cross-segmento → analysis.json
- SA5 (Claude): Genera insights .txt
- SA6 (Claude + python-pptx): Genera PowerPoint

## Stack
- Python 3.11+
- Anthropic SDK
- Streamlit (UI)

## Cómo ejecutar
streamlit run ui/app.py

## Variables de entorno necesarias
- ANTHROPIC_API_KEY
- GOOGLE_DRIVE_FOLDER_ID
- ENVIRONMENT (development/production)
- APP_PASSWORD