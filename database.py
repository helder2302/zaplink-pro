import sqlite3
from datetime import datetime, timedelta

DB_NAME = "app.db"


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            premium_active INTEGER NOT NULL DEFAULT 0,
            premium_until TEXT,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            mp_payment_id TEXT,
            status TEXT,
            external_reference TEXT,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def upsert_user(name: str, email: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT id FROM users WHERE email = ?", (email,))
    existing = cur.fetchone()

    now = datetime.utcnow().isoformat()

    if existing:
        cur.execute(
            "UPDATE users SET name = ? WHERE email = ?",
            (name, email)
        )
    else:
        cur.execute(
            "INSERT INTO users (name, email, created_at) VALUES (?, ?, ?)",
            (name, email, now)
        )

    conn.commit()
    conn.close()


def get_user_by_email(email: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = ?", (email,))
    user = cur.fetchone()
    conn.close()
    return user


def activate_premium(email: str, days: int = 30):
    conn = get_connection()
    cur = conn.cursor()

    premium_until = (datetime.utcnow() + timedelta(days=days)).isoformat()

    cur.execute("""
        UPDATE users
        SET premium_active = 1,
            premium_until = ?
        WHERE email = ?
    """, (premium_until, email))

    conn.commit()
    conn.close()


def is_user_premium(email: str) -> bool:
    user = get_user_by_email(email)
    if not user:
        return False

    if not user["premium_active"]:
        return False

    premium_until = user["premium_until"]
    if not premium_until:
        return False

    try:
        premium_until_dt = datetime.fromisoformat(premium_until)
    except ValueError:
        return False

    return premium_until_dt > datetime.utcnow()


def save_payment(email: str, mp_payment_id: str, status: str, external_reference: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO payments (email, mp_payment_id, status, external_reference, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (
        email,
        mp_payment_id,
        status,
        external_reference,
        datetime.utcnow().isoformat()
    ))

    conn.commit()
    conn.close()