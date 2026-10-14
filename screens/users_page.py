"""User administration and roles (Admin only)."""

import streamlit as st

from logic import users as user_admin
from logic.auth import get_user, is_locked
from logic.settings import ROLES, nice_date, role_title
from screens.helpers import go_to, message_for_next_run, show_table

ROLE_PERMISSIONS = {
    "Admin": "Everything: users, roles, audit log, all records and reports.",
    "Manager": "All business records, team performance, team activity and reports. No user administration.",
    "SalesExecutive": "Only records assigned to them, their own dashboard and reports.",
}


def show(user, option=None):
    if option == "roles":
        roles_view()
    elif option == "new":
        user_form(user, None)
    elif option == "edit":
        existing = get_user(st.session_state.get("record_id"))
        if existing is None:
            st.error("User not found.")
        else:
            user_form(user, existing)
    else:
        list_view(user)


def list_view(admin):
    st.title("Users & access")
    if st.button("Add new user"):
        go_to("users", "new")
        st.rerun()

    columns = st.columns(4)
    search = columns[0].text_input("Search name or email")
    role = columns[1].selectbox("Role", [""] + ROLES, format_func=lambda value: role_title(value) if value else "All roles")
    state = columns[2].selectbox("State", ["", "active", "inactive", "locked"], format_func=lambda value: value.title() or "All")
    sort = columns[3].selectbox("Sort by", ["name", "email", "newest", "oldest"])

    rows = user_admin.list_users(search, role, state, sort)
    show_table(rows, {
        "Name": "name", "Email": "email", "Role": lambda row: role_title(row["role"]),
        "Active": lambda row: "Yes" if row["active"] else "No",
        "Locked": lambda row: "Yes" if is_locked(row) else "No",
        "Created": lambda row: nice_date(row["created_at"]),
    }, "No users found.")

    if rows:
        options = {f"{row['name']} ({row['email']})": row for row in rows}
        left, middle, right = st.columns([4, 1, 1])
        chosen = options[left.selectbox("Choose a user", list(options))]
        middle.write("")
        middle.write("")
        if middle.button("Edit"):
            go_to("users", "edit", record_id=chosen["id"])
            st.rerun()
        if is_locked(chosen):
            right.write("")
            right.write("")
            if right.button("Unlock"):
                user_admin.unlock_user(admin, chosen["id"])
                message_for_next_run(f"{chosen['name']}'s account has been unlocked.")
                st.rerun()


def user_form(admin, existing):
    is_new = existing is None
    if st.button("← Back to users"):
        go_to("users")
        st.rerun()
    st.title("Add new user" if is_new else f"Edit {existing['name']}")

    with st.form("user_form"):
        name = st.text_input("Full name", value="" if is_new else existing["name"])
        email = st.text_input("Email", value="" if is_new else existing["email"])
        role = st.selectbox("Role", ROLES, format_func=role_title,
                            index=ROLES.index("SalesExecutive" if is_new else existing["role"]))
        active = st.checkbox("Active", value=True if is_new else bool(existing["active"]))
        password = st.text_input("Password" if is_new else "New password (leave empty to keep the current one)",
                                 type="password")
        submitted = st.form_submit_button("Save")

    if submitted:
        _, error = user_admin.save_user(admin, name, email, role, active, password,
                                        None if is_new else existing["id"])
        if error:
            st.error(error)
        else:
            message_for_next_run(f"User {name} created." if is_new else f"Details for {name} saved.")
            go_to("users")
            st.rerun()


def roles_view():
    st.title("Roles & permissions")
    counts = user_admin.count_users_per_role()
    show_table([{"role": role} for role in ROLES], {
        "Role": lambda row: role_title(row["role"]),
        "Users": lambda row: counts[row["role"]],
        "What they can do": lambda row: ROLE_PERMISSIONS[row["role"]],
    })
