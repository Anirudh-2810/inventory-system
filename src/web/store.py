"""User persistence for the web tier (same SQLite file as inventory data).

Passwords are hashed with PBKDF2-HMAC-SHA256 via auth.hash_password — never
stored in plaintext, logs, or responses.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, Optional

from auth import hash_password, verify_password


class UserStore:
    def __init__(self, db_path: str) -> None:
        self.db_file = db_path
        self._init_db()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_file)
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id         TEXT PRIMARY KEY,
                    email      TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    salt       TEXT NOT NULL,
                    role       TEXT NOT NULL DEFAULT 'user',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_email ON users (email)"
            )
            conn.commit()

    def create_user(self, email: str, password: str, role: str = "user") -> Dict:
        """Create a user. Raises ValueError if the email already exists."""
        if not email or "@" not in email:
            raise ValueError("A valid email is required")
        if not password or len(password) < 8:
            raise ValueError("Password must be at least 8 characters")

        import uuid
        user_id = str(uuid.uuid4())
        pw_hash, salt = hash_password(password)
        now = datetime.now().isoformat()
        try:
            with self._connect() as conn:
                conn.execute(
                    """INSERT INTO users (id, email, password_hash, salt, role, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (user_id, email.lower(), pw_hash, salt, role, now, now),
                )
                conn.commit()
        except sqlite3.IntegrityError:
            raise ValueError("Email already registered")

        return {"id": user_id, "email": email.lower(), "role": role}

    def get_by_email(self, email: str) -> Optional[Dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, email, password_hash, salt, role FROM users WHERE email = ?",
                (email.lower(),),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0], "email": row[1], "password_hash": row[2],
            "salt": row[3], "role": row[4],
        }

    def get_by_id(self, user_id: str) -> Optional[Dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, email, role FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        if row is None:
            return None
        return {"id": row[0], "email": row[1], "role": row[2]}

    def verify_credentials(self, email: str, password: str) -> Optional[Dict]:
        """Return the user dict if credentials are valid, else None."""
        user = self.get_by_email(email)
        if user is None:
            # Run a dummy hash to equalize timing and avoid user enumeration.
            hash_password("dummy-password-for-timing")
            return None
        if verify_password(password, user["password_hash"], user["salt"]):
            return user
        return None

    def update_password(self, user_id: str, new_password: str) -> None:
        if not new_password or len(new_password) < 8:
            raise ValueError("Password must be at least 8 characters")
        pw_hash, salt = hash_password(new_password)
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET password_hash = ?, salt = ?, updated_at = ? WHERE id = ?",
                (pw_hash, salt, datetime.now().isoformat(), user_id),
            )
            conn.commit()
