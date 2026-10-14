"""
All CRM reading and saving goes through this file:
customers, leads, opportunities, follow-ups and activities.

Main rules:
- A Sales Executive only sees records assigned to them.
- Managers and Admins see everything.
- Deletes are "soft" (deleted = 1), so the history is kept.
- Every change is written to the audit log.
"""

import re
from datetime import timedelta

from logic.audit import add_audit_entry
from logic.database import fetch_all, fetch_one, insert, update
from logic.settings import (
    ACTIVITY_TYPES, MODULES, NEXT_LEAD_STATUSES, PRIORITIES, SALES_EXECUTIVE, STAGES, STATUSES,
    now_utc, to_date, today_in_india, utc_text_to_india_date,
)

PHONE_PATTERN = re.compile(r"^[6-9]\d{9}$")   # 10-digit Indian mobile number
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Columns that belong to each module (besides the common name/status/owner/notes).
MODULE_COLUMNS = {
    "customers": ["email", "phone", "company", "address", "city", "state"],
    "leads": ["email", "phone", "company", "source", "priority", "expected_value"],
    "opportunities": ["customer_id", "lead_id", "stage", "amount", "probability", "close_date", "source"],
    "followups": ["customer_id", "lead_id", "opportunity_id", "due_date", "type"],
    "activities": ["customer_id", "lead_id", "due_date", "type"],
}


# Which tables point to a record, and through which column.
LINKS = {
    "customers": [("leads", "customer_id"), ("opportunities", "customer_id"),
                  ("followups", "customer_id"), ("activities", "customer_id")],
    "leads": [("opportunities", "lead_id"), ("followups", "lead_id"), ("activities", "lead_id")],
    "opportunities": [("followups", "opportunity_id")],
}


class CrmError(Exception):
    """Raised when a business rule fails. The screen shows the message to the user."""


def is_sales_executive(user):
    return user["role"] == SALES_EXECUTIVE


def check_module(module):
    if module not in MODULES:
        raise CrmError("Page not found.")


# ---------- Reading ----------

def load_records(module, user):
    """All non-deleted rows of a module that this user may see,
    with the owner's name and the related record's name added."""
    check_module(module)
    sql = f"SELECT * FROM {module} WHERE deleted = 0"
    params = []
    if is_sales_executive(user):
        sql += " AND owner_id = ?"
        params.append(user["id"])
    rows = fetch_all(sql, params)

    user_names = {row["id"]: row["name"] for row in fetch_all("SELECT id, name FROM users")}
    customer_names = {row["id"]: row["name"] for row in fetch_all("SELECT id, name FROM customers")}
    lead_names = {row["id"]: row["name"] for row in fetch_all("SELECT id, name FROM leads")}
    opportunity_names = {row["id"]: row["name"] for row in fetch_all("SELECT id, name FROM opportunities")}
    today = today_in_india()

    for row in rows:
        row["module"] = module
        row["owner"] = user_names.get(row["owner_id"], "")
        # "Related to": the customer / lead / opportunity this record belongs to.
        # For a lead it is the customer the lead was converted into.
        row["related_to"] = (
            customer_names.get(row.get("customer_id"))
            or lead_names.get(row.get("lead_id"))
            or opportunity_names.get(row.get("opportunity_id"))
            or ""
        )
        if module == "opportunities":
            row["weighted_amount"] = row["amount"] * row["probability"] / 100
        if module == "followups":
            row["is_overdue"] = row["status"] == "Planned" and to_date(row["due_date"]) < today
    return rows


