"""
AcxiomCRM - Streamlit version.

Run it with:   streamlit run app.py

How this file works:
1. Create the database tables (and demo data the first time).
2. If nobody is logged in, show the login page.
3. Otherwise show the sidebar menu for the user's role and the chosen page.
"""

import streamlit as st

from logic import auth, records
from logic.database import create_tables
from logic.sample_data import create_sample_data_if_empty
from logic.settings import ADMIN, MANAGER, role_title
from screens import (
    dashboard_page, login_page, profile_page, records_page, reports_page,
    search_page, team_page, users_page,
)
from screens.helpers import go_to, show_saved_message

st.set_page_config(page_title="AcxiomCRM", layout="wide")

# The only styling in the app: hide Streamlit's coloured line at the top of the page.
st.markdown("<style>[data-testid='stDecoration'] {display: none;}</style>", unsafe_allow_html=True)


# ---------- Menus ----------
# Each menu section is (section title, [(link text, page name, option), ...]).
# Hiding a link is only for convenience; every page also checks the role itself.

ADMIN_MENU = [
    ("Control Centre", [("Admin dashboard", "dashboard", None), ("Team performance", "team", None),
                        ("Search", "search", None)]),
    ("User Administration", [("Users & access", "users", None), ("Add new user", "users", "new"),
                             ("Roles & permissions", "users", "roles")]),
    ("Security & Compliance", [("Audit log", "reports", "audit"), ("User activity", "reports", "user-activity")]),
    ("Business Records", [("Customers", "records", "customers"), ("Leads", "records", "leads"),
                          ("Opportunities", "records", "opportunities"), ("Follow-ups", "records", "followups"),
                          ("Activities", "records", "activities")]),
    ("Insights", [("Sales reports", "reports", "pipeline")]),
    ("Account", [("My profile", "profile", None)]),
]

MANAGER_MENU = [
    ("Overview", [("Manager dashboard", "dashboard", None), ("Search", "search", None)]),
    ("Team Management", [("Team performance", "team", None), ("Team activity", "reports", "user-activity")]),
    ("Sales Pipeline", [("Leads", "records", "leads"), ("Opportunities", "records", "opportunities"),
                        ("Pipeline report", "reports", "pipeline")]),
    ("Customer Relations", [("Customers", "records", "customers"), ("Follow-ups", "records", "followups"),
                            ("Activities", "records", "activities")]),
    ("Account", [("My profile", "profile", None)]),
]

SALES_EXECUTIVE_MENU = [
    ("My Workspace", [("My dashboard", "dashboard", None), ("My follow-ups", "records", "followups"),
                      ("My activities", "records", "activities"), ("Search", "search", None)]),
    ("My Sales", [("My leads", "records", "leads"), ("My opportunities", "records", "opportunities"),
                  ("My customers", "records", "customers")]),
    ("My Insights", [("My reports", "reports", "pipeline")]),
    ("Account", [("My profile", "profile", None)]),
]


def menu_for(role):
    if role == ADMIN:
        return ADMIN_MENU
    if role == MANAGER:
        return MANAGER_MENU
    return SALES_EXECUTIVE_MENU


def show_sidebar(user):
    st.sidebar.title("AcxiomCRM")
    st.sidebar.write(f"**{user['name']}**  \n{role_title(user['role'])}")

    due = records.count_due_followups(user)
    if due:
        st.sidebar.warning(f"{due} follow-up(s) due today or overdue")

    current_page = st.session_state.get("page", ("dashboard", None))
    for section_title, links in menu_for(user["role"]):
        st.sidebar.subheader(section_title)
        for link_text, page_name, option in links:
            is_current = current_page == (page_name, option)
            # on_click runs go_to() before the page is drawn again, so no st.rerun() is needed.
            st.sidebar.button(link_text, key=f"menu_{link_text}", use_container_width=True,
                              type="primary" if is_current else "secondary",
                              on_click=go_to, args=(page_name, option))

    st.sidebar.divider()
    if st.sidebar.button("Log out", use_container_width=True):
        auth.logout(user["id"])
        st.session_state.clear()
        st.rerun()


def show_page(user):
    page_name, option = st.session_state.get("page", ("dashboard", None))
    role = user["role"]

    if page_name == "records":
        records_page.show(user, option)
    elif page_name == "reports":
        reports_page.show(user, option)
    elif page_name == "team" and role in (ADMIN, MANAGER):
        team_page.show(user)
    elif page_name == "users" and role == ADMIN:
        users_page.show(user, option)
    elif page_name == "search":
        search_page.show(user)
    elif page_name == "profile":
        profile_page.show(user)
    elif page_name == "dashboard":
        dashboard_page.show(user)
    else:
        st.error("You do not have access to this page.")


@st.cache_resource
def prepare_database():
    """Runs once when the server starts (not on every click). Streamlit makes other
    browser tabs wait until it is done, so the demo data is never created twice.
    If you delete crm_data.db, restart the app so this runs again."""
    create_tables()
    create_sample_data_if_empty()


def main():
    prepare_database()
    show_saved_message()

    # Load the user fresh from the database on every run, so a deactivated
    # user or a role change takes effect straight away.
    user = auth.get_user(st.session_state["user_id"]) if "user_id" in st.session_state else None
    if user is None or not user["active"]:
        st.session_state.pop("user_id", None)
        login_page.show()
        return

    show_sidebar(user)
    show_page(user)


main()
