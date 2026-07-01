import bcrypt
from .database import get_connection, hash_password

def authenticate(login: str, password: str) -> dict | None:
    with get_connection() as conn:
        user = conn.execute("SELECT * FROM users WHERE login = ?", (login.strip(),)).fetchone()
    if not user:
        return None
    stored = user["password_hash"]
    if isinstance(stored, str): stored = stored.encode("utf-8")
    return dict(user) if bcrypt.checkpw(password.encode("utf-8"), stored) else None

def change_password(user_id: int, new_password: str, clear_required_flag: bool = True) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE users SET password_hash = ?, must_change_password = ? WHERE id = ?", (hash_password(new_password), 0 if clear_required_flag else 1, user_id)); conn.commit()

def list_users() -> list[dict]:
    with get_connection() as conn:
        return [dict(row) for row in conn.execute("SELECT id, login, role, must_change_password, created_at FROM users ORDER BY login").fetchall()]

def create_user(login: str, password: str, role: str) -> None:
    with get_connection() as conn:
        conn.execute("INSERT INTO users (login, password_hash, role, must_change_password) VALUES (?, ?, ?, 1)", (login.strip(), hash_password(password), role)); conn.commit()

def update_user(user_id: int, login: str, role: str, new_password: str | None = None) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE users SET login = ?, role = ? WHERE id = ?", (login.strip(), role, user_id))
        if new_password:
            conn.execute("UPDATE users SET password_hash = ?, must_change_password = 1 WHERE id = ?", (hash_password(new_password), user_id))
        conn.commit()

def delete_user(user_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM users WHERE id = ? AND login <> 'admin'", (user_id,)); conn.commit()
