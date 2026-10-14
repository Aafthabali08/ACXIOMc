"""
Numbers for the three role dashboards and the team performance table.
Every number comes from records.get_records(), so the role rules
(Sales Executive sees only their own records) are already applied.
"""

from datetime import date, datetime, timedelta, timezone

from logic.auth import is_locked
from logic.database import fetch_all
from logic.records import get_records
from logic.settings import ADMIN, MANAGER, OPEN_LEAD_STATUSES, ROLES, SALES_EXECUTIVE, to_date, today_in_india

PERIODS = {"all": "All time", "today": "Today", "week": "This week", "month": "This month", "custom": "Custom range"}


def period_dates(period, custom_from=None, custom_to=None):
    """Turns a period name into (from_date, to_date). 'all' gives (None, None)."""
    today = today_in_india()
    if period == "today":
        return today, today
    if period == "week":
        return today - timedelta(days=today.weekday()), today   # Monday to today
    if period == "month":
        return today.replace(day=1), today
    if period == "custom":
        return custom_from, custom_to
    return None, None


def last_six_months():
    """[(year, month), ...] for the last six months, oldest first."""
    today = today_in_india()
    months = []
    year, month = today.year, today.month
    for _ in range(6):
        months.insert(0, (year, month))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return months


def build_dashboard(user, from_date=None, to_date_=None):
    today = today_in_india()
    period = {"from_date": from_date, "to_date_": to_date_}

    # Records created in the selected period.
    customers = get_records("customers", user, **period)
    leads = get_records("leads", user, **period)
    opportunities = get_records("opportunities", user, **period)

    open_deals = [row for row in opportunities if row["status"] == "Open"]
    won_deals = [row for row in opportunities if row["status"] == "Won"]
    lost_deals = [row for row in opportunities if row["status"] == "Lost"]

    # Current work, not affected by the period filter.
    pending_followups = get_records("followups", user, status="Planned", sort="date")
    recent_activities = sorted(get_records("activities", user),
                               key=lambda row: (row["due_date"], row["created_at"]), reverse=True)[:5]
    all_opportunities = get_records("opportunities", user)
    closing_soon = sorted(
        [row for row in all_opportunities if row["status"] == "Open" and to_date(row["close_date"]) <= today + timedelta(days=30)],
        key=lambda row: row["close_date"])[:5]

    # Won sales per month for the last six months (by the date the deal was won).
    monthly_sales = []
    for year, month in last_six_months():
        total = sum(row["amount"] for row in all_opportunities
                    if row["status"] == "Won" and row["outcome_date"]
                    and to_date(row["outcome_date"]).year == year and to_date(row["outcome_date"]).month == month)
        monthly_sales.append({"Month": date(year, month, 1).strftime("%b %y"), "Won sales": total})

    dashboard = {
        "customers": customers,
        "leads": leads,
        "opportunities": opportunities,
        "open_leads": sum(1 for row in leads if row["status"] in OPEN_LEAD_STATUSES),
        "open_deals": open_deals,
        "open_pipeline": sum(row["amount"] for row in open_deals),
        "weighted_pipeline": sum(row["weighted_amount"] for row in open_deals),
        "won_count": len(won_deals),
        "lost_count": len(lost_deals),
        "won_value": sum(row["amount"] for row in won_deals),
        "pending_followups": pending_followups,
        "overdue_followups": [row for row in pending_followups if to_date(row["due_date"]) < today],
        "today_followups": [row for row in pending_followups if to_date(row["due_date"]) == today],
        "recent_activities": recent_activities,
        "closing_soon": closing_soon,
        "monthly_sales": monthly_sales,
    }

    if user["role"] == ADMIN:
        dashboard.update(admin_numbers())
    if user["role"] in (ADMIN, MANAGER):
        dashboard["team"] = team_performance(user, from_date, to_date_)
    return dashboard


def admin_numbers():
    users = fetch_all("SELECT * FROM users")
    one_day_ago = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    failed_logins = fetch_all(
        "SELECT id FROM audit_log WHERE entity = 'Authentication' AND result = 'Failed' AND created_at >= ?",
        (one_day_ago,))
    recent_audit = fetch_all(
        "SELECT audit_log.created_at, users.name AS user_name, action, entity, result FROM audit_log "
        "LEFT JOIN users ON users.id = audit_log.user_id ORDER BY audit_log.id DESC LIMIT 8")
    return {
        "total_users": len(users),
        "active_users": sum(1 for user in users if user["active"]),
        "locked_users": sum(1 for user in users if is_locked(user)),
        "users_per_role": {role: sum(1 for user in users if user["role"] == role) for role in ROLES},
        "failed_logins_24h": len(failed_logins),
        "recent_audit": recent_audit,
        "recent_users": sorted(users, key=lambda user: user["created_at"], reverse=True)[:5],
    }


def team_performance(user, from_date=None, to_date_=None):
    """One row per sales executive (plus anyone else who owns records in the period)."""
    period = {"from_date": from_date, "to_date_": to_date_}
    leads = get_records("leads", user, **period)
    opportunities = get_records("opportunities", user, **period)
    activities = get_records("activities", user, **period)
    overdue = get_records("followups", user, status="Overdue")

    owners_with_records = {row["owner_id"] for row in leads + opportunities + activities + overdue}
    users = fetch_all("SELECT * FROM users ORDER BY name")
    # Inactive sales executives are shown only while they still own records in the period.
    team = [member for member in users
            if member["id"] in owners_with_records or (member["active"] and member["role"] == SALES_EXECUTIVE)]

    rows = []
    for member in team:
        member_deals = [row for row in opportunities if row["owner_id"] == member["id"]]
        open_deals = [row for row in member_deals if row["status"] == "Open"]
        won = [row for row in member_deals if row["status"] == "Won"]
        lost = [row for row in member_deals if row["status"] == "Lost"]
        rows.append({
            "name": member["name"],
            "leads": sum(1 for row in leads if row["owner_id"] == member["id"]),
            "converted": sum(1 for row in leads if row["owner_id"] == member["id"] and row["status"] == "Converted"),
            "open_deals": len(open_deals),
            "open_pipeline": sum(row["amount"] for row in open_deals),
            "weighted_pipeline": sum(row["weighted_amount"] for row in open_deals),
            "won_deals": len(won),
            "won_value": sum(row["amount"] for row in won),
            "lost_deals": len(lost),
            "overdue_followups": sum(1 for row in overdue if row["owner_id"] == member["id"]),
            "activities": sum(1 for row in activities if row["owner_id"] == member["id"]),
        })
    return rows
