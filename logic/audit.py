"""
Audit log: a history line is written for every important action
(login, create, update, delete, status change, conversion ...).
"""

import json

from logic.database import execute, fetch_all
from logic.settings import now_utc


def to_text(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, default=str)


def add_audit_entry(user_id, action, entity, record_id, old_value=None, new_value=None, result="Success"):
    execute(
        "INSERT INTO audit_log (user_id, action, entity, record_id, result, old_value, new_value, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, action, entity, str(record_id), result, to_text(old_value), to_text(new_value), now_utc()),
    )


def get_record_history(module, record_id, limit=30):
    return fetch_all(
        "SELECT audit_log.*, users.name AS user_name FROM audit_log "
        "LEFT JOIN users ON users.id = audit_log.user_id "
        "WHERE entity = ? AND record_id = ? ORDER BY audit_log.id DESC LIMIT ?",
        (module, str(record_id), limit),
    )
