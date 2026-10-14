"""Search across all five CRM modules. Sales Executives only find their own records."""

import streamlit as st

from logic.records import get_records
from logic.settings import MODULES
from screens.helpers import record_picker, show_table


def show(user):
    st.title("Search")
    text = st.text_input("Search all records", placeholder="At least 2 characters")
    if len(text.strip()) < 2:
        return

    found_anything = False
    for module, title in MODULES.items():
        rows = get_records(module, user, search=text, sort="name")
        if not rows:
            continue
        found_anything = True
        st.subheader(f"{title} ({len(rows)})")
        show_table(rows, {"Name": "name", "Status": "status", "Related to": "related_to",
                          "Email": "email", "Owner": "owner"})
        record_picker(rows, key=f"search_{module}")

    if not found_anything:
        st.info("No records match your search.")
