"""Team performance (Admin and Manager): one row per sales executive."""

import pandas as pd
import streamlit as st

from logic.dashboard_numbers import team_performance
from logic.settings import rupees, win_rate
from screens.helpers import period_filter, show_table


def show(user):
    st.title("Team performance")
    period = period_filter("team_period")
    if period is None:
        return
    from_date, to_date_, period_label = period
    st.caption(f"Period: {period_label}")

    team = team_performance(user, from_date, to_date_)
    show_table(team, {
        "Sales executive": "name",
        "Leads": "leads",
        "Converted": "converted",
        "Open deals": "open_deals",
        "Open pipeline": lambda row: rupees(row["open_pipeline"]),
        "Weighted pipeline": lambda row: rupees(row["weighted_pipeline"]),
        "Won deals": "won_deals",
        "Won value": lambda row: rupees(row["won_value"]),
        "Win rate": lambda row: win_rate(row["won_deals"], row["lost_deals"]),
        "Activities": "activities",
        "Overdue follow-ups": "overdue_followups",
    }, "No team members yet.")

    if team:
        st.subheader("Open pipeline vs won value")
        chart = pd.DataFrame(team).set_index("name")[["open_pipeline", "won_value"]]
        chart.columns = ["Open pipeline", "Won value"]
        st.bar_chart(chart)
