from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError


class AuthStore:
    """Small SQLite store for local users, login flows, and application sessions."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.password_hasher = PasswordHasher()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS local_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    disabled INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS auth_flows (
                    state_hash TEXT PRIMARY KEY,
                    browser_token_hash TEXT NOT NULL,
                    expires_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_json TEXT NOT NULL,
                    auth_source TEXT NOT NULL,
                    expires_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS sessions_expires_at_idx
                    ON sessions (expires_at);
                CREATE INDEX IF NOT EXISTS auth_flows_expires_at_idx
                    ON auth_flows (expires_at);
                """
            )

    @staticmethod
    def _hash_secret(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def create_or_update_local_user(
        self,
        username: str,
        password: str,
        display_name: str,
    ) -> None:
        normalized_username = username.strip()
        normalized_display_name = display_name.strip() or normalized_username
        if not normalized_username:
            raise ValueError("Username cannot be empty")
        if len(normalized_username) > 128:
            raise ValueError("Username must be 128 characters or fewer")
        if len(password) < 12:
            raise ValueError("Password must contain at least 12 characters")

        now = int(time.time())
        password_hash = self.password_hasher.hash(password)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO local_users (
                    username, password_hash, display_name, disabled, created_at, updated_at
                ) VALUES (?, ?, ?, 0, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    password_hash = excluded.password_hash,
                    display_name = excluded.display_name,
                    disabled = 0,
                    updated_at = excluded.updated_at
                """,
                (
                    normalized_username,
                    password_hash,
                    normalized_display_name,
                    now,
                    now,
                ),
            )

    def authenticate_local_user(self, username: str, password: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, username, password_hash, display_name
                FROM local_users
                WHERE username = ? COLLATE NOCASE AND disabled = 0
                """,
                (username.strip(),),
            ).fetchone()

            if row is None:
                return None

            try:
                valid = self.password_hasher.verify(row["password_hash"], password)
            except (InvalidHashError, VerifyMismatchError):
                return None

            if not valid:
                return None

            if self.password_hasher.check_needs_rehash(row["password_hash"]):
                connection.execute(
                    "UPDATE local_users SET password_hash = ?, updated_at = ? WHERE id = ?",
                    (self.password_hasher.hash(password), int(time.time()), row["id"]),
                )

        return {
            "sub": f"local:{row['id']}",
            "name": row["display_name"],
            "displayName": row["display_name"],
            "preferred_username": row["username"],
            "roles": ["local-user"],
            "auth_source": "local",
        }

    def create_auth_flow(
        self,
        state: str,
        browser_token: str,
        ttl_seconds: int,
    ) -> None:
        now = int(time.time())
        with self._connect() as connection:
            connection.execute("DELETE FROM auth_flows WHERE expires_at <= ?", (now,))
            connection.execute(
                """
                INSERT INTO auth_flows (state_hash, browser_token_hash, expires_at)
                VALUES (?, ?, ?)
                """,
                (
                    self._hash_secret(state),
                    self._hash_secret(browser_token),
                    now + ttl_seconds,
                ),
            )

    def consume_auth_flow(self, state: str, browser_token: str) -> bool:
        now = int(time.time())
        state_hash = self._hash_secret(state)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT browser_token_hash, expires_at
                FROM auth_flows
                WHERE state_hash = ?
                """,
                (state_hash,),
            ).fetchone()
            connection.execute("DELETE FROM auth_flows WHERE state_hash = ?", (state_hash,))

        return bool(
            row
            and row["expires_at"] > now
            and row["browser_token_hash"] == self._hash_secret(browser_token)
        )

    def create_session(
        self,
        token: str,
        user: dict[str, Any],
        auth_source: str,
        ttl_seconds: int,
    ) -> None:
        now = int(time.time())
        with self._connect() as connection:
            connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
            connection.execute(
                """
                INSERT INTO sessions (token_hash, user_json, auth_source, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    self._hash_secret(token),
                    json.dumps(user, separators=(",", ":")),
                    auth_source,
                    now + ttl_seconds,
                    now,
                ),
            )

    def get_session(self, token: str) -> dict[str, Any] | None:
        if not token:
            return None

        now = int(time.time())
        token_hash = self._hash_secret(token)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT user_json, auth_source, expires_at
                FROM sessions
                WHERE token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
            if row is None:
                return None
            if row["expires_at"] <= now:
                connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
                return None

        user = json.loads(row["user_json"])
        user["auth_source"] = row["auth_source"]
        return user

    def delete_session(self, token: str) -> None:
        if not token:
            return
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM sessions WHERE token_hash = ?",
                (self._hash_secret(token),),
            )