def filter_records(rows, search="", status="", owner_id=None, activity_type="", stage="",
                   from_date=None, to_date_=None, sort="newest"):
    """Applies the filters from the list screen. Every filter is optional."""
    today = today_in_india()

    if search:
        text = search.strip().lower()
        searchable = ["name", "email", "phone", "company", "related_to", "code", "owner", "status"]
        rows = [row for row in rows if text in " ".join(str(row.get(key) or "") for key in searchable).lower()]

    # "Overdue" is not stored in the database: it means Planned with a date in the past.
    if status == "Overdue":
        rows = [row for row in rows if row["status"] == "Planned" and to_date(row["due_date"]) < today]
    elif status:
        rows = [row for row in rows if row["status"] == status]

    if owner_id:
        rows = [row for row in rows if row["owner_id"] == owner_id]
    if activity_type:
        rows = [row for row in rows if row.get("type") == activity_type]
    if stage:
        rows = [row for row in rows if row.get("stage") == stage]

    # Follow-ups and activities use their own date. Other modules use the created date.
    def record_date(row):
        return to_date(row.get("due_date")) or utc_text_to_india_date(row["created_at"])

    if from_date:
        rows = [row for row in rows if record_date(row) >= from_date]
    if to_date_:
        rows = [row for row in rows if record_date(row) <= to_date_]

    if sort == "name":
        rows.sort(key=lambda row: row["name"].lower())
    elif sort == "oldest":
        rows.sort(key=lambda row: (row["created_at"], row["id"]))
    elif sort == "amount":
        rows.sort(key=lambda row: row.get("amount") or 0, reverse=True)
    elif sort == "date":
        rows.sort(key=lambda row: row.get("due_date") or row.get("close_date") or "")
    else:
        rows.sort(key=lambda row: (row["created_at"], row["id"]), reverse=True)
    return rows


def get_records(module, user, **filters):
    return filter_records(load_records(module, user), **filters)


def find_record(module, record_id, user):
    """One record. Missing and 'not yours' give the same error,
    so nobody can guess other people's record ids."""
    for row in load_records(module, user):
        if row["id"] == record_id:
            return row
    raise CrmError("Record not found.")


def get_assignable_users(user):
    """Records are assigned to an active Sales Executive.
    A Sales Executive can only pick themselves."""
    sql = "SELECT id, name FROM users WHERE active = 1 AND role = ?"
    params = [SALES_EXECUTIVE]
    if is_sales_executive(user):
        sql += " AND id = ?"
        params.append(user["id"])
    return fetch_all(sql + " ORDER BY name", params)


def count_due_followups(user):
    """Planned follow-ups due today or already overdue (shown in the sidebar)."""
    today = today_in_india().isoformat()
    return sum(1 for row in load_records("followups", user)
               if row["status"] == "Planned" and row["due_date"] <= today)


def get_linked_records(module, record_id, user):
    """Follow-ups, activities and opportunities linked to a record (for the details screen)."""
    column = {"customers": "customer_id", "leads": "lead_id", "opportunities": "opportunity_id"}.get(module)
    if not column:
        return [], [], []
    followups = [row for row in get_records("followups", user, sort="date") if row.get(column) == record_id]
    activities = [row for row in load_records("activities", user) if row.get(column) == record_id]
    opportunities = []
    if module in ("customers", "leads"):
        opportunities = [row for row in load_records("opportunities", user) if row.get(column) == record_id]
    return followups, activities, opportunities


def has_linked_records(module, record_id):
    """True when other (non-deleted) records point to this one."""
    for table, column in LINKS.get(module, []):
        if fetch_one(f"SELECT id FROM {table} WHERE deleted = 0 AND {column} = ?", (record_id,)):
            return True
    return False


# ---------- Validation ----------

