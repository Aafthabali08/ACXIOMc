"""Reports with filters and CSV download."""

import pandas as pd
import streamlit as st

from logic import reports
from logic.records import get_assignable_users, is_sales_executive
from logic.database import fetch_all


def show(user, report_name=None):
    st.title("Reports")
    allowed = reports.reports_for(user)
    names = list(allowed)
    default = names.index(report_name) if report_name in names else 0
    report_name = st.selectbox("Report", names, index=default, format_func=allowed.get)

    columns = st.columns(4)
    search = columns[0].text_input("Search")
    owner_id = None
    if not is_sales_executive(user):
        # Audit reports can filter by any user. Record reports by sales executive.
        if report_name in ("audit", "user-activity"):
            people = fetch_all("SELECT id, name FROM users ORDER BY name")
        else:
            people = get_assignable_users(user)
        names_by_id = {person["id"]: person["name"] for person in people}
        owner_id = columns[1].selectbox("User / owner", [None] + list(names_by_id),
                                        format_func=lambda value: names_by_id.get(value, "Everyone"))
    from_date = columns[2].date_input("From date", value=None)
    to_date_ = columns[3].date_input("To date", value=None)
    sort = st.radio("Sort", ["newest", "oldest", "name"], horizontal=True)

    if from_date and to_date_ and from_date > to_date_:
        st.error("From date cannot be after To date.")
        return

    headings, rows = reports.build_report(report_name, user, search=search, owner_id=owner_id,
                                          from_date=from_date, to_date_=to_date_, sort=sort)
    st.subheader(allowed[report_name])
    if rows:
        st.dataframe(pd.DataFrame(rows, columns=headings), hide_index=True, use_container_width=True)
    else:
        st.info("No data for these filters.")

    st.download_button("Download CSV", reports.to_csv(headings, rows),
                       file_name=f"{report_name}-report.csv", mime="text/csv")
