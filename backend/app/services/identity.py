"""Supabase-verified identity and minimal, content-free usage counters."""
import base64
import hashlib
import json
import os
import sqlite3
import time
from urllib.parse import urlparse
from pathlib import Path
from contextlib import contextmanager

import httpx
from fastapi import HTTPException

cache = {}


def configuration():
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
    public_key = key.startswith("sb_publishable_")
    if key.count(".") == 2:
        try:
            payload = key.split(".")[1]
            public_key = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))).get("role") == "anon"
        except (ValueError, TypeError):
            public_key = False
    parsed = urlparse(url)
    valid = public_key and parsed.scheme == "https" and (parsed.hostname or "").endswith(".supabase.co") and not parsed.username and parsed.path in ("", "/")
    return {"enabled": bool(url or key), "url": url if valid else "", "publishable_key": key if valid else "",
            "google_enabled": os.getenv("GOOGLE_SIGN_IN_ENABLED", "false").lower() == "true"}


def verify(token):
    config = configuration()
    if not config["enabled"] or not config["url"] or not config["publishable_key"]:
        raise HTTPException(503, "Account sign-in has not been configured yet.")
    if not token or len(token) > 8192:
        raise HTTPException(401, "Please sign in to continue.")
    key = hashlib.sha256(token.encode()).hexdigest()
    cached = cache.get(key)
    if cached and cached["until"] > time.time():
        return cached["user"]
    try:
        response = httpx.get(config["url"] + "/auth/v1/user", headers={
            "apikey": config["publishable_key"], "Authorization": "Bearer " + token,
        }, timeout=10, follow_redirects=False)
    except httpx.HTTPError:
        raise HTTPException(503, "Sign-in is temporarily unavailable. Please retry.")
    if response.status_code != 200:
        raise HTTPException(401, "Your sign-in has expired. Please sign in again.")
    user = response.json()
    if not user.get("id") or not user.get("email") or not user.get("email_confirmed_at"):
        raise HTTPException(401, "Verify your email address before signing in.")
    try:
        encoded = token.split(".")[1]
        expires = float(json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))["exp"])
    except (IndexError, ValueError, KeyError, TypeError):
        raise HTTPException(401, "Invalid sign-in token.")
    if expires <= time.time():
        raise HTTPException(401, "Your sign-in has expired. Please sign in again.")
    if len(cache) >= 1024:
        cache.clear()
    cache[key] = {"user": user, "until": min(expires, time.time() + 30)}
    return user


def administrator(user):
    emails = {e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()}
    return user["email"].lower() in emails


def connect():
    path = Path(os.getenv("USAGE_DB_PATH", str(Path(os.getenv("STORAGE_DIR", "storage")) / "usage.sqlite3")))
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.execute("CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, email TEXT NOT NULL, first_seen REAL NOT NULL, last_seen REAL NOT NULL)")
    connection.execute("CREATE TABLE IF NOT EXISTS events (user_id TEXT NOT NULL, event TEXT NOT NULL, occurred_at REAL NOT NULL)")
    connection.execute("CREATE INDEX IF NOT EXISTS events_user_time ON events(user_id, occurred_at)")
    os.chmod(path, 0o600)
    return connection


@contextmanager
def database():
    connection = connect()
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def record(user, event):
    if event not in {"sign_in", "upload", "clean", "editor_start", "editor_fix", "download"}:
        return
    now = time.time()
    with database() as connection:
        connection.execute("INSERT INTO users VALUES (?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET email=excluded.email, last_seen=excluded.last_seen", (user["id"], user["email"], now, now))
        connection.execute("INSERT INTO events VALUES (?, ?, ?)", (user["id"], event, now))
        connection.execute("DELETE FROM events WHERE occurred_at < ?", (now - 90 * 86400,))
        connection.execute("DELETE FROM users WHERE last_seen < ?", (now - 90 * 86400,))


def overview():
    with database() as connection:
        cutoff = time.time() - 90 * 86400
        connection.execute("DELETE FROM events WHERE occurred_at < ?", (cutoff,))
        connection.execute("DELETE FROM users WHERE last_seen < ?", (cutoff,))
        users = [{"id": row[0], "email": row[1], "first_seen": row[2], "last_seen": row[3], "counts": {}}
                 for row in connection.execute("SELECT id, email, first_seen, last_seen FROM users ORDER BY last_seen DESC LIMIT 500")]
        by_id = {user["id"]: user for user in users}
        for uid, event, count in connection.execute("SELECT user_id, event, COUNT(*) FROM events GROUP BY user_id, event"):
            if uid in by_id:
                by_id[uid]["counts"][event] = count
        return {"retention_days": 90, "users": users,
                "totals": dict(connection.execute("SELECT event, COUNT(*) FROM events GROUP BY event"))}