def validate_common(module, form, user, existing):
    if not form["name"].strip():
        raise CrmError("Name is required.")
    if len(form["name"]) > 120:
        raise CrmError("Name can be at most 120 characters.")
    if len(form.get("notes") or "") > 2000:
        raise CrmError("Notes can be at most 2000 characters.")
    if form["status"] not in STATUSES[module]:
        raise CrmError("Select a valid status.")
    if is_sales_executive(user) and form["owner_id"] != user["id"]:
        raise CrmError("You can only assign records to yourself.")
    owner = fetch_one("SELECT * FROM users WHERE id = ? AND active = 1 AND role = ?", (form["owner_id"], SALES_EXECUTIVE))
    if not owner:
        raise CrmError("Assign the record to an active Sales Executive.")
    # Changing the owner of a record that has children would split its history between two people.
    if existing and existing["owner_id"] != form["owner_id"] and has_linked_records(module, existing["id"]):
        raise CrmError("This record has linked records. Keep its current owner to preserve the complete history.")

    if module in ("customers", "leads"):
        form["email"] = (form.get("email") or "").strip().lower()
        form["phone"] = (form.get("phone") or "").strip()
        if not form["email"]:
            raise CrmError("Email is required.")
        if not EMAIL_PATTERN.match(form["email"]):
            raise CrmError("Enter a valid email address.")
        if not form["phone"]:
            raise CrmError("Phone is required.")
        if not PHONE_PATTERN.match(form["phone"]):
            raise CrmError("Enter a valid 10-digit Indian mobile number.")


def validate_customer(form, record_id):
    # Deleted customers are included on purpose: their contact details stay reserved.
    if fetch_one("SELECT id FROM customers WHERE email = ? AND id != ?", (form["email"], record_id or 0)):
        raise CrmError("This email is already registered, including inactive customers.")
    if fetch_one("SELECT id FROM customers WHERE phone = ? AND id != ?", (form["phone"], record_id or 0)):
        raise CrmError("This phone is already registered, including inactive customers.")


def validate_lead(form, existing):
    value = form.get("expected_value") or 0
    if value < 0 or value > 999_999_999:
        raise CrmError("Expected value must be between 0 and 99,99,99,999.")
    if round(value, 2) != value:
        raise CrmError("Use up to two decimal places.")
    if form.get("priority") not in PRIORITIES:
        raise CrmError("Select a valid priority.")
    if existing is None and form["status"] != "New":
        raise CrmError("A new lead must start with New status.")
    if existing and existing["status"] == "Converted":
        raise CrmError("Converted leads are read-only.")
    if existing and existing["status"] != form["status"] \
            and form["status"] not in NEXT_LEAD_STATUSES.get(existing["status"], []):
        raise CrmError("Use New → Contacted → Qualified. Use Convert for qualified leads.")


def validate_opportunity(form, user):
    if not form.get("customer_id"):
        raise CrmError("Select a customer.")
    if form.get("stage") not in STAGES:
        raise CrmError("Select a valid stage.")
    expected_status = form["stage"] if form["stage"] in ("Won", "Lost") else "Open"
    if form["status"] != expected_status:
        raise CrmError("Status must match the selected stage.")
    amount = form.get("amount") or 0
    if amount <= 0:
        raise CrmError("Opportunity amount must be greater than 0.")
    if amount > 999_999_999:
        raise CrmError("Opportunity amount can be at most 99,99,99,999.")
    if round(amount, 2) != amount:
        raise CrmError("Use up to two decimal places.")
    if not 0 <= (form.get("probability") or 0) <= 100:
        raise CrmError("Probability must be between 0 and 100.")
    if not form.get("close_date"):
        raise CrmError("Expected close date is required.")
    if expected_status == "Open" and to_date(form["close_date"]) < today_in_india():
        raise CrmError("Expected close date cannot be in the past.")
    if form["stage"] == "Won" and form["probability"] != 100:
        raise CrmError("A won opportunity must have 100% probability.")
    if form["stage"] == "Lost" and form["probability"] != 0:
        raise CrmError("A lost opportunity must have 0% probability.")
    check_same_owner("customers", form.get("customer_id"), form["owner_id"], user)
    check_same_owner("leads", form.get("lead_id"), form["owner_id"], user)
    if form.get("lead_id"):
        lead = find_record("leads", form["lead_id"], user)
        if lead["customer_id"] and lead["customer_id"] != form["customer_id"]:
            raise CrmError("The converted lead belongs to a different customer.")


