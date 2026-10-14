"""
The eight reports and the CSV export.
Each report is returned as (headings, rows) so the screen can show it
as a table and also download it as CSV.
"""

import csv
import io

from logic.database import fetch_all
from logic.records import get_records, is_sales_executive
from logic.settings import ADMIN, MODULES, STAGES, nice_date, percentage, rupees

REPORTS = {
    "pipeline": "Pipeline",
    "conversion": "Conversion",
    "customers": "Customers",
    "leads": "Leads",
    "opportunities": "Opportunities",
    "followups": "Follow-ups",
    "user-activity": "User activity",
    "audit": "Audit log",
}


def can_open(report_name, user):
    """Audit log: Admin only. User activity: Admin and Manager. Others: everyone."""
    if report_name == "audit":
        return user["role"] == ADMIN
    if report_name == "user-activity":
        return not is_sales_executive(user)
    return report_name in REPORTS


def reports_for(user):
    return {name: title for name, title in REPORTS.items() if can_open(name, user)}


def build_report(report_name, user, search="", owner_id=None, from_date=None, to_date_=None, sort="newest"):
    if not can_open(report_name, user):
        raise PermissionError("You do not have access to this report.")
    filters = {"search": search, "owner_id": owner_id, "from_date": from_date, "to_date_": to_date_, "sort": sort}

    if report_name == "pipeline":
        return pipeline_report(user, filters)
    if report_name == "conversion":
        return conversion_report(user, filters)
    if report_name in ("audit", "user-activity"):
        headings, rows = audit_report(user, filters) if report_name == "audit" else user_activity_report(user, filters)
        if search:
            rows = [row for row in rows if search.lower() in " ".join(str(cell) for cell in row).lower()]
        if sort == "name":
            rows.sort(key=lambda row: row[0])
        return headings, rows
    return module_report(report_name, user, filters)


def pipeline_report(user, filters):
    """Open pipeline three ways: per stage, per owner, and stage x owner."""
    open_deals = [row for row in get_records("opportunities", user, **filters) if row["status"] == "Open"]

    def make_row(view, stage, owner, deals):
        return [view, stage, owner, len(deals),
                rupees(sum(row["amount"] for row in deals)),
                rupees(sum(row["weighted_amount"] for row in deals))]

    rows = []
    open_stages = [stage for stage in STAGES if stage not in ("Won", "Lost")]
    for stage in open_stages:
        rows.append(make_row("Stage-wise", stage, "All owners", [row for row in open_deals if row["stage"] == stage]))
    for owner in sorted({row["owner"] for row in open_deals}):
        rows.append(make_row("Owner-wise", "All open stages", owner, [row for row in open_deals if row["owner"] == owner]))
    for stage in open_stages:
        for owner in sorted({row["owner"] for row in open_deals if row["stage"] == stage}):
            deals = [row for row in open_deals if row["stage"] == stage and row["owner"] == owner]
            rows.append(make_row("Stage x owner", stage, owner, deals))
    rows.append(make_row("Total", "All open stages", "All owners", open_deals))
    return ["View", "Stage", "Owner", "Open deals", "Amount", "Weighted value"], rows


def conversion_report(user, filters):
    leads = get_records("leads", user, **filters)
    opportunities = get_records("opportunities", user, **filters)
    converted = sum(1 for row in leads if row["status"] == "Converted")
    won = sum(1 for row in opportunities if row["status"] == "Won")
    lost = sum(1 for row in opportunities if row["status"] == "Lost")
    rows = [
        ["Leads converted", converted, percentage(converted, len(leads))],
        ["Leads not converted", len(leads) - converted, percentage(len(leads) - converted, len(leads))],
        ["Opportunities won", won, percentage(won, len(opportunities))],
        ["Opportunities lost", lost, percentage(lost, len(opportunities))],
    ]
    return ["Measure", "Count", "Rate"], rows


