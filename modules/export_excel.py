from pathlib import Path
import pandas as pd
from .database import EXPORT_DIR

def export_analysis_to_excel(result: dict, kind: str = "full") -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    safe = (result.get("document_title") or "analysis").replace("/", "_").replace("\\", "_")[:60]
    path = EXPORT_DIR / f"legal_tables_{kind}_{safe}.xlsx"
    keywords = [{"Категория": cat, "Ключевое слово": word} for cat, words in result.get("keywords", {}).items() for word in words]
    overview = [{"Раздел": "Краткий вывод", "Текст": result.get("summary", "")}, {"Раздел": "Итоговый обзор", "Текст": result.get("final_review", "")}, {"Раздел": "Общий уровень риска", "Текст": result.get("overall_risk", "")}]
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(result.get("changes", [])).to_excel(writer, sheet_name="Сравнение", index=False)
        pd.DataFrame(result.get("risks", [])).to_excel(writer, sheet_name="Риски", index=False)
        pd.DataFrame(keywords).to_excel(writer, sheet_name="Ключевые слова", index=False)
        pd.DataFrame(overview).to_excel(writer, sheet_name="Общий обзор", index=False)
    return path

def export_dictionary_to_excel(rows: list[dict]) -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPORT_DIR / "analysis_dictionaries.xlsx"
    pd.DataFrame(rows).to_excel(path, index=False)
    return path