def validate_followup_or_activity(module, form, user, existing):
    is_followup = module == "followups"
    today = today_in_india()
    if form.get("type") not in ACTIVITY_TYPES:
        raise CrmError("Select a valid activity type.")
    if not form.get("due_date"):
        raise CrmError("Date is required.")
    due_date = to_date(form["due_date"])
    if is_followup and (existing is None or form["status"] == "Planned") and due_date < today:
        raise CrmError("Follow-up date cannot be earlier than today.")
    if is_followup and form["status"] == "Missed" and due_date >= today:
        raise CrmError("Only an overdue follow-up can be marked missed.")

    if not is_followup:
        form["opportunity_id"] = None
    linked_count = sum(1 for key in ("customer_id", "lead_id", "opportunity_id") if form.get(key))
    if linked_count != 1:
        raise CrmError("Select exactly one related customer, lead" + (" or opportunity." if is_followup else "."))

    check_same_owner("customers", form.get("customer_id"), form["owner_id"], user)
    check_same_owner("leads", form.get("lead_id"), form["owner_id"], user)
    if is_followup:
        check_same_owner("opportunities", form.get("opportunity_id"), form["owner_id"], user)


def check_same_owner(module, related_id, owner_id, user):
    """The related record must be visible to you and owned by the same sales person."""
    if not related_id:
        return
    related = find_record(module, related_id, user)
    if related["owner_id"] != owner_id:
        raise CrmError("Related record and assigned user must belong to the same sales owner.")


# ---------- Saving ----------

def save_record(module, form, user, record_id=None):
    """Creates (record_id=None) or updates a record. Returns the record id.
    `form` is a dictionary with keys named like the database columns."""
    check_module(module)
    existing = find_record(module, record_id, user) if record_id else None

    validate_common(module, form, user, existing)
    if module == "customers":
        validate_customer(form, record_id)
    elif module == "leads":
        validate_lead(form, existing)
    elif module == "opportunities":
        validate_opportunity(form, user)
    else:
        validate_followup_or_activity(module, form, user, existing)

    values = {
        "name": form["name"].strip(),
        "status": form["status"],
        "owner_id": form["owner_id"],
        "notes": (form.get("notes") or "").strip(),
        "updated_at": now_utc(),
    }
    for column in MODULE_COLUMNS[module]:
        value = form.get(column)
        values[column] = value.strip() if isinstance(value, str) else value
    for date_column in ("close_date", "due_date"):
        if values.get(date_column):
            values[date_column] = to_date(values[date_column]).isoformat()

    # Outcome date is the real "won/lost on" date, used by the monthly sales chart.
    if module == "opportunities":
        old_stage = existing["stage"] if existing else None
        if values["status"] == "Open":
            values["outcome_date"] = None
        elif old_stage != values["stage"]:
            values["outcome_date"] = today_in_india().isoformat()

    if existing is None:
        values["created_by"] = user["id"]
        values["created_at"] = now_utc()
        record_id = insert(module, values)
        # Readable codes for customers and leads, e.g. CUS-1005 / LD-2005.
        if module == "customers":
            update(module, record_id, {"code": f"CUS-{1000 + record_id}"})
        if module == "leads":
            update(module, record_id, {"code": f"LD-{2000 + record_id}"})
        add_audit_entry(user["id"], "Create", module, record_id, None, values)
    else:
        update(module, record_id, values)
        add_audit_entry(user["id"], "Update", module, record_id, existing, values)
        if existing["status"] != values["status"]:
            add_audit_entry(user["id"], "Status Change", module, record_id, existing["status"], values["status"])
        if existing.get("due_date") and existing["due_date"] != values.get("due_date"):
            add_audit_entry(user["id"], "Reschedule", module, record_id, existing["due_date"], values["due_date"])

    was_completed = existing is not None and existing["status"] == "Completed"
    if module == "followups" and values["status"] == "Completed" and not was_completed:
        move_lead_to_contacted(values.get("lead_id"), record_id, user)
    return record_id


