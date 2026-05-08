import json
from pathlib import Path


def save_json(data: dict, file_path: str | Path) -> None:
    """Guarda un dict como JSON en la ruta indicada."""
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_json(file_path: str | Path) -> dict:
    """Carga un JSON desde la ruta indicada."""
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"JSON no encontrado: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)