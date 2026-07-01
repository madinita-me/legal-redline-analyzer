import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from modules.auth import authenticate, change_password, create_user, delete_user, list_users, update_user
from modules.database import LIBRARY_DIR, REGULATION_AREAS, get_connection, get_enabled_dictionaries, init_db, save_analysis
from modules.document_parser import extract_text
from modules.export_excel import export_analysis_to_excel, export_dictionary_to_excel
from modules.export_word import export_analysis_to_word
from modules.legal_rules import analyze
from modules.templates import ANALYSIS_TYPES, LEGAL_DISCLAIMER

st.set_page_config(page_title="Legal Redline Analyzer", layout="wide")
init_db()

st.markdown("""
<style>
.main .block-container {padding-top: 1.5rem; max-width: 1280px;}
.stButton>button {border-radius: 6px; font-weight: 600;}
section[data-testid="stSidebar"] {background: #f7f8fa;}
</style>
""", unsafe_allow_html=True)

if "user" not in st.session_state: st.session_state.user = None
if "analysis_result" not in st.session_state: st.session_state.analysis_result = None
if "old_prefill" not in st.session_state: st.session_state.old_prefill = ""
if "new_prefill" not in st.session_state: st.session_state.new_prefill = ""

def is_admin() -> bool:
    return bool(st.session_state.user and st.session_state.user["role"] == "admin")

def require_login():
    if st.session_state.user: return
    st.title("Legal Redline Analyzer")
    st.info("Войдите в локальное приложение. При первом запуске используйте admin / admin123.")
    with st.form("login_form"):
        login = st.text_input("Логин")
        password = st.text_input("Пароль", type="password")
        submitted = st.form_submit_button("Войти")
    if submitted:
        user = authenticate(login, password)
        if user:
            st.session_state.user = user; st.rerun()
        else: st.error("Неверный логин или пароль.")
    st.stop()

def force_password_change():
    user = st.session_state.user
    if not user or not user.get("must_change_password"): return
    st.warning("Для безопасности необходимо сменить пароль после первого входа.")
    with st.form("force_change_password"):
        new_password = st.text_input("Новый пароль", type="password")
        repeat = st.text_input("Повторите пароль", type="password")
        submitted = st.form_submit_button("Сменить пароль")
    if submitted:
        if len(new_password) < 6: st.error("Пароль должен содержать не менее 6 символов.")
        elif new_password != repeat: st.error("Пароли не совпадают.")
        else:
            change_password(user["id"], new_password)
            st.session_state.user = {**user, "must_change_password": 0}
            st.success("Пароль изменен."); st.rerun()
    st.stop()

def download_file_button(label: str, path: Path, mime: str):
    with open(path, "rb") as f:
        st.download_button(label, f, file_name=path.name, mime=mime)

