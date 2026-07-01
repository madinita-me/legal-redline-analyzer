import json
import sqlite3
from pathlib import Path
from typing import Any

import bcrypt

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
LIBRARY_DIR = DATA_DIR / "legal_library"
EXPORT_DIR = DATA_DIR / "exports"
DB_PATH = DATA_DIR / "legal_analyzer.db"
REGULATION_AREAS = ["связь", "центры обработки данных", "искусственный интеллект", "кибербезопасность", "персональные данные", "конкуренция", "цифровые активы", "закупки", "трудовое право", "административная ответственность", "иное"]
DEFAULT_DICTIONARIES = {
    "Обязанности": ["обязан", "должен", "обеспечивает", "предоставляет", "направляет", "подключает", "исполняет", "финансирует", "размещает", "передает", "согласовывает", "уведомляет", "создает условия", "принимает меры"],
    "Права": ["вправе", "может", "имеет право", "допускается", "разрешается"],
    "Запреты": ["запрещается", "не допускается", "ограничивается", "приостанавливается", "прекращается", "не вправе", "обязан воздержаться"],
    "Финансовые последствия": ["расходы", "финансирование", "за счет собственных средств", "плата", "тариф", "аренда", "компенсация", "возмещение", "стоимость", "безвозмездно", "оплата", "инвестиции", "содержание инфраструктуры", "эксплуатация", "техническое обслуживание"],
    "Операционное влияние": ["сеть связи", "линии связи", "магистральные линии связи", "сооружения связи", "портовая емкость", "присоединение сетей", "ЦУСТ", "СОРМ", "центр обработки данных", "ЦОД", "оборудование", "инфраструктура", "информационная система", "подключение", "доступ", "канал связи", "трафик", "кибербезопасность", "персональные данные"],
    "Полномочия государственных органов": ["уполномоченный орган", "государственный орган", "орган национальной безопасности", "Министерство", "Комитет", "утверждает", "определяет порядок", "согласовывает", "контролирует", "требует", "направляет предписание", "по требованию", "в порядке, определяемом"],
    "Риск расширительного толкования": ["иные лица", "иные объекты", "иные случаи", "иные требования", "при необходимости", "в том числе", "соответствующие меры", "надлежащим образом", "существенное ухудшение", "и/или", "в целях обеспечения", "по согласованию", "в порядке, определяемом", "без ограничения", "и другие", "иные"],
    "Ответственность": ["штраф", "ответственность", "нарушение", "КоАП", "административная ответственность", "санкция"],
    "Телеком-инфраструктура": ["портовая емкость", "ЦУСТ", "СОРМ", "сеть связи", "магистральные линии связи", "оборудование", "подключение", "линии связи", "сооружения связи"],
    "ЦОД": ["центр обработки данных", "ЦОД", "сервер", "стойка", "дата-центр", "вычислительная инфраструктура"],
    "Кибербезопасность": ["кибербезопасность", "информационная безопасность", "инцидент", "защита информации", "угроза", "уязвимость"],
    "Персональные данные": ["персональные данные", "субъект персональных данных", "обработка персональных данных", "оператор персональных данных"],
    "Конкуренция": ["конкуренция", "доминирующее положение", "антимонопольный орган", "недискриминационный доступ", "монополия"],
}

def ensure_dirs() -> None:
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

def get_connection() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password: str) -> bytes:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

def init_db() -> None:
    ensure_dirs()
    with get_connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, login TEXT UNIQUE NOT NULL, password_hash BLOB NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin', 'user')), must_change_password INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS documents (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, doc_type TEXT NOT NULL, area TEXT NOT NULL, uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, uploaded_by INTEGER NOT NULL, file_path TEXT NOT NULL, extracted_text TEXT, description TEXT, status TEXT NOT NULL DEFAULT 'актуальный', FOREIGN KEY(uploaded_by) REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS dictionaries (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT NOT NULL, keyword TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, UNIQUE(category, keyword));
        CREATE TABLE IF NOT EXISTS analyses (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, user_id INTEGER NOT NULL, document_title TEXT, article_number TEXT, area TEXT, analysis_type TEXT, old_text TEXT NOT NULL, new_text TEXT NOT NULL, summary TEXT, changes_json TEXT, risks_json TEXT, review TEXT, risk_level TEXT, full_result_json TEXT, FOREIGN KEY(user_id) REFERENCES users(id));
        """)
        if not conn.execute("SELECT id FROM users WHERE login = 'admin'").fetchone():
            conn.execute("INSERT INTO users (login, password_hash, role, must_change_password) VALUES (?, ?, 'admin', 1)", ("admin", hash_password("admin123")))
        for category, words in DEFAULT_DICTIONARIES.items():
            for word in words:
                conn.execute("INSERT OR IGNORE INTO dictionaries (category, keyword, enabled) VALUES (?, ?, 1)", (category, word))
        conn.commit()

def get_enabled_dictionaries() -> dict[str, list[str]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT category, keyword FROM dictionaries WHERE enabled = 1 ORDER BY category, keyword").fetchall()
    data: dict[str, list[str]] = {}
    for row in rows:
        data.setdefault(row["category"], []).append(row["keyword"])
    return data

def save_analysis(user_id: int, payload: dict[str, Any]) -> int:
    with get_connection() as conn:
        cur = conn.execute("""INSERT INTO analyses (user_id, document_title, article_number, area, analysis_type, old_text, new_text, summary, changes_json, risks_json, review, risk_level, full_result_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (user_id, payload.get("document_title", ""), payload.get("article_number", ""), payload.get("area", ""), payload.get("analysis_type", ""), payload.get("old_text", ""), payload.get("new_text", ""), payload.get("summary", ""), json.dumps(payload.get("changes", []), ensure_ascii=False), json.dumps(payload.get("risks", []), ensure_ascii=False), payload.get("final_review", ""), payload.get("overall_risk", "низкий"), json.dumps(payload, ensure_ascii=False)))
        conn.commit()
        return int(cur.lastrowid)
