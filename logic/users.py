"""
User administration (Admin only): list, add, edit, change role,
deactivate, reset password and unlock accounts.
"""

from logic.audit import add_audit_entry
from logic.auth import find_user_by_email, get_user, hash_password, is_locked, is_valid_email, password_problem
from logic.database import fetch_all, insert, update
from logic.settings import ADMIN, ROLES, now_utc


def list_users(search="", role="", state="", sort="name"):
    users = fetch_all("SELECT * FROM users")

    if search:
        text = search.strip().lower()
        users = [user for user in users if text in user["name"].lower() or text in user["email"].lower()]
    if role:
        users = [user for user in users if user["role"] == role]
    if state == "active":
        users = [user for user in users if user["active"]]
    elif state == "inactive":
        users = [user for user in users if not user["active"]]
    elif state == "locked":
        users = [user for user in users if is_locked(user)]

    if sort == "email":
        users.sort(key=lambda user: user["email"])
    elif sort == "newest":
        users.sort(key=lambda user: (user["created_at"], user["id"]), reverse=True)
    elif sort == "oldest":
        users.sort(key=lambda user: (user["created_at"], user["id"]))
    else:
        users.sort(key=lambda user: user["name"].lower())
    return users


def save_user(admin, name, email, role, active, password, user_id=None):
    """Creates a user (user_id=None) or updates one.
    Returns (user_id, None) or (None, error message)."""
    is_new = user_id is None
    name = name.strip()
    email = email.strip().lower()

    if not name or len(name) > 80:
        return None, "Full name is required (up to 80 characters)."
    if not is_valid_email(email):
        return None, "Enter a valid email address."
    if role not in ROLES:
        return None, "Select a valid role."
    if is_new and not password:
        return None, "Password is required for a new user."
    if password:
        problem = password_problem(password)
        if problem:
            return None, problem
    if user_id == admin["id"] and (not active or role != ADMIN):
        return None, "You cannot remove your own administrator access."

    same_email_user = find_user_by_email(email)
    if same_email_user and same_email_user["id"] != user_id:
        return None, "This email is already used by another user."

    if is_new:
        user_id = insert("users", {
            "name": name, "email": email, "password_hash": hash_password(password),
            "role": role, "active": 1 if active else 0, "created_at": now_utc(),
        })
        add_audit_entry(admin["id"], "Create", "Users", user_id, None,
                        {"name": name, "email": email, "active": active, "role": role})
        return user_id, None

    old_user = get_user(user_id)
    changes = {"name": name, "email": email, "role": role, "active": 1 if active else 0}
    if password:
        changes["password_hash"] = hash_password(password)
    update("users", user_id, changes)

    if password:
        add_audit_entry(admin["id"], "Password Reset", "Users", user_id)
    if old_user["role"] != role:
        add_audit_entry(admin["id"], "Role Change", "Users", user_id, old_user["role"], role)
    add_audit_entry(admin["id"], "Update", "Users", user_id,
                    {"name": old_user["name"], "email": old_user["email"], "active": bool(old_user["active"]), "role": old_user["role"]},
                    {"name": name, "email": email, "active": active, "role": role})
    return user_id, None


def unlock_user(admin, user_id):
    update("users", user_id, {"locked_until": None, "failed_logins": 0})
    add_audit_entry(admin["id"], "Unlock", "Users", user_id)


def count_users_per_role():
    users = fetch_all("SELECT role FROM users")
    return {role: sum(1 for user in users if user["role"] == role) for role in ROLES}
