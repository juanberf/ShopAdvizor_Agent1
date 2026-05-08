import pandas as pd
from pathlib import Path


def read_excel_sheets(file_path: str | Path) -> dict:
    """
    Lee todas las hojas del Excel de campaña.
    Devuelve un dict con nombre de hoja -> lista de filas brutas.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Excel no encontrado: {file_path}")

    workbook = {}
    xl = pd.ExcelFile(file_path)

    for sheet_name in xl.sheet_names:
        df = pd.read_excel(
            xl,
            sheet_name=sheet_name,
            header=None  # Sin header porque la estructura es irregular
        )
        # Convertir a lista de listas, reemplazando NaN por None
        rows = df.where(pd.notna(df), None).values.tolist()
        workbook[sheet_name] = rows

    return workbook


def get_sheet_names(file_path: str | Path) -> list[str]:
    """Devuelve los nombres de las hojas del Excel."""
    xl = pd.ExcelFile(file_path)
    return xl.sheet_names