def move_lead_to_contacted(lead_id, followup_id, user):
    """A completed follow-up means the lead has been contacted, so a New lead becomes Contacted."""
    if not lead_id:
        return
    lead = fetch_one("SELECT * FROM leads WHERE id = ? AND deleted = 0", (lead_id,))
    if not lead or lead["status"] != "New":
        return
    update("leads", lead_id, {"status": "Contacted", "updated_at": now_utc()})
    add_audit_entry(user["id"], "Status Change", "leads", lead_id, "New",
                    {"status": "Contacted", "reason": "Follow-up completed", "followup_id": followup_id})


# ---------- Other actions ----------

def delete_record(module, record_id, user):
    """Soft delete. Records that other records point to are kept, so history is not broken."""
    record = find_record(module, record_id, user)
    if has_linked_records(module, record_id):
        raise CrmError("Delete the related records before deleting this record, or keep it for its history.")
    update(module, record_id, {"deleted": 1, "updated_at": now_utc()})
    add_audit_entry(user["id"], "Delete", module, record_id, record, {"id": record_id, "deleted": True})


def mark_done(module, record_id, user):
    """One-click 'Mark done' for a planned follow-up or a pending activity."""
    if module not in ("followups", "activities"):
        raise CrmError("Only follow-ups and activities can be marked as done.")
    record = find_record(module, record_id, user)
    open_status = "Planned" if module == "followups" else "Pending"
    if record["status"] != open_status:
        raise CrmError(f"Only a {open_status.lower()} item can be marked as done.")
    update(module, record_id, {"status": "Completed", "updated_at": now_utc()})
    add_audit_entry(user["id"], "Status Change", module, record_id, open_status, "Completed")
    if module == "followups":
        move_lead_to_contacted(record.get("lead_id"), record_id, user)


def convert_lead(lead_id, user):
    """Qualified lead -> customer (+ an opportunity when the lead has an expected value).
    Returns the customer id."""
    lead = find_record("leads", lead_id, user)
    if lead["status"] != "Qualified":
        raise CrmError("Only qualified leads can be converted.")

    # Reuse an existing customer only when email AND phone match and it has the same owner.
    customer = fetch_one("SELECT * FROM customers WHERE email = ? OR phone = ?", (lead["email"], lead["phone"]))
    if customer and (customer["deleted"] or customer["owner_id"] != lead["owner_id"]
                     or customer["email"] != lead["email"] or customer["phone"] != lead["phone"]):
        raise CrmError("Customer contact details conflict with an existing record. Please resolve the duplicate first.")

    if customer:
        customer_id = customer["id"]
    else:
        customer_id = insert("customers", {
            "name": lead["name"], "email": lead["email"], "phone": lead["phone"], "company": lead["company"],
            "status": "Active", "notes": lead["notes"], "owner_id": lead["owner_id"], "created_by": user["id"],
            "created_at": now_utc(), "updated_at": now_utc(),
        })
        update("customers", customer_id, {"code": f"CUS-{1000 + customer_id}"})
        add_audit_entry(user["id"], "Create", "customers", customer_id, None, {"from_lead": lead_id})

    update("leads", lead_id, {"status": "Converted", "customer_id": customer_id, "updated_at": now_utc()})

    if lead["expected_value"] > 0:
        opportunity_id = insert("opportunities", {
            "name": (lead["company"] or lead["name"]) + " - sales enquiry",
            "customer_id": customer_id, "lead_id": lead_id, "owner_id": lead["owner_id"], "created_by": user["id"],
            "amount": lead["expected_value"], "probability": 25, "stage": "Qualification", "status": "Open",
            "close_date": (today_in_india() + timedelta(days=30)).isoformat(),
            "source": lead["source"], "created_at": now_utc(), "updated_at": now_utc(),
        })
        add_audit_entry(user["id"], "Create", "opportunities", opportunity_id, None, {"from_lead": lead_id})

    add_audit_entry(user["id"], "Convert", "leads", lead_id, lead["status"], {"status": "Converted", "customer_id": customer_id})
    return customer_id
