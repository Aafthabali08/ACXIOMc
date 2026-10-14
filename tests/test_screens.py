"""
Screen tests: open the real Streamlit app (without a browser), log in as each role,
click every sidebar link and use the main buttons. Fails if any page shows an error.

Run with:   python -m pytest tests
"""

import pytest
from streamlit.testing.v1 import AppTest

from logic import auth, database, records
from logic.sample_data import create_sample_data_if_empty


@pytest.fixture(autouse=True)
def fresh_database(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_FILE", tmp_path / "test.db")
    database.create_tables()
    create_sample_data_if_empty()


def logged_in_app(email):
    app = AppTest.from_file("../app.py", default_timeout=30)
    app.session_state["user_id"] = auth.find_user_by_email(email)["id"]
    app.run()
    return app


def click(app, label):
    [button for button in app.button if button.label == label][0].click().run()


def assert_no_errors(app, where):
    assert not app.exception, f"{where}: {app.exception[0].message if app.exception else ''}"
    assert not app.error, f"{where}: {[error.value for error in app.error]}"


def test_login_page_logs_in():
    app = AppTest.from_file("../app.py", default_timeout=30).run()
    app.text_input[0].input("manager@acxiom.test")
    app.text_input[1].input("Acxiom@123")
    click(app, "Log in")
    assert app.title[0].value == "Sales Manager dashboard"


@pytest.mark.parametrize("email", ["admin@acxiom.test", "manager@acxiom.test", "sales@acxiom.test"])
def test_every_menu_link_opens_without_errors(email):
    app = logged_in_app(email)
    menu_labels = [button.label for button in app.sidebar.button if button.label != "Log out"]
    assert len(menu_labels) >= 9
    for label in menu_labels:
        click(app, label)
        assert_no_errors(app, label)


def test_every_dashboard_period_works():
    app = logged_in_app("admin@acxiom.test")
    for index in range(4):   # All time, Today, This week, This month
        app.selectbox(key="dashboard_period").select_index(index).run()
        assert_no_errors(app, f"period {index}")


def test_add_lead_through_the_form():
    app = logged_in_app("sales@acxiom.test")
    click(app, "My leads")
    click(app, "Add lead")
    app.text_input[0].input("Screen Lead")
    app.text_input[1].input("screen.lead@example.test")
    app.text_input[2].input("9000000077")
    click(app, "Save")
    assert_no_errors(app, "save lead")
    assert app.title[0].value == "Screen Lead"


def test_form_shows_rule_errors():
    app = logged_in_app("sales@acxiom.test")
    click(app, "My leads")
    click(app, "Add lead")
    app.text_input[0].input("Bad Lead")
    app.text_input[1].input("bad@example.test")
    app.text_input[2].input("123")
    click(app, "Save")
    assert app.error[0].value == "Enter a valid 10-digit Indian mobile number."


def test_open_details_convert_and_edit():
    app = logged_in_app("sales@acxiom.test")
    click(app, "My leads")
    app.selectbox(key="leads_picker").set_value("Aditya Patel (#3)").run()
    click(app, "Open")
    click(app, "Convert lead")
    assert_no_errors(app, "convert")
    assert "Customers" in app.caption[0].value
    click(app, "Edit")
    click(app, "Save")
    assert_no_errors(app, "edit customer")


def test_report_filters_and_csv_button():
    app = logged_in_app("admin@acxiom.test")
    click(app, "Audit log")
    app.radio[0].set_value("oldest").run()
    app.text_input[0].input("Login").run()
    assert_no_errors(app, "audit report")


# Saving the user form and the profile form is checked in the browser instead:
# Streamlit 1.32's AppTest replays the button press after st.rerun() there.
# The logic behind them is tested in test_crm_rules.py.


def test_search_finds_records():
    app = logged_in_app("sales@acxiom.test")
    click(app, "Search")
    app.text_input[0].input("Karthik").run()
    assert_no_errors(app, "search")
    assert any("Customers" in header.value for header in app.subheader)


def test_mark_done_from_dashboard():
    app = logged_in_app("sales@acxiom.test")
    rahul = auth.find_user_by_email("sales@acxiom.test")
    before = records.count_due_followups(rahul)
    [button for button in app.button if button.label == "Mark done"][0].click().run()
    assert records.count_due_followups(rahul) == before - 1


def test_log_out():
    app = logged_in_app("sales@acxiom.test")
    click(app, "Log out")
    assert app.title[0].value == "AcxiomCRM"


# ---------- Extra checks: every module, every report, empty accounts, paging ----------

def open_page(email, page, mode="list", record_id=None):
    app = AppTest.from_file("../app.py", default_timeout=30)
    app.session_state["user_id"] = auth.find_user_by_email(email)["id"]
    app.session_state["page"] = page
    app.session_state["record_mode"] = mode
    app.session_state["record_id"] = record_id
    app.session_state["record_preset"] = {}
    return app.run()


@pytest.mark.parametrize("module", ["customers", "leads", "opportunities", "followups", "activities"])
@pytest.mark.parametrize("mode", ["details", "edit", "new"])
def test_details_edit_and_new_pages_for_every_module(module, mode):
    manager = auth.find_user_by_email("manager@acxiom.test")
    record_id = records.get_records(module, manager)[0]["id"]
    app = open_page("manager@acxiom.test", ("records", module), mode, record_id)
    assert_no_errors(app, f"{module} {mode}")


@pytest.mark.parametrize("report", ["pipeline", "conversion", "customers", "leads", "opportunities",
                                    "followups", "user-activity", "audit"])
def test_every_report_page(report):
    app = open_page("admin@acxiom.test", ("reports", report))
    assert_no_errors(app, report)
    for sort in ["oldest", "name"]:
        app.radio[0].set_value(sort).run()
        assert_no_errors(app, f"{report} {sort}")


def test_sales_executive_cannot_open_admin_pages():
    for page in [("users", None), ("team", None)]:
        app = open_page("sales@acxiom.test", page)
        assert app.error[0].value == "You do not have access to this page."


def test_brand_new_account_with_no_records():
    auth.register("Fresh User", "fresh@example.test", "Fresh@123", "Fresh@123")
    app = logged_in_app("fresh@example.test")
    for label in [button.label for button in app.sidebar.button if button.label != "Log out"]:
        click(app, label)
        assert_no_errors(app, label)


def test_custom_period_needs_both_dates():
    app = logged_in_app("manager@acxiom.test")
    app.selectbox(key="dashboard_period").select_index(4).run()   # Custom range
    assert app.warning[0].value == "Select both dates for a custom range."


def test_page_number_resets_when_filter_shrinks_the_list():
    rahul = auth.find_user_by_email("sales@acxiom.test")
    for number in range(20):   # 5 demo leads + 20 = 25 leads = 3 pages
        records.save_record("leads", {
            "name": f"Paging Lead {number}", "email": f"paging{number}@example.test", "phone": f"90000001{number:02d}",
            "company": "", "source": "", "priority": "Normal", "expected_value": 0.0, "status": "New",
            "owner_id": rahul["id"], "notes": ""}, rahul)
    app = open_page("sales@acxiom.test", ("records", "leads"))
    app.number_input(key="leads_page").set_value(3).run()
    assert_no_errors(app, "page 3")
    app.text_input(key="leads_search").input("Paging Lead 1").run()   # 11 matches -> only 2 pages
    assert_no_errors(app, "after search")


def test_delete_through_the_details_page():
    rahul = auth.find_user_by_email("sales@acxiom.test")
    activity = records.get_records("activities", rahul)[0]
    app = open_page("sales@acxiom.test", ("records", "activities"), "details", activity["id"])
    app.checkbox(key=f"confirm_delete_activities_{activity['id']}").check().run()
    click(app, "Delete")
    with pytest.raises(records.CrmError):
        records.find_record("activities", activity["id"], rahul)
