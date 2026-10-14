"""
Dashboard. One page, three versions:
- Admin: system access numbers, company numbers, audit events, users, team table
- Manager: team numbers, team table, overdue follow-ups, deals closing soon
- Sales Executive: my numbers, today's agenda with "Mark done", my pipeline
"""

import pandas as pd
import streamlit as st

from logic import records
from logic.dashboard_numbers import build_dashboard
from logic.settings import ADMIN, MANAGER, STAGES, nice_date, role_title, rupees, today_in_india, to_date, win_rate
from screens.helpers import message_for_next_run, period_filter, show_table


def show(user):
    first_name = user["name"].split()[0]
    st.title(f"{role_title(user['role'])} dashboard")
    st.write(f"Hello {first_name}. Today is {today_in_india().strftime('%A, %d %B %Y')}.")

    period = period_filter("dashboard_period")
    if period is None:
        return
    from_date, to_date_, period_label = period
    data = build_dashboard(user, from_date, to_date_)
    st.caption(f"Numbers below are for: {period_label}. Follow-ups and deals closing soon always show current work.")

    if user["role"] == ADMIN:
        admin_section(data)
    scope = "My" if user["role"] not in (ADMIN, MANAGER) else ("Team" if user["role"] == MANAGER else "Company")

    st.subheader(f"{scope} numbers")
    row1 = st.columns(4)
    row1[0].metric("Customers", len(data["customers"]))
    row1[1].metric("Open leads", data["open_leads"])
    row1[2].metric("Open deals", len(data["open_deals"]))
    row1[3].metric("Win rate", win_rate(data["won_count"], data["lost_count"]))
    row2 = st.columns(4)
    row2[0].metric("Open pipeline", rupees(data["open_pipeline"]))
    row2[1].metric("Weighted pipeline", rupees(data["weighted_pipeline"]))
    row2[2].metric("Won value", rupees(data["won_value"]))
    row2[3].metric("Overdue follow-ups", len(data["overdue_followups"]))

    if user["role"] in (ADMIN, MANAGER):
        team_section(data)
        st.subheader("Overdue follow-ups")
        followup_list(user, data["overdue_followups"], "No overdue follow-ups.")
    else:
        st.subheader("Today's agenda")
        followup_list(user, data["overdue_followups"] + data["today_followups"], "Nothing due today.")

        st.subheader("My lead status")
        lead_counts = {}
        for lead in data["leads"]:
            lead_counts[lead["status"]] = lead_counts.get(lead["status"], 0) + 1
        if lead_counts:
            st.bar_chart(pd.DataFrame({"Leads": lead_counts}))
        else:
            st.info("No leads in this period.")

    st.subheader("Pipeline by stage")
    stage_totals = {stage: sum(row["amount"] for row in data["opportunities"] if row["stage"] == stage) for stage in STAGES}
    st.bar_chart(pd.DataFrame({"Amount": stage_totals}))

    st.subheader("Deals closing in the next 30 days")
    show_table(data["closing_soon"], {
        "Opportunity": "name", "Customer": "related_to", "Stage": "stage",
        "Amount": lambda row: rupees(row["amount"]), "Close date": lambda row: nice_date(row["close_date"]),
        "Owner": "owner",
    }, "No open deals closing in the next 30 days.")

    st.subheader("Won sales - last six months")
    st.bar_chart(pd.DataFrame(data["monthly_sales"]).set_index("Month"))

    st.subheader("Recent activities")
    show_table(data["recent_activities"], {
        "Activity": "name", "Type": "type", "Date": lambda row: nice_date(row["due_date"]),
        "Status": "status", "Related to": "related_to", "Owner": "owner",
    }, "No activities yet.")


def admin_section(data):
    st.subheader("System access")
    columns = st.columns(4)
    columns[0].metric("Users", data["total_users"])
    columns[1].metric("Active users", data["active_users"])
    columns[2].metric("Locked accounts", data["locked_users"])
    columns[3].metric("Failed sign-ins (24h)", data["failed_logins_24h"])

    left, right = st.columns(2)
    with left:
        st.write("**Users by role**")
        st.bar_chart(pd.DataFrame({"Users": {role_title(role): count for role, count in data["users_per_role"].items()}}))
    with right:
        st.write("**Newest users**")
        show_table(data["recent_users"], {
            "Name": "name", "Email": "email", "Role": lambda row: role_title(row["role"]),
            "Active": lambda row: "Yes" if row["active"] else "No",
        })

    st.write("**Latest audit events**")
    show_table(data["recent_audit"], {
        "Time (UTC)": "created_at", "User": lambda row: row["user_name"] or "Unknown",
        "Action": "action", "Module": "entity", "Result": "result",
    })


def team_section(data):
    st.subheader("Team performance")
    show_table(data["team"], {
        "Sales executive": "name", "Leads": "leads", "Converted": "converted", "Open deals": "open_deals",
        "Open pipeline": lambda row: rupees(row["open_pipeline"]),
        "Won value": lambda row: rupees(row["won_value"]),
        "Win rate": lambda row: win_rate(row["won_deals"], row["lost_deals"]),
        "Overdue follow-ups": "overdue_followups",
    }, "No team members yet.")
    if data["team"]:
        chart = pd.DataFrame(data["team"]).set_index("name")[["open_pipeline", "won_value"]]
        chart.columns = ["Open pipeline", "Won value"]
        st.bar_chart(chart)


def followup_list(user, followups, empty_text):
    """List of follow-ups, each with a 'Mark done' button."""
    if not followups:
        st.info(empty_text)
        return
    today = today_in_india()
    for followup in followups:
        due = to_date(followup["due_date"])
        when = "Today" if due == today else f"Overdue since {nice_date(due)}"
        text_column, button_column = st.columns([5, 1])
        text_column.write(f"**{followup['name']}** - {followup['type']} with {followup['related_to']} "
                          f"({when}, {followup['owner']})")
        if button_column.button("Mark done", key=f"done_{followup['id']}"):
            records.mark_done("followups", followup["id"], user)
            message_for_next_run("Marked as done.")
            st.rerun()
