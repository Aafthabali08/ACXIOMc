"""
Small helpers shared by all screens: page switching, messages and tables.
"""

import altair as alt
import pandas as pd
import streamlit as st

from logic.dashboard_numbers import PERIODS, period_dates


# ---------- Moving between pages ----------
# The current page is stored in st.session_state["page"] as (page_name, option),
# for example ("records", "leads") or ("reports", "audit").

def go_to(page_name, option=None, record_mode="list", record_id=None, preset=None):
    st.session_state["page"] = (page_name, option)
    st.session_state["record_mode"] = record_mode   # list / details / edit / new
    st.session_state["record_id"] = record_id
    st.session_state["record_preset"] = preset or {}


def open_record(module, record_id):
    go_to("records", module, record_mode="details", record_id=record_id)


# ---------- Messages ----------
# st.success() disappears when the page reruns, so after an action we save
# the message and show it at the top of the next run.

def message_for_next_run(text, kind="success"):
    st.session_state["message"] = (kind, text)


def show_saved_message():
    if "message" in st.session_state:
        kind, text = st.session_state.pop("message")
        if kind == "success":
            st.success(text)
        else:
            st.error(text)


# ---------- Tables ----------

def show_table(rows, columns, empty_text="Nothing to show."):
    """columns = {"Heading": "key"} or {"Heading": function(row)}"""
    if not rows:
        st.info(empty_text)
        return
    data = []
    for row in rows:
        line = {}
        for heading, source in columns.items():
            line[heading] = source(row) if callable(source) else row.get(source, "")
        data.append(line)
    st.dataframe(pd.DataFrame(data), hide_index=True, use_container_width=True)


def record_picker(rows, label="Open a record", key="open_picker"):
    """A dropdown + button to open one record from a list (st.dataframe rows are not clickable)."""
    if not rows:
        return
    options = {f"{row['name']} (#{row['id']})": row for row in rows}
    left, right = st.columns([4, 1])
    choice = left.selectbox(label, list(options), key=key)
    right.write("")
    right.write("")
    if right.button("Open", key=key + "_button"):
        row = options[choice]
        open_record(row["module"], row["id"])
        st.rerun()


# ---------- Charts ----------

def bar_chart(labels, series):
    """Bar chart with horizontal labels, in the order given.
    labels = ["Jan", "Feb"], series = {"Won sales": [100, 200]}.
    With more than one series the bars stand side by side, with a legend on the right."""
    rows = [{"Label": label, "Series": name, "Value": values[index]}
            for name, values in series.items() for index, label in enumerate(labels)]
    chart = alt.Chart(pd.DataFrame(rows)).mark_bar().encode(
        x=alt.X("Label:N", sort=None, title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("Value:Q", title=None),
        tooltip=["Label", "Series", "Value"],
    )
    if len(series) > 1:
        # Keep the legend in its default place (right). In Streamlit 1.32 a legend
        # at the top or bottom hides the numbers on the left axis.
        chart = chart.encode(xOffset="Series:N", color=alt.Color("Series:N", title=None))
    st.altair_chart(chart, use_container_width=True)


# ---------- Period filter (dashboard and team page) ----------

def period_filter(key):
    """Shows the period dropdown. Returns (from_date, to_date, label) or None when the custom range is wrong."""
    columns = st.columns(3)
    period = columns[0].selectbox("Period", list(PERIODS), format_func=PERIODS.get, key=key)
    custom_from = custom_to = None
    if period == "custom":
        custom_from = columns[1].date_input("From", value=None, key=key + "_from")
        custom_to = columns[2].date_input("To", value=None, key=key + "_to")
        if not custom_from or not custom_to:
            st.warning("Select both dates for a custom range.")
            return None
        if custom_from > custom_to:
            st.error("From date cannot be after To date.")
            return None
    from_date, to_date_ = period_dates(period, custom_from, custom_to)
    return from_date, to_date_, PERIODS[period]