def render_analysis(result: dict):
    st.subheader("Краткий вывод"); st.write(result["summary"])
    risk_label = result.get("overall_risk", "низкий")
    st.caption(f"Общий уровень риска: {risk_label}")
    st.subheader("Сравнение редакций"); st.dataframe(pd.DataFrame(result["changes"]), use_container_width=True, hide_index=True)
    tabs = st.tabs(["Добавлено", "Исключено", "Смысл", "Обязанности", "Права", "Ограничения", "Финансы", "Операции", "Госорганы", "Толкование"])
    tab_data = [("added_items", True), ("removed_items", True), ("semantic_changes", False), ("new_obligations", False), ("new_rights", False), ("prohibitions", False), ("financial", False), ("operations", False), ("authority", False), ("uncertainty", False)]
    for tab, (key, is_list) in zip(tabs, tab_data):
        with tab:
            value = result.get(key, "")
            if is_list:
                for item in value: st.markdown(f"- {item}")
            else: st.write(value)
    st.subheader("Риски для Общества"); st.dataframe(pd.DataFrame(result["risks"]), use_container_width=True, hide_index=True)
    st.subheader("Итоговый юридический обзор влияния на деятельность Общества"); st.text(result["final_review"])

    if is_admin():
        c1, c2, c3, c4 = st.columns(4)
    else:
        c1, c4 = st.columns(2)
        c2 = c3 = None
    with c1:
        if st.button("Скачать юридический обзор в Word"):
            st.session_state.word_path = str(export_analysis_to_word(result, st.session_state.user["login"]))
        if "word_path" in st.session_state: download_file_button("Загрузить Word", Path(st.session_state.word_path), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    if is_admin():
        with c2:
            if st.button("Скачать таблицу рисков в Excel"):
                st.session_state.risk_xlsx = str(export_analysis_to_excel({**result, "changes": [], "keywords": {}}, "risks"))
            if "risk_xlsx" in st.session_state: download_file_button("Загрузить риски", Path(st.session_state.risk_xlsx), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        with c3:
            if st.button("Скачать сравнительную таблицу в Excel"):
                st.session_state.comp_xlsx = str(export_analysis_to_excel({**result, "risks": [], "keywords": {}}, "comparison"))
            if "comp_xlsx" in st.session_state: download_file_button("Загрузить сравнение", Path(st.session_state.comp_xlsx), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    with c4:
        if st.button("Сохранить анализ в историю"):
            st.success(f"Анализ сохранен. ID: {save_analysis(st.session_state.user['id'], result)}")

def page_home():
    st.title("Legal Redline Analyzer")
    st.write("Legal Redline Analyzer — локальный инструмент для сравнения действующей и предлагаемой редакции нормы, выявления юридически значимых изменений и подготовки предварительного обзора влияния на деятельность Общества.")
    st.warning(LEGAL_DISCLAIMER)
    st.markdown("Все документы, результаты анализа, словари и история хранятся локально в SQLite и папках data/legal_library и data/exports.")

def page_new_analysis():
    st.title("Новый анализ")
    with st.form("analysis_form"):
        c1, c2 = st.columns(2)
        with c1:
            doc_title = st.text_input("Название документа"); article = st.text_input("Номер статьи/пункта")
        with c2:
            area = st.selectbox("Сфера регулирования", REGULATION_AREAS); analysis_type = st.selectbox("Тип анализа", ANALYSIS_TYPES)
        old_text = st.text_area("Действующая редакция нормы", value=st.session_state.old_prefill, height=260)
        new_text = st.text_area("Предлагаемая редакция нормы", value=st.session_state.new_prefill, height=260)
        submitted = st.form_submit_button("Сравнить и сформировать юридический обзор")
    if submitted:
        if not old_text.strip() or not new_text.strip(): st.error("Заполните обе редакции нормы.")
        else:
            metadata = {"document_title": doc_title, "article_number": article, "area": area, "analysis_type": analysis_type, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
            st.session_state.analysis_result = analyze(old_text, new_text, metadata, get_enabled_dictionaries())
    if st.session_state.analysis_result: render_analysis(st.session_state.analysis_result)

def page_library():
    st.title("Библиотека законодательства")
    if is_admin():
        with st.expander("Загрузить документ", expanded=True):
            with st.form("upload_document"):
                uploaded = st.file_uploader("Файл DOCX, PDF или TXT", type=["docx", "pdf", "txt"])
                title = st.text_input("Название документа")
                area = st.selectbox("Сфера регулирования", REGULATION_AREAS, key="lib_area")
                description = st.text_area("Краткое описание")
                status = st.selectbox("Статус", ["актуальный", "архивный"])
                submitted = st.form_submit_button("Сохранить документ")
            if submitted:
                if not uploaded:
                    st.error("Выберите файл для загрузки.")
                else:
                    safe_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uploaded.name}"; path = LIBRARY_DIR / safe_name
                    with open(path, "wb") as f: f.write(uploaded.getbuffer())
                    text, warning = extract_text(path)
                    with get_connection() as conn:
                        conn.execute("INSERT INTO documents (title, doc_type, area, uploaded_by, file_path, extracted_text, description, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (title.strip() or uploaded.name, Path(uploaded.name).suffix.lower(), area, st.session_state.user["id"], str(path), text, description, status)); conn.commit()
                    if warning: st.warning(warning)
                    st.success("Документ сохранен локально.")
    search = st.text_input("Поиск по названию")
    area_filter = st.selectbox("Фильтр по сфере", ["Все"] + REGULATION_AREAS)
    with get_connection() as conn:
        query = "SELECT d.*, u.login AS uploaded_login FROM documents d JOIN users u ON u.id=d.uploaded_by WHERE 1=1"; params = []
        if search: query += " AND d.title LIKE ?"; params.append(f"%{search}%")
        if area_filter != "Все": query += " AND d.area = ?"; params.append(area_filter)
        rows = [dict(r) for r in conn.execute(query + " ORDER BY uploaded_at DESC", params).fetchall()]
    if rows: st.dataframe(pd.DataFrame(rows)[["id", "title", "doc_type", "area", "uploaded_at", "uploaded_login", "status"]], use_container_width=True, hide_index=True)
    else: st.info("Документы не найдены.")
    selected = st.number_input("ID документа для просмотра", min_value=0, step=1)
    if selected:
        row = next((r for r in rows if r["id"] == selected), None)
        if row:
            st.subheader(row["title"]); text = row.get("extracted_text") or ""
            if not text and row["doc_type"] == ".pdf": st.warning("Текст из PDF не извлечен. Вероятно, документ является сканированным. Для анализа требуется текстовый PDF, DOCX или TXT.")
            fragment = st.text_area("Извлеченный текст / фрагмент для копирования", text, height=260)
            c1, c2, c3 = st.columns(3)
            if c1.button("Использовать как действующую редакцию"):
                st.session_state.old_prefill = fragment; st.success("Фрагмент перенесен в новый анализ.")
            if c2.button("Использовать как предлагаемую редакцию"):
                st.session_state.new_prefill = fragment; st.success("Фрагмент перенесен в новый анализ.")
            if is_admin() and c3.button("Удалить документ"):
                try: Path(row["file_path"]).unlink(missing_ok=True)
                except Exception: pass
                with get_connection() as conn: conn.execute("DELETE FROM documents WHERE id=?", (selected,)); conn.commit()
                st.success("Документ удален."); st.rerun()
            if is_admin():
                with st.expander("Редактировать карточку документа"):
                    with st.form(f"edit_doc_{selected}"):
                        new_title = st.text_input("Название", value=row.get("title") or "")
                        new_area = st.selectbox("Сфера", REGULATION_AREAS, index=REGULATION_AREAS.index(row.get("area")) if row.get("area") in REGULATION_AREAS else 0)
                        new_status = st.selectbox("Статус", ["актуальный", "архивный"], index=0 if row.get("status") == "актуальный" else 1)
                        new_description = st.text_area("Краткое описание", value=row.get("description") or "")
                        if st.form_submit_button("Сохранить изменения"):
                            with get_connection() as conn:
                                conn.execute("UPDATE documents SET title=?, area=?, status=?, description=? WHERE id=?", (new_title.strip() or row["title"], new_area, new_status, new_description, selected)); conn.commit()
                            st.success("Карточка документа обновлена."); st.rerun()

def page_history():
    st.title("История анализов")
    c1, c2, c3, c4, c5 = st.columns(5)
    date_q = c1.text_input("Дата"); title_q = c2.text_input("Название"); area_q = c3.selectbox("Сфера", ["Все"] + REGULATION_AREAS); risk_q = c4.selectbox("Уровень риска", ["Все", "низкий", "средний", "высокий"]); user_q = c5.text_input("Пользователь") if is_admin() else ""
    query = "SELECT a.*, u.login FROM analyses a JOIN users u ON u.id=a.user_id WHERE 1=1"; params = []
    if not is_admin(): query += " AND a.user_id=?"; params.append(st.session_state.user["id"])
    if date_q: query += " AND a.created_at LIKE ?"; params.append(f"%{date_q}%")
    if title_q: query += " AND a.document_title LIKE ?"; params.append(f"%{title_q}%")
    if area_q != "Все": query += " AND a.area=?"; params.append(area_q)
    if risk_q != "Все": query += " AND a.risk_level=?"; params.append(risk_q)
    if is_admin() and user_q: query += " AND u.login LIKE ?"; params.append(f"%{user_q}%")
    with get_connection() as conn: rows = [dict(r) for r in conn.execute(query + " ORDER BY a.created_at DESC", params).fetchall()]
    if rows:
        st.dataframe(pd.DataFrame(rows)[["id", "created_at", "login", "document_title", "area", "risk_level"]], use_container_width=True, hide_index=True)
        selected = st.number_input("ID анализа для просмотра", min_value=0, step=1)
        row = next((r for r in rows if r["id"] == selected), None)
        if row:
            render_analysis(json.loads(row["full_result_json"]))
            if is_admin() and st.button("Удалить анализ из истории"):
                with get_connection() as conn: conn.execute("DELETE FROM analyses WHERE id=?", (selected,)); conn.commit()
                st.success("Анализ удален."); st.rerun()
    else: st.info("История пуста.")

def page_dictionaries():
    st.title("Словари анализа")
    with get_connection() as conn: rows = [dict(r) for r in conn.execute("SELECT * FROM dictionaries ORDER BY category, keyword").fetchall()]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    categories = sorted({r["category"] for r in rows})
    with st.form("dict_add"):
        category = st.selectbox("Категория", categories); keyword = st.text_input("Ключевое слово"); enabled = st.checkbox("Включено", value=True)
        if st.form_submit_button("Добавить") and keyword:
            with get_connection() as conn: conn.execute("INSERT OR IGNORE INTO dictionaries (category, keyword, enabled) VALUES (?, ?, ?)", (category, keyword, 1 if enabled else 0)); conn.commit()
            st.rerun()
    c1, c2, c3 = st.columns(3); edit_id = c1.number_input("ID для редактирования/удаления", min_value=0, step=1); new_kw = c2.text_input("Новое значение"); new_enabled = c3.checkbox("Активно", value=True)
    if edit_id and st.button("Обновить ключевое слово"):
        with get_connection() as conn: conn.execute("UPDATE dictionaries SET keyword=?, enabled=? WHERE id=?", (new_kw, 1 if new_enabled else 0, edit_id)); conn.commit(); st.rerun()
    if edit_id and st.button("Удалить ключевое слово"):
        with get_connection() as conn: conn.execute("DELETE FROM dictionaries WHERE id=?", (edit_id,)); conn.commit(); st.rerun()
    uploaded = st.file_uploader("Импорт словаря из Excel", type=["xlsx"])
    if uploaded and st.button("Импортировать"):
        df = pd.read_excel(uploaded)
        with get_connection() as conn:
            for _, row in df.iterrows(): conn.execute("INSERT OR IGNORE INTO dictionaries (category, keyword, enabled) VALUES (?, ?, ?)", (str(row.get("category") or row.get("Категория")), str(row.get("keyword") or row.get("Ключевое слово")), int(row.get("enabled", row.get("Включено", 1)))))
            conn.commit()
        st.success("Импорт выполнен.")
    if st.button("Экспортировать словарь в Excel"):
        download_file_button("Загрузить словарь", export_dictionary_to_excel(rows), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

def page_admin():
    st.title("Администрирование")
    users = list_users(); st.dataframe(pd.DataFrame(users), use_container_width=True, hide_index=True)
    with st.form("create_user"):
        login = st.text_input("Логин нового пользователя")
        password = st.text_input("Пароль", type="password")
        role = st.selectbox("Роль", ["user", "admin"])
        if st.form_submit_button("Создать пользователя"):
            if not login.strip():
                st.error("Укажите логин пользователя.")
            elif len(password) < 6:
                st.error("Пароль должен содержать не менее 6 символов.")
            else:
                try: create_user(login, password, role); st.success("Пользователь создан."); st.rerun()
                except Exception as e: st.error(f"Не удалось создать пользователя: {e}")
    st.subheader("Редактирование пользователя")
    if users:
        labels = {f"{u['id']} — {u['login']} ({u['role']})": u for u in users}
        selected_label = st.selectbox("Пользователь", list(labels.keys()))
        selected_user = labels[selected_label]
        login2 = st.text_input("Логин", value=selected_user["login"])
        role2 = st.selectbox("Роль", ["user", "admin"], index=0 if selected_user["role"] == "user" else 1, key="role2")
        pwd2 = st.text_input("Новый пароль, если требуется", type="password")
        c1, c2 = st.columns(2)
        if c1.button("Обновить пользователя"):
            if not login2.strip():
                st.error("Логин не может быть пустым.")
            elif pwd2 and len(pwd2) < 6:
                st.error("Новый пароль должен содержать не менее 6 символов.")
            else:
                update_user(selected_user["id"], login2, role2, pwd2 or None); st.success("Пользователь обновлен."); st.rerun()
        if c2.button("Удалить пользователя"):
            if selected_user["login"] == "admin" or selected_user["id"] == st.session_state.user["id"]:
                st.error("Нельзя удалить основного администратора или текущего пользователя.")
            else:
                delete_user(selected_user["id"]); st.success("Пользователь удален."); st.rerun()

def page_settings():
    st.title("Настройки")
    st.write(f"Текущий пользователь: {st.session_state.user['login']} ({st.session_state.user['role']})")
    with st.form("change_password"):
        new_password = st.text_input("Новый пароль", type="password"); repeat = st.text_input("Повторите пароль", type="password")
        if st.form_submit_button("Сменить пароль"):
            if len(new_password) < 6: st.error("Пароль должен содержать не менее 6 символов.")
            elif new_password != repeat: st.error("Пароли не совпадают.")
            else: change_password(st.session_state.user["id"], new_password); st.success("Пароль изменен.")
    st.info("Приложение работает локально. Сетевые API и облачные сервисы не используются.")

require_login(); force_password_change()
st.sidebar.title("Legal Redline Analyzer"); st.sidebar.caption(f"Пользователь: {st.session_state.user['login']}")
menu = ["Главная", "Новый анализ", "Библиотека законодательства", "История анализов"]
if is_admin(): menu += ["Словари анализа", "Администрирование"]
menu += ["Настройки"]
page = st.sidebar.radio("Раздел", menu)
if st.sidebar.button("Выйти"): st.session_state.clear(); st.rerun()
if page == "Главная": page_home()
elif page == "Новый анализ": page_new_analysis()
elif page == "Библиотека законодательства": page_library()
elif page == "История анализов": page_history()
elif page == "Словари анализа" and is_admin(): page_dictionaries()
elif page == "Администрирование" and is_admin(): page_admin()
elif page == "Настройки": page_settings()
