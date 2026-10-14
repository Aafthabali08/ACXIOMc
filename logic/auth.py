"""
Login, logout, registration, passwords and the user's own profile.

Passwords are never stored as plain text. We store a salted PBKDF2 hash
(built into Python, no extra library needed).
"""

import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from logic.audit import add_audit_entry
from logic.database import fetch_one, insert, update
from logic.settings import LOCK_MINUTES, MAX_FAILED_LOGINS, SALES_EXECUTIVE, now_utc

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------- Password helpers ----------

def hash_password(password):
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return salt.hex() + "$" + digest.hex()


def password_matches(password, stored_hash):
    salt_hex, digest_hex = stored_hash.split("$")
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 200_000)
    return secrets.compare_digest(digest.hex(), digest_hex)


def password_problem(password):
    """Returns an error message if the password is too weak, otherwise None."""
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if not re.search(r"[A-Z]", password):
        return "Password must contain an uppercase letter."
    if not re.search(r"[a-z]", password):
        return "Password must contain a lowercase letter."
    if not re.search(r"[0-9]", password):
        return "Password must contain a digit."
    if not re.search(r"[^A-Za-z0-9]", password):
        return "Password must contain a symbol, for example @ or #."
    return None


def is_valid_email(email):
    return bool(EMAIL_PATTERN.match(email or ""))


# ---------- Finding users ----------

def get_user(user_id):
    return fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))


def find_user_by_email(email):
    return fetch_one("SELECT * FROM users WHERE lower(email) = lower(?)", (email.strip(),))


def is_locked(user):
    return bool(user["locked_until"]) and user["locked_until"] > now_utc()


# ---------- Login / logout / register ----------

def login(email, password):
    """Returns (user, None) on success or (None, error message) on failure."""
    user = find_user_by_email(email)

    if user and user["active"] and is_locked(user):
        add_audit_entry(user["id"], "Lockout", "Authentication", user["id"], result="Failed")
        return None, "Account is temporarily locked. Please try again after the lockout period."

    # An inactive account gets the same message as a wrong password.
    if user and user["active"] and password_matches(password, user["password_hash"]):
        update("users", user["id"], {"failed_logins": 0, "locked_until": None})
        add_audit_entry(user["id"], "Login", "Authentication", user["id"])
        return get_user(user["id"]), None

    if user:
        failed_logins = user["failed_logins"] + 1
        if failed_logins >= MAX_FAILED_LOGINS:
            locked_until = (datetime.now(timezone.utc) + timedelta(minutes=LOCK_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
            update("users", user["id"], {"failed_logins": 0, "locked_until": locked_until})
            add_audit_entry(user["id"], "Lockout", "Authentication", user["id"], result="Failed")
            return None, "Account is temporarily locked. Please try again after the lockout period."
        update("users", user["id"], {"failed_logins": failed_logins})

    add_audit_entry(user["id"] if user else None, "Failed Login", "Authentication",
                    user["id"] if user else "unknown", result="Failed")
    return None, "Invalid login details or inactive account."


def logout(user_id):
    add_audit_entry(user_id, "Logout", "Authentication", user_id)


def register(name, email, password, confirm_password):
    """Self registration. New users always get the Sales Executive role.
    Returns (user, None) or (None, error message)."""
    name = name.strip()
    email = email.strip().lower()
    if not name or len(name) > 80:
        return None, "Full name is required (up to 80 characters)."
    if not is_valid_email(email):
        return None, "Enter a valid email address."
    if find_user_by_email(email):
        return None, "This email is already registered."
    problem = password_problem(password)
    if problem:
        return None, problem
    if password != confirm_password:
        return None, "Both passwords must match."

    user_id = insert("users", {
        "name": name, "email": email, "password_hash": hash_password(password),
        "role": SALES_EXECUTIVE, "active": 1, "created_at": now_utc(),
    })
    add_audit_entry(user_id, "Register", "Users", user_id)
    add_audit_entry(user_id, "Login", "Authentication", user_id)
    return get_user(user_id), None


# ---------- My profile ----------

def change_my_name(user, new_name):
    new_name = new_name.strip()
    if not new_name or len(new_name) > 80:
        return "Full name is required (up to 80 characters)."
    update("users", user["id"], {"name": new_name})
    add_audit_entry(user["id"], "Profile Update", "Users", user["id"], {"name": user["name"]}, {"name": new_name})
    return None


def change_my_password(user, current_password, new_password, confirm_password):
    """Returns an error message, or None when the password was changed."""
    if not password_matches(current_password, user["password_hash"]):
        add_audit_entry(user["id"], "Password Change", "Users", user["id"], result="Failed")
        return "Current password is not correct."
    problem = password_problem(new_password)
    if problem:
        return problem
    if new_password != confirm_password:
        return "Both passwords must match."
    update("users", user["id"], {"password_hash": hash_password(new_password)})
    add_audit_entry(user["id"], "Password Change", "Users", user["id"])
    return None


def previous_login_time(user_id):
    """The login before the current one (the newest login is this session)."""
    row = fetch_one(
        "SELECT created_at FROM audit_log WHERE user_id = ? AND action = 'Login' "
        "ORDER BY id DESC LIMIT 1 OFFSET 1", (user_id,))
    return row["created_at"] if row else None
