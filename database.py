import os
import sqlite3
from dataclasses import dataclass
from typing import Optional


@dataclass
class UserToken:
    qq_id: str
    cred: str
    token: str
    skland_user_id: str
    phone: str
    updated_at: int


class TokenDatabase:
    def __init__(self, db_path: str):
        self._db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_tokens (
                    qq_id          TEXT PRIMARY KEY,
                    cred           TEXT NOT NULL,
                    token          TEXT NOT NULL DEFAULT '',
                    skland_user_id TEXT NOT NULL DEFAULT '',
                    phone          TEXT NOT NULL DEFAULT '',
                    updated_at     INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_phones (
                    qq_id      TEXT PRIMARY KEY,
                    phone      TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS auto_sign (
                    qq_id      TEXT PRIMARY KEY,
                    enabled    INTEGER NOT NULL DEFAULT 1,
                    notify_id  TEXT NOT NULL DEFAULT '',
                    updated_at INTEGER NOT NULL
                )
                """
            )
            conn.commit()

    def upsert(self, qq_id: str, cred: str, token: str, skland_user_id: str, phone: str, updated_at: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_tokens (qq_id, cred, token, skland_user_id, phone, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(qq_id) DO UPDATE SET
                    cred           = excluded.cred,
                    token          = excluded.token,
                    skland_user_id = excluded.skland_user_id,
                    phone          = excluded.phone,
                    updated_at     = excluded.updated_at
                """,
                (qq_id, cred, token, skland_user_id, phone, updated_at),
            )
            conn.commit()

    def get(self, qq_id: str) -> Optional[UserToken]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM user_tokens WHERE qq_id = ?", (qq_id,)
            ).fetchone()
        if row is None:
            return None
        return UserToken(
            qq_id=row["qq_id"],
            cred=row["cred"],
            token=row["token"],
            skland_user_id=row["skland_user_id"],
            phone=row["phone"],
            updated_at=row["updated_at"],
        )

    def delete(self, qq_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM user_tokens WHERE qq_id = ?", (qq_id,)
            )
            conn.commit()
        return cursor.rowcount > 0

    def all_qq_ids(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT qq_id FROM user_tokens").fetchall()
        return [r["qq_id"] for r in rows]

    def set_pending_phone(self, qq_id: str, phone: str, updated_at: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO pending_phones (qq_id, phone, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(qq_id) DO UPDATE SET
                    phone      = excluded.phone,
                    updated_at = excluded.updated_at
                """,
                (qq_id, phone, updated_at),
            )
            conn.commit()

    def get_pending_phone(self, qq_id: str) -> Optional[tuple[str, int]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT phone, updated_at FROM pending_phones WHERE qq_id = ?",
                (qq_id,),
            ).fetchone()
        if row is None:
            return None
        return row["phone"], row["updated_at"]

    def delete_pending_phone(self, qq_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM pending_phones WHERE qq_id = ?",
                (qq_id,),
            )
            conn.commit()
        return cursor.rowcount > 0

    def set_auto_sign(self, qq_id: str, enabled: bool, notify_id: str = "") -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO auto_sign (qq_id, enabled, notify_id, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(qq_id) DO UPDATE SET
                    enabled    = excluded.enabled,
                    notify_id  = excluded.notify_id,
                    updated_at = excluded.updated_at
                """,
                (qq_id, 1 if enabled else 0, notify_id, int(__import__("time").time())),
            )
            conn.commit()

    def get_auto_sign(self, qq_id: str) -> Optional[bool]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT enabled FROM auto_sign WHERE qq_id = ?", (qq_id,)
            ).fetchone()
        if row is None:
            return None
        return bool(row["enabled"])

    def all_auto_sign_qq_ids(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT qq_id FROM auto_sign WHERE enabled = 1"
            ).fetchall()
        return [r["qq_id"] for r in rows]
