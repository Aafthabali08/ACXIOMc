"""
Fixed lists and small helper functions used all over the app.

If you want to add a new status, stage, role or activity type, change it here
and the dropdowns and the checks will both pick it up.
"""

from datetime import date, datetime, timedelta, timezone

# ---------- Roles ----------

ADMIN = "Admin"
MANAGER = "Manager"
SALES_EXECUTIVE = "SalesExecutive"

ROLES = [ADMIN, MANAGER, SALES_EXECUTIVE]

ROLE_TITLES = {
    ADMIN: "Administrator",
    MANAGER: "Sales Manager",
    SALES_EXECUTIVE: "Sales Executive",
}

# ---------- CRM modules ----------

# The key is also the database table name.
MODULES = {
    "customers": "Customers",
    "leads": "Leads",
    "opportunities": "Opportunities",
    "followups": "Follow-ups",
    "activities": "Activities",
}

# Allowed statuses for each module. The first one is the default for new records.
STATUSES = {
    "customers": ["Active", "Inactive"],
    "leads": ["New", "Contacted", "Qualified", "Unqualified", "Converted", "Lost"],
    "opportunities": ["Open", "Won", "Lost"],
    "followups": ["Planned", "Completed", "Missed", "Cancelled"],
    "activities": ["Pending", "Completed", "Cancelled"],
}

STAGES = ["Qualification", "Proposal", "Negotiation", "Won", "Lost"]
ACTIVITY_TYPES = ["Call", "Meeting", "Email", "Task"]
PRIORITIES = ["Low", "Normal", "High"]

# Which lead statuses you can move to by hand.
# "Converted" is only reached with the Convert button.
NEXT_LEAD_STATUSES = {
    "New": ["Contacted", "Lost"],
    "Contacted": ["Qualified", "Unqualified", "Lost"],
    "Qualified": ["Lost"],
}

# Lead statuses that still need work from the sales team.
OPEN_LEAD_STATUSES = ["New", "Contacted", "Qualified"]

# ---------- Login security ----------

MAX_FAILED_LOGINS = 5
LOCK_MINUTES = 15

# ---------- Dates ----------

# All business date rules (overdue, past close date) use the Indian date.
INDIA_OFFSET = timedelta(hours=5, minutes=30)


def today_in_india():
    return (datetime.now(timezone.utc) + INDIA_OFFSET).date()


def now_utc():
    """Current UTC time as text, the format we store in the database."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def utc_text_to_india_date(utc_text):
    utc_time = datetime.strptime(utc_text[:19], "%Y-%m-%d %H:%M:%S")
    return (utc_time + INDIA_OFFSET).date()


def to_date(value):
    """Turns 'YYYY-MM-DD' text into a date. Returns None for empty values."""
    if not value:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def nice_date(value):
    """'2026-10-14' -> '14 Oct 2026'."""
    value = to_date(value)
    return value.strftime("%d %b %Y") if value else ""


# ---------- Formatting ----------

def rupees(amount):
    """450000 -> '₹4,50,000' (Indian lakh grouping)."""
    amount = round(float(amount or 0))
    sign = "-" if amount < 0 else ""
    digits = str(abs(amount))
    if len(digits) > 3:
        last_three = digits[-3:]
        rest = digits[:-3]
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        digits = ",".join(groups) + "," + last_three
    return sign + "₹" + digits


def percentage(part, total):
    if total == 0:
        return "0%"
    return f"{100 * part / total:.1f}%"


def win_rate(won, lost):
    if won + lost == 0:
        return "-"
    return f"{100 * won / (won + lost):.0f}%"


def role_title(role):
    return ROLE_TITLES.get(role, "No access")
