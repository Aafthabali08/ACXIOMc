"""
Tests for the business rules. Each test gets its own fresh database with the demo data.

Run with:   python -m pytest tests
"""

from datetime import timedelta

import pytest

from logic import auth, database, records, reports, users
from logic.dashboard_numbers import build_dashboard, team_performance
from logic.records import CrmError
from logic.sample_data import create_sample_data_if_empty
from logic.settings import rupees, today_in_india


@pytest.fixture(autouse=True)
def fresh_database(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_FILE", tmp_path / "test.db")
    database.create_tables()
    create_sample_data_if_empty()


def user(email):
    return auth.find_user_by_email(email)


def new_lead(owner, **changes):
    form = {"name": "Test Lead", "email": "test.lead@example.test", "phone": "9000000001", "company": "Test Co",
            "source": "Website", "priority": "Normal", "expected_value": 50000.0, "status": "New",
            "owner_id": owner["id"], "notes": ""}
    form.update(changes)
    return form


# ---------- Login ----------

def test_login_works_with_demo_password():
    logged_in, error = auth.login("sales@acxiom.test", "Acxiom@123")
    assert error is None and logged_in["name"] == "Rahul Verma"


def test_account_locks_after_five_wrong_passwords():
    for _ in range(5):
        auth.login("sales@acxiom.test", "wrong")
    _, error = auth.login("sales@acxiom.test", "Acxiom@123")
    assert "locked" in error
    users.unlock_user(user("admin@acxiom.test"), user("sales@acxiom.test")["id"])
    assert auth.login("sales@acxiom.test", "Acxiom@123")[1] is None


def test_inactive_user_cannot_log_in():
    admin = user("admin@acxiom.test")
    neha = user("sales2@acxiom.test")
    users.save_user(admin, neha["name"], neha["email"], "SalesExecutive", False, "", neha["id"])
    assert auth.login("sales2@acxiom.test", "Acxiom@123")[1] == "Invalid login details or inactive account."


def test_register_needs_strong_password_and_gives_sales_role():
    assert auth.register("New Person", "new@example.test", "weak", "weak")[1] is not None
    new_user, error = auth.register("New Person", "new@example.test", "Strong@123", "Strong@123")
    assert error is None and new_user["role"] == "SalesExecutive"


def test_admin_cannot_remove_own_admin_access():
    admin = user("admin@acxiom.test")
    _, error = users.save_user(admin, admin["name"], admin["email"], "Manager", True, "", admin["id"])
    assert error == "You cannot remove your own administrator access."


# ---------- Who sees what ----------

def test_sales_executive_only_sees_own_records():
    rahul, neha, manager = user("sales@acxiom.test"), user("sales2@acxiom.test"), user("manager@acxiom.test")
    rahul_customers = records.get_records("customers", rahul)
    assert all(row["owner_id"] == rahul["id"] for row in rahul_customers)
    assert len(rahul_customers) + len(records.get_records("customers", neha)) == len(records.get_records("customers", manager))


def test_sales_executive_cannot_open_someone_elses_record():
    rahul, neha = user("sales@acxiom.test"), user("sales2@acxiom.test")
    neha_customer = records.get_records("customers", neha)[0]
    with pytest.raises(CrmError):
        records.find_record("customers", neha_customer["id"], rahul)


def test_sales_executive_cannot_assign_to_someone_else():
    rahul, neha = user("sales@acxiom.test"), user("sales2@acxiom.test")
    with pytest.raises(CrmError, match="only assign records to yourself"):
        records.save_record("leads", new_lead(neha), rahul)


# ---------- Leads ----------

def test_lead_workflow_and_conversion_creates_customer_and_opportunity():
    rahul = user("sales@acxiom.test")
    lead_id = records.save_record("leads", new_lead(rahul), rahul)
    assert records.find_record("leads", lead_id, rahul)["code"] == f"LD-{2000 + lead_id}"

    with pytest.raises(CrmError, match="Only qualified"):
        records.convert_lead(lead_id, rahul)
    with pytest.raises(CrmError):   # New cannot jump straight to Qualified
        records.save_record("leads", new_lead(rahul, status="Qualified"), rahul, lead_id)

    records.save_record("leads", new_lead(rahul, status="Contacted"), rahul, lead_id)
    records.save_record("leads", new_lead(rahul, status="Qualified"), rahul, lead_id)
    customer_id = records.convert_lead(lead_id, rahul)

    lead = records.find_record("leads", lead_id, rahul)
    assert lead["status"] == "Converted" and lead["customer_id"] == customer_id
    opportunity = [row for row in records.get_records("opportunities", rahul) if row["lead_id"] == lead_id][0]
    assert opportunity["amount"] == 50000 and opportunity["probability"] == 25
    with pytest.raises(CrmError, match="read-only"):
        records.save_record("leads", new_lead(rahul, status="Lost"), rahul, lead_id)


def test_new_lead_must_start_as_new_and_phone_must_be_valid():
    rahul = user("sales@acxiom.test")
    with pytest.raises(CrmError, match="must start with New"):
        records.save_record("leads", new_lead(rahul, status="Contacted"), rahul)
    with pytest.raises(CrmError, match="Indian mobile"):
        records.save_record("leads", new_lead(rahul, phone="12345"), rahul)


# ---------- Customers ----------

def test_duplicate_customer_email_is_blocked():
    rahul = user("sales@acxiom.test")
    form = {"name": "Copy", "email": "contact1@example.test", "phone": "9000000099", "status": "Active",
            "owner_id": rahul["id"]}
    with pytest.raises(CrmError, match="email is already registered"):
        records.save_record("customers", form, rahul)


def test_customer_with_linked_records_cannot_be_deleted():
    rahul = user("sales@acxiom.test")
    customer = records.get_records("customers", rahul)[0]
    with pytest.raises(CrmError, match="Delete the related records"):
        records.delete_record("customers", customer["id"], rahul)


# ---------- Opportunities ----------

def test_opportunity_rules():
    rahul = user("sales@acxiom.test")
    customer = records.get_records("customers", rahul)[0]
    form = {"name": "Deal", "customer_id": customer["id"], "lead_id": None, "stage": "Proposal", "status": "Open",
            "amount": 1000.0, "probability": 50, "close_date": today_in_india() + timedelta(days=5),
            "source": "", "owner_id": rahul["id"]}
    with pytest.raises(CrmError, match="cannot be in the past"):
        records.save_record("opportunities", {**form, "close_date": today_in_india() - timedelta(days=1)}, rahul)
    with pytest.raises(CrmError, match="100% probability"):
        records.save_record("opportunities", {**form, "stage": "Won", "status": "Won"}, rahul)
    with pytest.raises(CrmError, match="greater than 0"):
        records.save_record("opportunities", {**form, "amount": 0}, rahul)

    deal_id = records.save_record("opportunities", form, rahul)
    records.save_record("opportunities", {**form, "stage": "Won", "status": "Won", "probability": 100}, rahul, deal_id)
    assert records.find_record("opportunities", deal_id, rahul)["outcome_date"] == today_in_india().isoformat()


# ---------- Follow-ups ----------

def test_followup_needs_exactly_one_related_record_and_no_past_date():
    rahul = user("sales@acxiom.test")
    customer = records.get_records("customers", rahul)[0]
    form = {"name": "Call back", "type": "Call", "due_date": today_in_india(), "status": "Planned",
            "customer_id": customer["id"], "lead_id": None, "opportunity_id": None, "owner_id": rahul["id"]}
    with pytest.raises(CrmError, match="exactly one"):
        records.save_record("followups", {**form, "customer_id": None}, rahul)
    with pytest.raises(CrmError, match="earlier than today"):
        records.save_record("followups", {**form, "due_date": today_in_india() - timedelta(days=1)}, rahul)
    assert records.save_record("followups", form, rahul)


def test_mark_done_moves_new_lead_to_contacted():
    rahul = user("sales@acxiom.test")
    lead_id = records.save_record("leads", new_lead(rahul), rahul)
    followup_id = records.save_record("followups", {
        "name": "First call", "type": "Call", "due_date": today_in_india(), "status": "Planned",
        "customer_id": None, "lead_id": lead_id, "opportunity_id": None, "owner_id": rahul["id"]}, rahul)
    records.mark_done("followups", followup_id, rahul)
    assert records.find_record("followups", followup_id, rahul)["status"] == "Completed"
    assert records.find_record("leads", lead_id, rahul)["status"] == "Contacted"
    with pytest.raises(CrmError, match="Only a planned"):
        records.mark_done("followups", followup_id, rahul)


# ---------- Dashboard and reports ----------

def test_dashboard_and_team_numbers():
    manager = user("manager@acxiom.test")
    data = build_dashboard(manager)
    assert data["won_count"] == 3 and data["lost_count"] == 1
    assert len(data["monthly_sales"]) == 6
    team_names = [row["name"] for row in team_performance(manager)]
    assert team_names == ["Neha Iyer", "Rahul Verma"]


def test_report_access_and_csv_is_formula_safe():
    rahul, admin, manager = user("sales@acxiom.test"), user("admin@acxiom.test"), user("manager@acxiom.test")
    assert not reports.can_open("audit", rahul)
    assert not reports.can_open("audit", manager)
    assert reports.can_open("user-activity", manager)
    headings, rows = reports.build_report("pipeline", admin)
    assert rows[-1][0] == "Total"
    assert reports.to_csv(["A"], [["=1+1"]]).decode("utf-8-sig").splitlines()[1] == "\"'=1+1\""


def test_rupees_uses_indian_grouping():
    assert rupees(450000) == "₹4,50,000"
    assert rupees(12345678) == "₹1,23,45,678"
    assert rupees(999) == "₹999"


# ---------- Remaining functions (so every function in logic/ is exercised) ----------

def test_profile_name_and_password_change():
    rahul = user("sales@acxiom.test")
    assert auth.change_my_name(rahul, "") is not None
    assert auth.change_my_name(rahul, "Rahul V") is None
    assert auth.change_my_password(rahul, "wrong", "New@12345", "New@12345") == "Current password is not correct."
    assert auth.change_my_password(rahul, "Acxiom@123", "New@12345", "Other@12345") == "Both passwords must match."
    assert auth.change_my_password(rahul, "Acxiom@123", "New@12345", "New@12345") is None
    assert auth.login("sales@acxiom.test", "New@12345")[0]["name"] == "Rahul V"


def test_previous_login_time_and_logout():
    assert auth.previous_login_time(user("sales@acxiom.test")["id"]) is None
    auth.login("sales@acxiom.test", "Acxiom@123")
    auth.login("sales@acxiom.test", "Acxiom@123")
    assert auth.previous_login_time(user("sales@acxiom.test")["id"]) is not None
    auth.logout(user("sales@acxiom.test")["id"])


def test_register_rejects_duplicate_email():
    assert auth.register("Copy", "sales@acxiom.test", "Strong@123", "Strong@123")[1] == "This email is already registered."


def test_admin_creates_edits_and_filters_users():
    admin = user("admin@acxiom.test")
    new_id, error = users.save_user(admin, "Kiran", "kiran@example.test", "Manager", True, "Strong@123")
    assert error is None
    assert users.save_user(admin, "Kiran", "admin@acxiom.test", "Manager", True, "", new_id)[1] is not None
    assert users.save_user(admin, "Kiran K", "kiran@example.test", "SalesExecutive", True, "Reset@123", new_id)[1] is None
    assert auth.get_user(new_id)["role"] == "SalesExecutive"
    assert auth.login("kiran@example.test", "Reset@123")[1] is None
    assert [row["name"] for row in users.list_users(search="kiran")] == ["Kiran K"]
    assert len(users.list_users(role="Admin")) == 1
    assert len(users.list_users(state="inactive")) == 0
    assert users.list_users(sort="newest")[0]["name"] == "Kiran K"
    assert users.count_users_per_role()["SalesExecutive"] == 3


def test_customer_create_edit_delete_and_activity():
    rahul = user("sales@acxiom.test")
    form = {"name": "New Customer", "email": "NEW@Example.test", "phone": "9000000055", "company": "", "address": "",
            "city": "Pune", "state": "MH", "status": "Active", "owner_id": rahul["id"], "notes": "hi"}
    customer_id = records.save_record("customers", form, rahul)
    customer = records.find_record("customers", customer_id, rahul)
    assert customer["email"] == "new@example.test" and customer["code"] == f"CUS-{1000 + customer_id}"
    records.save_record("customers", {**form, "status": "Inactive"}, rahul, customer_id)

    activity_id = records.save_record("activities", {
        "name": "Visit", "type": "Meeting", "due_date": today_in_india(), "status": "Pending",
        "customer_id": customer_id, "lead_id": None, "owner_id": rahul["id"]}, rahul)
    followups, activities, opportunities = records.get_linked_records("customers", customer_id, rahul)
    assert [row["id"] for row in activities] == [activity_id] and followups == [] and opportunities == []
    records.mark_done("activities", activity_id, rahul)

    with pytest.raises(CrmError):
        records.delete_record("customers", customer_id, rahul)
    records.delete_record("activities", activity_id, rahul)
    records.delete_record("customers", customer_id, rahul)
    with pytest.raises(CrmError, match="not found"):
        records.find_record("customers", customer_id, rahul)


def test_filters_sorting_and_due_count():
    manager, rahul = user("manager@acxiom.test"), user("sales@acxiom.test")
    deals = records.get_records("opportunities", manager, sort="amount")
    assert deals[0]["amount"] == max(row["amount"] for row in deals)
    assert all(row["stage"] == "Proposal" for row in records.get_records("opportunities", manager, stage="Proposal"))
    assert len(records.get_records("followups", manager, status="Overdue")) == 1
    assert all(row["type"] == "Call" for row in records.get_records("followups", manager, activity_type="Call"))
    assert len(records.get_records("customers", manager, search="kochi")) == 0          # city is not searched
    assert len(records.get_records("customers", manager, search="malabar")) == 1         # company is
    assert records.get_records("leads", manager, sort="name")[0]["name"] == "Aditya Patel"
    assert records.count_due_followups(rahul) == 2
    assert [row["name"] for row in records.get_assignable_users(rahul)] == ["Rahul Verma"]
    assert len(records.get_assignable_users(manager)) == 2


def test_period_dates_and_every_report_for_every_role():
    from logic.dashboard_numbers import period_dates
    today = today_in_india()
    assert period_dates("all") == (None, None)
    assert period_dates("today") == (today, today)
    assert period_dates("month") == (today.replace(day=1), today)
    assert period_dates("week")[0].weekday() == 0
    for email in ("admin@acxiom.test", "manager@acxiom.test", "sales@acxiom.test"):
        someone = user(email)
        build_dashboard(someone, today.replace(day=1), today)
        for name in reports.reports_for(someone):
            for sort in ("newest", "oldest", "name"):
                headings, rows = reports.build_report(name, someone, search="a", sort=sort,
                                                      from_date=today.replace(day=1), to_date_=today)
                assert all(len(row) == len(headings) for row in rows)
    with pytest.raises(PermissionError):
        reports.build_report("audit", user("sales@acxiom.test"))
