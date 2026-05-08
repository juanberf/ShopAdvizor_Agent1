from pathlib import Path
from pypdf import PdfReader


def read_pdf_text(file_path: str | Path) -> str:
    """
    Extrae todo el texto del PDF de campaña.
    Devuelve el texto completo como string.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"PDF no encontrado: {file_path}")

    reader = PdfReader(file_path)
    full_text = []

    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if text:
            full_text.append(f"--- Página {i+1} ---\n{text}")

    return "\n\n".join(full_text)


def get_pdf_page_count(file_path: str | Path) -> int:
    """Devuelve el número de páginas del PDF."""
    reader = PdfReader(file_path)
    return len(reader.pages)