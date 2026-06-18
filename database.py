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