def module_report(module, user, filters):
    records = get_records(module, user, **filters)
    if module == "customers":
        headings = ["Customer", "Code", "Status", "Owner", "Created", "Company", "Email", "Phone"]
        rows = [[r["name"], r["code"], r["status"], r["owner"], nice_date(r["created_at"]), r["company"], r["email"], r["phone"]]
                for r in records]
    elif module == "leads":
        headings = ["Lead", "Code", "Source", "Status", "Priority", "Owner", "Expected value", "Converted", "Converted to customer"]
        rows = [[r["name"], r["code"], r["source"], r["status"], r["priority"], r["owner"], rupees(r["expected_value"]),
                 "Yes" if r["status"] == "Converted" else "No", r["related_to"]] for r in records]
    elif module == "followups":
        headings = ["Subject", "Date", "Status", "Owner", "Type", "Related record"]
        rows = [[r["name"], nice_date(r["due_date"]), "Overdue" if r["is_overdue"] else r["status"], r["owner"], r["type"], r["related_to"]]
                for r in records]
    else:
        headings = ["Opportunity", "Customer", "Stage", "Status", "Amount", "Probability", "Close date", "Owner"]
        rows = [[r["name"], r["related_to"], r["stage"], r["status"], rupees(r["amount"]), f"{r['probability']}%",
                 nice_date(r["close_date"]), r["owner"]] for r in records]
    return headings, rows


def filtered_audit_logs(user, filters):
    sql = ("SELECT audit_log.*, users.name AS user_name FROM audit_log "
           "LEFT JOIN users ON users.id = audit_log.user_id WHERE 1 = 1")
    params = []
    # Managers see only CRM record events. Logins and user changes are Admin only.
    if user["role"] != ADMIN:
        sql += f" AND entity IN ({', '.join('?' for _ in MODULES)})"
        params += list(MODULES)
    if filters["owner_id"]:
        sql += " AND user_id = ?"
        params.append(filters["owner_id"])
    if filters["from_date"]:
        sql += " AND audit_log.created_at >= ?"
        params.append(filters["from_date"].isoformat())
    if filters["to_date_"]:
        sql += " AND audit_log.created_at <= ?"
        params.append(filters["to_date_"].isoformat() + " 23:59:59")
    sql += " ORDER BY audit_log.id " + ("ASC" if filters["sort"] == "oldest" else "DESC")
    return fetch_all(sql, params)


def audit_report(user, filters):
    logs = filtered_audit_logs(user, filters)
    rows = [[log["created_at"], log["user_name"] or "Unknown", log["entity"], log["action"], log["record_id"],
             log["result"], log["old_value"] or "", log["new_value"] or ""] for log in logs]
    return ["Date (UTC)", "User", "Module", "Action", "Record", "Result", "Old value", "New value"], rows


def user_activity_report(user, filters):
    logs = filtered_audit_logs(user, filters)
    per_user = {}
    for log in logs:
        name = log["user_name"] or "Unknown"
        if name not in per_user:
            per_user[name] = {"total": 0, "created": 0, "updated": 0, "last": log["created_at"]}
        per_user[name]["total"] += 1
        per_user[name]["created"] += log["action"] == "Create"
        per_user[name]["updated"] += log["action"] == "Update"
        per_user[name]["last"] = max(per_user[name]["last"], log["created_at"])
    rows = [[name, data["total"], data["created"], data["updated"], data["last"]] for name, data in per_user.items()]
    return ["User", "Total actions", "Created", "Updated", "Last activity (UTC)"], rows


def to_csv(headings, rows):
    """CSV bytes for download. Cells starting with = + - @ get a leading quote,
    so Excel does not run them as formulas."""
    def safe(cell):
        text = str(cell)
        if text and text[0] in "=+-@\t\r":
            text = "'" + text
        return text

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    writer.writerow(headings)
    for row in rows:
        writer.writerow([safe(cell) for cell in row])
    return output.getvalue().encode("utf-8-sig")
