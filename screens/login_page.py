"""Login and registration screen (shown when nobody is signed in)."""

import streamlit as st

from logic import auth
from screens.helpers import go_to, message_for_next_run


def show():
    st.title("AcxiomCRM")

    login_tab, register_tab = st.tabs(["Log in", "Register"])

    with login_tab:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log in")
        if submitted:
            if not email or not password:
                st.error("Enter your email and password.")
            else:
                user, error = auth.login(email, password)
                if error:
                    st.error(error)
                else:
                    sign_in(user)

        with st.expander("Demo accounts"):
            st.write("Password for all demo accounts: **Acxiom@123**")
            st.table({
                "Role": ["Admin", "Manager", "Sales Executive", "Sales Executive"],
                "Email": ["admin@acxiom.test", "manager@acxiom.test", "sales@acxiom.test", "sales2@acxiom.test"],
            })

    with register_tab:
        st.caption("New accounts get the Sales Executive role. An admin can change it later.")
        with st.form("register_form"):
            name = st.text_input("Full name")
            email = st.text_input("Email", key="register_email")
            password = st.text_input("Password", type="password", key="register_password",
                                     help="At least 8 characters with upper case, lower case, a digit and a symbol.")
            confirm = st.text_input("Confirm password", type="password")
            submitted = st.form_submit_button("Create account")
        if submitted:
            user, error = auth.register(name, email, password, confirm)
            if error:
                st.error(error)
            else:
                message_for_next_run("Welcome aboard! Your Sales Executive workspace is ready.")
                sign_in(user)


def sign_in(user):
    st.session_state["user_id"] = user["id"]
    go_to("dashboard")
    st.rerun()
