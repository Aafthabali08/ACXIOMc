"""
One screen for all five CRM modules (customers, leads, opportunities, follow-ups, activities).

It has four views, stored in st.session_state["record_mode"]:
- list:    filters + table
- details: one record with its linked records and history
- new:     empty form
- edit:    form filled with the record
"""

from datetime import timedelta

import streamlit as st

from logic import records
from logic.audit import get_record_history
from logic.records import CrmError
from logic.settings import (
    ACTIVITY_TYPES, MODULES, NEXT_LEAD_STATUSES, PRIORITIES, STAGES, STATUSES,
    nice_date, rupees, today_in_india, to_date,
)
from screens.helpers import go_to, message_for_next_run, open_record, record_picker, show_table

ADD_BUTTON_TEXT = {
    "customers": "Add customer",
    "leads": "Add lead",
    "opportunities": "Add opportunity",
    "followups": "Schedule follow-up",
    "activities": "Log activity",
}

PAGE_SIZE = 10


def show(user, module):
    mode = st.session_state.get("record_mode", "list")
    record_id = st.session_state.get("record_id")

    try:
        if mode == "details":
            details_view(user, module, record_id)
        elif mode == "edit":
            form_view(user, module, records.find_record(module, record_id, user))
        elif mode == "new":
            form_view(user, module, None)
        else:
            list_view(user, module)
    except CrmError as error:
        st.error(str(error))
        if st.button("Back to list"):
            go_to("records", module)
            st.rerun()


# ---------- List ----------

