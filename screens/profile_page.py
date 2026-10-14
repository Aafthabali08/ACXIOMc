"""My profile: every role can change their name and password."""

import streamlit as st

from logic import auth
from logic.settings import role_title
from screens.helpers import message_for_next_run


def show(user):
    st.title("My profile")
    st.write(f"**Email:** {user['email']}")
    st.write(f"**Role:** {role_title(user['role'])}")
    st.write(f"**Member since:** {user['created_at'][:10]}")
    st.write(f"**Previous sign-in (UTC):** {auth.previous_login_time(user['id']) or 'First sign-in'}")

    st.subheader("Change name")
    with st.form("name_form"):
        new_name = st.text_input("Full name", value=user["name"])
        if st.form_submit_button("Save name"):
            error = auth.change_my_name(user, new_name)
            if error:
                st.error(error)
            else:
                message_for_next_run("Your profile has been updated.")
                st.rerun()

    st.subheader("Change password")
    with st.form("password_form", clear_on_submit=True):
        current = st.text_input("Current password", type="password")
        new = st.text_input("New password", type="password",
                            help="At least 8 characters with upper case, lower case, a digit and a symbol.")
        confirm = st.text_input("Confirm new password", type="password")
        if st.form_submit_button("Change password"):
            error = auth.change_my_password(user, current, new, confirm)
            if error:
                st.error(error)
            else:
                message_for_next_run("Password changed.")
                st.rerun()
