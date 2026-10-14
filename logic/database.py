"""
Everything that talks to the SQLite database.

The whole database is one file (crm_data.db) next to app.py.
Delete that file to start again with fresh sample data.
"""

import sqlite3
from pathlib import Path

DATABASE_FILE = Path(__file__).resolve().parent.parent / "crm_data.db"


def connect():
    connection = sqlite3.connect(DATABASE_FILE)
    connection.row_factory = sqlite3.Row   # rows behave like dictionaries
    return connection


def fetch_all(sql, params=()):
    """Runs a SELECT and returns a list of dictionaries."""
    connection = connect()
    try:
        return [dict(row) for row in connection.execute(sql, params).fetchall()]
    finally:
        connection.close()


def fetch_one(sql, params=()):
    """Runs a SELECT and returns the first row as a dictionary, or None."""
    rows = fetch_all(sql, params)
    return rows[0] if rows else None


def execute(sql, params=()):
    """Runs an INSERT / UPDATE / DELETE and returns the new row id."""
    connection = connect()
    try:
        cursor = connection.execute(sql, params)
        connection.commit()
        return cursor.lastrowid
    finally:
        connection.close()


def insert(table, values):
    """insert("customers", {"name": "Ravi", ...}) -> new id"""
    columns = ", ".join(values.keys())
    placeholders = ", ".join("?" for _ in values)
    return execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", list(values.values()))


def update(table, record_id, values):
    """update("customers", 5, {"name": "Ravi"})"""
    assignments = ", ".join(f"{column} = ?" for column in values)
    execute(f"UPDATE {table} SET {assignments} WHERE id = ?", list(values.values()) + [record_id])


def create_tables():
    """Creates the tables the first time the app starts. Safe to call every time."""
    connection = connect()
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            failed_logins INTEGER NOT NULL DEFAULT 0,
            locked_until TEXT,
            created_at TEXT NOT NULL
        );

        -- Every CRM table has these common columns:
        -- name, status, notes, owner_id, created_by, created_at, updated_at, deleted

        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            phone TEXT NOT NULL UNIQUE,
            company TEXT DEFAULT '',
            address TEXT DEFAULT '',
            city TEXT DEFAULT '',
            state TEXT DEFAULT '',
            status TEXT NOT NULL,
            notes TEXT DEFAULT '',
            owner_id INTEGER REFERENCES users(id),
            created_by INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT NOT NULL,
            company TEXT DEFAULT '',
            source TEXT DEFAULT '',
            priority TEXT DEFAULT 'Normal',
            expected_value REAL DEFAULT 0,
            customer_id INTEGER REFERENCES customers(id),
            status TEXT NOT NULL,
            notes TEXT DEFAULT '',
            owner_id INTEGER REFERENCES users(id),
            created_by INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            customer_id INTEGER NOT NULL REFERENCES customers(id),
            lead_id INTEGER REFERENCES leads(id),
            stage TEXT NOT NULL DEFAULT 'Qualification',
            amount REAL NOT NULL DEFAULT 0,
            probability INTEGER NOT NULL DEFAULT 0,
            close_date TEXT NOT NULL,
            outcome_date TEXT,
            source TEXT DEFAULT '',
            status TEXT NOT NULL,
            notes TEXT DEFAULT '',
            owner_id INTEGER REFERENCES users(id),
            created_by INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS followups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            customer_id INTEGER REFERENCES customers(id),
            lead_id INTEGER REFERENCES leads(id),
            opportunity_id INTEGER REFERENCES opportunities(id),
            due_date TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'Call',
            status TEXT NOT NULL,
            notes TEXT DEFAULT '',
            owner_id INTEGER REFERENCES users(id),
            created_by INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            customer_id INTEGER REFERENCES customers(id),
            lead_id INTEGER REFERENCES leads(id),
            due_date TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'Call',
            status TEXT NOT NULL,
            notes TEXT DEFAULT '',
            owner_id INTEGER REFERENCES users(id),
            created_by INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted INTEGER NOT NULL DEFAULT 0
        );

        -- History of every change. Rows are only ever added, never edited.
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            entity TEXT NOT NULL,
            record_id TEXT NOT NULL,
            result TEXT NOT NULL DEFAULT 'Success',
            old_value TEXT,
            new_value TEXT,
            created_at TEXT NOT NULL
        );
    """)
    connection.close()
