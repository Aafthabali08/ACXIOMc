# AcxiomCRM (Streamlit version)

A simple CRM (Customer Relationship Management) prototype written in Python with Streamlit and SQLite.
It has three roles: **Admin**, **Manager** and **Sales Executive**. Together they manage customers, leads,
opportunities, follow-ups and activities.

## How to run

```bash
pip install -r requirements.txt
streamlit run app.py
```

Open http://localhost:8501. On the first start the app creates `crm_data.db` and fills it with demo data.
To start fresh, delete `crm_data.db` and run the app again.

### Demo accounts (password for all: `Acxiom@123`)

| Role | Email |
| --- | --- |
| Admin | admin@acxiom.test |
| Manager | manager@acxiom.test |
| Sales Executive | sales@acxiom.test |
| Sales Executive | sales2@acxiom.test |

### Run the tests

```bash
python -m pytest tests
```

## Folder structure

```
app.py                  Start here. Login check, sidebar menu per role, picks which page to show.

logic/                  Plain Python. No Streamlit code in here.
  settings.py           Fixed lists (roles, statuses, stages) and small helpers (dates, ₹ format).
  database.py           SQLite connection and the CREATE TABLE statements.
  auth.py               Password hashing, login with lockout, register, change password.
  users.py              Admin user management (add, edit, role change, unlock).
  records.py            The main CRM rules: list, filter, save, delete, mark done, convert lead.
  dashboard_numbers.py  Numbers for the dashboards and the team performance table.
  reports.py            The 8 reports and CSV export.
  audit.py              Writes the history (audit log) of every change.
  sample_data.py        Demo users and records created on first start.

screens/                One file per page. Only Streamlit UI code.
  helpers.py            Shared bits: switching pages, messages, tables, period filter.
  login_page.py         Log in and Register tabs.
  dashboard_page.py     The dashboard (different sections for each role).
  records_page.py       List / details / add / edit for all five CRM modules.
  team_page.py          Team performance (Admin, Manager).
  reports_page.py       Reports with filters and CSV download.
  search_page.py        Search across all modules.
  users_page.py         Users & access, add/edit user, roles (Admin).
  profile_page.py       My profile: change name and password.

tests/test_crm_rules.py Tests for the business rules.
.streamlit/config.toml  Plain light theme.
```

**Main idea:** `screens/` only *shows* things, and `logic/` *decides* things. When you click Save, the screen
gathers the form values into a dictionary and calls a function in `logic/records.py`. If a rule fails, that
function raises `CrmError("message")`, and the screen shows the message in red.

## How it works (for explaining)

1. **Every click reruns `app.py` from top to bottom.** That is how Streamlit works. Values that must survive a
   rerun live in `st.session_state`:
   - `user_id`: who is logged in
   - `page`: which page is open, e.g. `("records", "leads")`
   - `record_mode` / `record_id`: list, details, edit or new, and which record
2. **Login** (`logic/auth.py`): passwords are stored as salted PBKDF2 hashes, never as plain text. Five wrong
   passwords lock the account for 15 minutes. An Admin can unlock it.
3. **Roles**: the sidebar menu differs per role (`ADMIN_MENU`, `MANAGER_MENU`, `SALES_EXECUTIVE_MENU` in
   `app.py`). The real protection sits in `logic/`:
   - `load_records()` only returns a Sales Executive's own records.
   - Reports check `can_open()`.
   - The user pages check the role in `show_page()`.
4. **Soft delete**: deleting sets `deleted = 1`, so the row stays in the database for history. A record that other
   records point to cannot be deleted.
5. **Audit log**: `add_audit_entry()` writes one row per login, create, update, delete, status change and convert.

## Business rules (all in `logic/records.py`)

- Records are assigned to an active Sales Executive. A Sales Executive can only assign to themselves.
- Customers and leads need a valid email and a 10-digit Indian mobile number (starting with 6–9).
  Customer email and phone must be unique, including deleted customers.
- Lead status moves New → Contacted → Qualified (or Unqualified / Lost). A new lead always starts as New.
- **Convert lead** works only on a Qualified lead. It creates a customer, plus an opportunity when the expected
  value is above 0. Converted leads are read-only.
- Opportunity amount must be above 0. An open opportunity's close date cannot be in the past. Won needs 100%
  probability and Lost needs 0%. Status follows the stage.
- A follow-up or activity is linked to exactly one customer, lead or opportunity owned by the same person.
  A planned follow-up cannot be in the past. "Overdue" means Planned with a past date.
- Completing a follow-up for a New lead moves that lead to Contacted.
- All date rules use the Indian date (UTC+5:30).

## Where to change things

| I want to... | Change |
| --- | --- |
| Add a status, stage, priority or activity type | `logic/settings.py` |
| Change a validation rule | `validate_...` functions in `logic/records.py` |
| Add a field to customers | `database.py` (table), `MODULE_COLUMNS` in `records.py`, the form in `screens/records_page.py` |
| Change the sidebar menu | `ADMIN_MENU` / `MANAGER_MENU` / `SALES_EXECUTIVE_MENU` in `app.py` |
| Add a report | `REPORTS` and `build_report()` in `logic/reports.py` |
| Change lockout settings | `MAX_FAILED_LOGINS` / `LOCK_MINUTES` in `logic/settings.py` |
| Change the demo data | `logic/sample_data.py`, then delete `crm_data.db` |

## Differences from the old ASP.NET version

This is a simplified prototype. The following were left out on purpose:

- The JSON API (Streamlit apps do not serve APIs).
- IP addresses in the audit log.
- Per-IP rate limiting on login. Account lockout is still there.
- Signing out other sessions after a password change. A deactivated user is still logged out on their next click.
- Record IDs are simple numbers instead of GUIDs.
- Multi-step actions such as lead conversion are no longer wrapped in one database transaction.

The old C# code is still in git history (commit `c3a5caf`) if you ever need it.