def list_view(user, module):
    title = MODULES[module]
    is_sales_executive = records.is_sales_executive(user)
    st.title(("My " + title.lower()) if is_sales_executive else title)

    if st.button(ADD_BUTTON_TEXT[module]):
        go_to("records", module, record_mode="new")
        st.rerun()

    # Filters
    with st.expander("Search and filters", expanded=True):
        search = st.text_input("Search", placeholder="Name, company, email, phone or owner", key=f"{module}_search")
        columns = st.columns(4)
        statuses = STATUSES[module] + (["Overdue"] if module == "followups" else [])
        status = columns[0].selectbox("Status", [""] + statuses, format_func=lambda value: value or "All statuses",
                                      key=f"{module}_status")
        owner_id = None
        if not is_sales_executive:
            owners = records.get_assignable_users(user)
            owner_names = {owner["id"]: owner["name"] for owner in owners}
            owner_id = columns[1].selectbox("Owner", [None] + list(owner_names),
                                            format_func=lambda value: owner_names.get(value, "All owners"),
                                            key=f"{module}_owner")
        stage = activity_type = ""
        if module == "opportunities":
            stage = columns[2].selectbox("Stage", [""] + STAGES, format_func=lambda value: value or "All stages",
                                         key=f"{module}_stage")
        if module in ("followups", "activities"):
            activity_type = columns[2].selectbox("Type", [""] + ACTIVITY_TYPES,
                                                 format_func=lambda value: value or "All types", key=f"{module}_type")
        sort_options = ["newest", "oldest", "name"]
        if module == "opportunities":
            sort_options += ["amount", "date"]
        if module in ("followups", "activities"):
            sort_options += ["date"]
        sort = columns[3].selectbox("Sort by", sort_options, key=f"{module}_sort")

        date_columns = st.columns(2)
        from_date = date_columns[0].date_input("From date", value=None, key=f"{module}_from")
        to_date_ = date_columns[1].date_input("To date", value=None, key=f"{module}_to")

    if from_date and to_date_ and from_date > to_date_:
        st.error("From date cannot be after To date.")
        return

    rows = records.get_records(module, user, search=search, status=status, owner_id=owner_id, stage=stage,
                               activity_type=activity_type, from_date=from_date, to_date_=to_date_, sort=sort)
    st.write(f"{len(rows)} record(s)" + (" assigned to you." if is_sales_executive else " across the team."))

    # Simple paging: 10 rows per page.
    page_count = max(1, (len(rows) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = st.number_input("Page", min_value=1, max_value=page_count, value=1, key=f"{module}_page") if page_count > 1 else 1
    page_rows = rows[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]

    show_table(page_rows, list_columns(module), "No records found.")
    record_picker(page_rows, key=f"{module}_picker")


def list_columns(module):
    if module == "customers":
        return {"Code": "code", "Name": "name", "Company": "company", "Email": "email", "Phone": "phone",
                "City": "city", "Status": "status", "Owner": "owner"}
    if module == "leads":
        return {"Code": "code", "Name": "name", "Company": "company", "Source": "source", "Priority": "priority",
                "Expected value": lambda row: rupees(row["expected_value"]), "Status": "status", "Owner": "owner"}
    if module == "opportunities":
        return {"Opportunity": "name", "Customer": "related_to", "Stage": "stage",
                "Amount": lambda row: rupees(row["amount"]), "Probability": lambda row: f"{row['probability']}%",
                "Close date": lambda row: nice_date(row["close_date"]), "Status": "status", "Owner": "owner"}
    if module == "followups":
        return {"Subject": "name", "Type": "type", "Date": lambda row: nice_date(row["due_date"]),
                "Status": lambda row: "Overdue" if row["is_overdue"] else row["status"],
                "Related to": "related_to", "Owner": "owner"}
    return {"Activity": "name", "Type": "type", "Date": lambda row: nice_date(row["due_date"]),
            "Status": "status", "Related to": "related_to", "Owner": "owner"}


# ---------- Details ----------

def details_view(user, module, record_id):
    record = records.find_record(module, record_id, user)

    if st.button("← Back to list"):
        go_to("records", module)
        st.rerun()

    st.title(record["name"])
    st.caption(f"{MODULES[module]} · Status: {record['status']} · Assigned to {record['owner']}")

    # Fields
    fields = detail_fields(module, record)
    left, right = st.columns(2)
    for index, (label, value) in enumerate(fields.items()):
        (left if index % 2 == 0 else right).write(f"**{label}:** {value if value not in (None, '') else '-'}")
    if record["notes"]:
        st.write(f"**Notes:** {record['notes']}")

    action_buttons(user, module, record)

    # Linked records
    followups, activities, opportunities = records.get_linked_records(module, record_id, user)
    if module in ("customers", "leads"):
        st.subheader("Opportunities")
        show_table(opportunities, list_columns("opportunities"), "No opportunities.")
        record_picker(opportunities, key="linked_opportunity")
    if module in ("customers", "leads", "opportunities"):
        st.subheader("Follow-ups")
        show_table(followups, list_columns("followups"), "No follow-ups.")
        record_picker(followups, key="linked_followup")
    if module in ("customers", "leads"):
        st.subheader("Activities")
        show_table(activities, list_columns("activities"), "No activities.")
        record_picker(activities, key="linked_activity")

    st.subheader("History")
    show_table(get_record_history(module, record_id), {
        "Time (UTC)": "created_at", "User": lambda row: row["user_name"] or "Unknown",
        "Action": "action", "Old value": "old_value", "New value": "new_value",
    }, "No history yet.")


def detail_fields(module, record):
    created = nice_date(record["created_at"])
    if module == "customers":
        return {"Code": record["code"], "Company": record["company"], "Email": record["email"], "Phone": record["phone"],
                "Address": record["address"], "City": record["city"], "State": record["state"], "Created": created}
    if module == "leads":
        return {"Code": record["code"], "Company": record["company"], "Email": record["email"], "Phone": record["phone"],
                "Source": record["source"], "Priority": record["priority"],
                "Expected value": rupees(record["expected_value"]), "Converted to customer": record["related_to"],
                "Created": created}
    if module == "opportunities":
        return {"Customer": record["related_to"], "Stage": record["stage"], "Amount": rupees(record["amount"]),
                "Probability": f"{record['probability']}%", "Weighted value": rupees(record["weighted_amount"]),
                "Expected close date": nice_date(record["close_date"]),
                "Won/lost on": nice_date(record["outcome_date"]), "Source": record["source"], "Created": created}
    return {"Type": record["type"], "Date": nice_date(record["due_date"]), "Related to": record["related_to"],
            "Created": created}


def action_buttons(user, module, record):
    buttons = st.columns(4)

    # Converted leads are read-only.
    if not (module == "leads" and record["status"] == "Converted"):
        if buttons[0].button("Edit"):
            go_to("records", module, record_mode="edit", record_id=record["id"])
            st.rerun()

    if module == "leads" and record["status"] == "Qualified":
        if buttons[1].button("Convert lead"):
            run_action(lambda: records.convert_lead(record["id"], user),
                       "Lead converted. An opportunity is also created when the expected value is above zero.",
                       go_to_customer=True)

    open_status = {"followups": "Planned", "activities": "Pending"}.get(module)
    if open_status and record["status"] == open_status:
        if buttons[1].button("Mark done"):
            run_action(lambda: records.mark_done(module, record["id"], user), "Marked as done.")

    link_column = {"customers": "customer_id", "leads": "lead_id", "opportunities": "opportunity_id"}.get(module)
    if link_column and not (module == "leads" and record["status"] == "Converted"):
        preset = {link_column: record["id"], "owner_id": record["owner_id"]}
        if buttons[2].button("Schedule follow-up"):
            go_to("records", "followups", record_mode="new", preset=preset)
            st.rerun()
        if module != "opportunities" and buttons[3].button("Log activity"):
            go_to("records", "activities", record_mode="new", preset=preset)
            st.rerun()

    # Delete sits on its own line and needs a tick first, so it is not clicked by accident.
    st.write("")
    confirmed = st.checkbox("Tick to confirm delete (the record is hidden but kept in the history)")
    if st.button("Delete", disabled=not confirmed):
        try:
            records.delete_record(module, record["id"], user)
            message_for_next_run("Record deleted.")
            go_to("records", module)
        except CrmError as error:
            message_for_next_run(str(error), "error")
        st.rerun()


def run_action(action, success_text, go_to_customer=False):
    try:
        result = action()
        message_for_next_run(success_text)
        if go_to_customer:
            open_record("customers", result)
    except CrmError as error:
        message_for_next_run(str(error), "error")
    st.rerun()


# ---------- Add / edit form ----------

def form_view(user, module, record):
    is_new = record is None
    if module == "leads" and record and record["status"] == "Converted":
        st.error("Converted leads are read-only. Open the linked customer to continue.")
        return

    preset = st.session_state.get("record_preset") or {}
    values = dict(record or {})
    for key, value in preset.items():
        values.setdefault(key, value)

    if st.button("← Cancel"):
        if is_new:
            go_to("records", module)
        else:
            go_to("records", module, record_mode="details", record_id=record["id"])
        st.rerun()

    st.title(ADD_BUTTON_TEXT[module] if is_new else f"Edit {values['name']}")

    owners = records.get_assignable_users(user)
    owner_names = {owner["id"]: owner["name"] for owner in owners}
    if not owner_names:
        st.warning("There is no active Sales Executive to assign records to. Ask an admin to add one.")
        return
    customers = {row["id"]: row["name"] for row in records.get_records("customers", user, sort="name")}
    leads = {row["id"]: row["name"] for row in records.get_records("leads", user, sort="name")}
    opportunities = {row["id"]: row["name"] for row in records.get_records("opportunities", user, sort="name")}
    today = today_in_india()

    with st.form("record_form"):
        form = {"name": st.text_input("Name" if module in ("customers", "leads") else "Title / subject",
                                      value=values.get("name", ""), max_chars=120)}

        if module in ("customers", "leads"):
            columns = st.columns(2)
            form["email"] = columns[0].text_input("Email", value=values.get("email") or "")
            form["phone"] = columns[1].text_input("Phone (10-digit mobile)", value=values.get("phone") or "", max_chars=10)
            form["company"] = st.text_input("Company", value=values.get("company") or "")

        if module == "customers":
            form["address"] = st.text_input("Address", value=values.get("address") or "")
            columns = st.columns(2)
            form["city"] = columns[0].text_input("City", value=values.get("city") or "")
            form["state"] = columns[1].text_input("State", value=values.get("state") or "")
            form["status"] = st.selectbox("Status", STATUSES["customers"],
                                          index=STATUSES["customers"].index(values.get("status", "Active")))

        if module == "leads":
            columns = st.columns(3)
            form["source"] = columns[0].text_input("Source", value=values.get("source") or "",
                                                   placeholder="Website, Referral ...")
            form["priority"] = columns[1].selectbox("Priority", PRIORITIES,
                                                    index=PRIORITIES.index(values.get("priority") or "Normal"))
            form["expected_value"] = columns[2].number_input("Expected value (₹)", min_value=0.0, step=1000.0,
                                                             value=float(values.get("expected_value") or 0))
            if is_new:
                st.write("Status: **New** (every new lead starts as New)")
                form["status"] = "New"
            else:
                choices = [values["status"]] + NEXT_LEAD_STATUSES.get(values["status"], [])
                form["status"] = st.selectbox("Status", choices,
                                              help="New → Contacted → Qualified. Use the Convert button for qualified leads.")

        if module == "opportunities":
            form["customer_id"] = pick("Customer", customers, values.get("customer_id"))
            form["lead_id"] = pick("From lead (optional)", leads, values.get("lead_id"))
            columns = st.columns(3)
            form["stage"] = columns[0].selectbox("Stage", STAGES, index=STAGES.index(values.get("stage") or "Qualification"))
            form["amount"] = columns[1].number_input("Amount (₹)", min_value=0.0, step=1000.0,
                                                     value=float(values.get("amount") or 0))
            form["probability"] = columns[2].number_input("Probability (%)", min_value=0, max_value=100, step=5,
                                                          value=int(values.get("probability") or 0))
            form["close_date"] = st.date_input("Expected close date",
                                               value=to_date(values.get("close_date")) or today + timedelta(days=30))
            form["source"] = st.text_input("Source", value=values.get("source") or "")
            st.caption("Won needs 100% probability, Lost needs 0%. Status follows the stage.")

        if module in ("followups", "activities"):
            columns = st.columns(3)
            form["type"] = columns[0].selectbox("Type", ACTIVITY_TYPES, index=ACTIVITY_TYPES.index(values.get("type") or "Call"))
            form["due_date"] = columns[1].date_input("Date", value=to_date(values.get("due_date")) or today)
            statuses = STATUSES[module]
            form["status"] = columns[2].selectbox("Status", statuses,
                                                  index=statuses.index(values.get("status") or statuses[0]))
            st.write("**Related to** (pick exactly one)")
            form["customer_id"] = pick("Customer", customers, values.get("customer_id"))
            form["lead_id"] = pick("Lead", leads, values.get("lead_id"))
            if module == "followups":
                form["opportunity_id"] = pick("Opportunity", opportunities, values.get("opportunity_id"))

        owner_ids = list(owner_names)
        current_owner = values.get("owner_id") if values.get("owner_id") in owner_ids else owner_ids[0]
        form["owner_id"] = st.selectbox("Assigned to", owner_ids, index=owner_ids.index(current_owner),
                                        format_func=owner_names.get)
        form["notes"] = st.text_area("Notes", value=values.get("notes") or "", max_chars=2000)

        submitted = st.form_submit_button("Save")

    if submitted:
        if module == "opportunities":
            form["status"] = form["stage"] if form["stage"] in ("Won", "Lost") else "Open"
        try:
            saved_id = records.save_record(module, form, user, None if is_new else record["id"])
            message_for_next_run("Record saved.")
            open_record(module, saved_id)
            st.rerun()
        except CrmError as error:
            st.error(str(error))


def pick(label, options, current_id):
    """Dropdown of related records with a '- none -' choice. Returns the chosen id or None."""
    ids = [None] + list(options)
    index = ids.index(current_id) if current_id in ids else 0
    return st.selectbox(label, ids, index=index, format_func=lambda value: options.get(value, "- none -"))
