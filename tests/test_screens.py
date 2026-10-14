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
