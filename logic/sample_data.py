"""
Demo users and sample CRM records, created the first time the app starts
(only when the users table is empty).

All demo accounts use the password: Acxiom@123
"""

from datetime import timedelta

from logic.audit import add_audit_entry
from logic.auth import hash_password
from logic.database import fetch_one, insert
from logic.settings import ACTIVITY_TYPES, ADMIN, MANAGER, SALES_EXECUTIVE, now_utc, today_in_india

DEMO_PASSWORD = "Acxiom@123"

DEMO_USERS = [
    ("Aarav Sharma", "admin@acxiom.test", ADMIN),
    ("Priya Nair", "manager@acxiom.test", MANAGER),
    ("Rahul Verma", "sales@acxiom.test", SALES_EXECUTIVE),
    ("Neha Iyer", "sales2@acxiom.test", SALES_EXECUTIVE),
]

# Customer, company, city, deal name, amount, stage, probability, months ago the deal closed
SAMPLE_ACCOUNTS = [
    ("Karthik Rao", "Nirmaan Industries", "Bengaluru", "Annual service agreement", 450000, "Qualification", 25, 0),
    ("Ananya Desai", "Bluepeak Technologies", "Pune", "CRM implementation", 280000, "Proposal", 50, 0),
    ("Vikram Shah", "Shah Logistics", "Ahmedabad", "Fleet support renewal", 650000, "Negotiation", 75, 0),
    ("Meera Menon", "Malabar Retail", "Kochi", "Retail expansion", 320000, "Won", 100, 0),
    ("Arjun Kapoor", "Kapoor Textiles", "Jaipur", "Textile supply contract", 180000, "Lost", 0, 1),
    ("Divya Reddy", "Deccan Foods", "Hyderabad", "Distribution software", 210000, "Proposal", 50, 0),
    ("Suresh Pillai", "Coastal Marine Exports", "Chennai", "Port tracking system", 390000, "Won", 100, 2),
    ("Lakshmi Iyer", "Saraswati Publications", "Mysuru", "Print workflow upgrade", 240000, "Won", 100, 4),
]

FOLLOWUP_SUBJECTS = [
    "Discuss service requirements", "Share revised proposal", "Confirm pricing with Vikram", "Check onboarding progress",
    "Review next quarter plan", "Arrange product demonstration", "Collect renewal feedback", "Plan annual review",
]

# Name, company, status, source, priority
SAMPLE_LEADS = [
    ("Rohit Kumar", "Orbit Systems", "New", "Website", "High"),
    ("Sneha Joshi", "Joshi Enterprises", "Contacted", "Referral", "Normal"),
    ("Aditya Patel", "Patel Exports", "Qualified", "Website", "Normal"),
    ("Pooja Singh", "Northstar Services", "New", "Referral", "High"),
    ("Sanjay Das", "Eastern Traders", "Lost", "Website", "Normal"),
    ("Nisha Thomas", "Thomas Ventures", "Unqualified", "Referral", "Normal"),
    ("Farhan Qureshi", "Qureshi Hardware", "Contacted", "Exhibition", "High"),
]


def months_ago(day, months):
    """First day of the month, `months` months before `day`."""
    year, month = day.year, day.month - months
    while month <= 0:
        year, month = year - 1, month + 12
    return day.replace(year=year, month=month, day=1)


def create_sample_data_if_empty():
    if fetch_one("SELECT id FROM users"):
        return

    user_ids = {}
    for name, email, role in DEMO_USERS:
        user_ids[email] = insert("users", {
            "name": name, "email": email, "password_hash": hash_password(DEMO_PASSWORD),
            "role": role, "active": 1, "created_at": now_utc(),
        })
    rahul = user_ids["sales@acxiom.test"]
    neha = user_ids["sales2@acxiom.test"]

    today = today_in_india()
    month_start = today.replace(day=1).isoformat() + " 00:00:00"

    for index, account in enumerate(SAMPLE_ACCOUNTS):
        contact, company, city, deal, amount, stage, probability, months_back = account
        owner = neha if index in (5, 7) else rahul
        is_closed = stage in ("Won", "Lost")
        closed_on = months_ago(today, months_back).replace(day=min(today.day, 28)) if is_closed else None
        created_on = months_ago(today, months_back).isoformat() + " 00:00:00"

        customer_id = insert("customers", {
            "code": f"CUS-{1001 + index}", "name": contact, "company": company,
            "email": f"contact{index + 1}@example.test", "phone": f"98765432{index + 10}",
            "city": city, "state": "India", "address": "Business district", "status": "Active",
            "notes": "Demo customer.", "owner_id": owner, "created_by": owner,
            "created_at": created_on, "updated_at": created_on,
        })
        insert("opportunities", {
            "name": deal, "customer_id": customer_id, "stage": stage, "amount": amount, "probability": probability,
            "status": stage if is_closed else "Open",
            "close_date": (closed_on or today + timedelta(days=14 + index * 4)).isoformat(),
            "outcome_date": closed_on.isoformat() if closed_on else None,
            "source": "Referral", "owner_id": owner, "created_by": owner,
            "created_at": created_on, "updated_at": created_on,
        })
        # Due dates from yesterday onwards, so the demo shows overdue, today and upcoming work.
        insert("followups", {
            "name": FOLLOWUP_SUBJECTS[index], "customer_id": customer_id,
            "due_date": (today + timedelta(days=index - 1)).isoformat(),
            "type": ACTIVITY_TYPES[index % 4], "status": "Planned",
            "owner_id": owner, "created_by": owner, "created_at": month_start, "updated_at": month_start,
        })
        insert("activities", {
            "name": "Introduction call with " + contact.split()[0], "customer_id": customer_id,
            "due_date": today.isoformat(), "type": "Call", "status": "Completed",
            "notes": "Discussed business requirements and the next follow-up.",
            "owner_id": owner, "created_by": owner, "created_at": month_start, "updated_at": month_start,
        })

    for index, (name, company, status, source, priority) in enumerate(SAMPLE_LEADS):
        owner = neha if index in (5, 6) else rahul
        insert("leads", {
            "code": f"LD-{2001 + index}", "name": name, "company": company,
            "email": f"lead{index}@example.test", "phone": f"91234567{index + 10}",
            "status": status, "source": source, "priority": priority, "expected_value": 150000 + index * 45000,
            "owner_id": owner, "created_by": owner, "created_at": month_start, "updated_at": month_start,
        })

    add_audit_entry(rahul, "Setup", "Application", "demo", new_value="Sample CRM records created")
