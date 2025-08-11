# pages/2_Admin.py — Admin + Email Log with robust backend import

from __future__ import annotations
import streamlit as st
import sys, os, traceback, importlib.util
from pathlib import Path
from datetime import date

# ---------- Robust import of backend.py ----------
ROOT = Path(__file__).resolve().parents[1]
BACKEND_FILE = ROOT / "backend.py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def _bind_from(mod):
    # bookings
    globals()["get_all_bookings"] = mod.get_all_bookings
    globals()["delete_booking"] = mod.delete_booking
    # unavailability
    globals()["mark_unavailable"] = mod.mark_unavailable
    globals()["list_unavailability"] = mod.list_unavailability
    globals()["delete_unavailability"] = mod.delete_unavailability
    # emails
    globals()["send_cancellation_emails"] = mod.send_cancellation_emails
    globals()["get_email_events"] = mod.get_email_events
    globals()["resend_email"] = mod.resend_email

try:
    import backend as _bk
    _bind_from(_bk)
except Exception:
    try:
        if BACKEND_FILE.exists():
            spec = importlib.util.spec_from_file_location("backend", str(BACKEND_FILE))
            _bk = importlib.util.module_from_spec(spec)
            sys.modules["backend"] = _bk
            assert spec.loader is not None
            spec.loader.exec_module(_bk)
            _bind_from(_bk)
        else:
            raise ImportError(f"backend.py not found at {BACKEND_FILE}")
    except Exception as e:
        st.error("Failed to import backend.py. Ensure the file exists in the repo root.")
        st.code("".join(traceback.format_exception_only(type(e), e)))
        st.stop()

# ---------- Page config & chrome ----------
st.set_page_config(page_title="Admin Dashboard", page_icon="🔐", layout="wide")
st.markdown("""
<style>
#MainMenu, footer, header {visibility: hidden;}
[data-testid="stDecoration"] {display: none;}
.block-container {padding-top: 1.25rem; padding-bottom: 1.25rem;}
</style>
""", unsafe_allow_html=True)

# ---------- Admin auth ----------
def admin_logged_in():
    return st.session_state.get("role") == "admin"

def admin_login_form():
    st.title("Admin Login")
    with st.form("admin_login", clear_on_submit=False):
        u = st.text_input("Username", autocomplete="username")
        p = st.text_input("Password", type="password", autocomplete="current-password")
        ok = st.form_submit_button("Login")
    if ok:
        if u == st.secrets.get("ADMIN_USERNAME") and p == st.secrets.get("ADMIN_PASSWORD"):
            st.session_state["role"] = "admin"
            st.rerun()
        else:
            st.error("Invalid admin credentials.")

if not admin_logged_in():
    admin_login_form()
    st.stop()

with st.sidebar:
    if st.button("Logout", use_container_width=True):
        st.session_state.clear()
        st.rerun()

st.title("Admin Dashboard")

tab_view, tab_unavail, tab_email = st.tabs(
    ["📋 View & Delete Bookings", "🧑‍🏫 Teacher Unavailability", "📧 Email Log"]
)

# =======================
# 📋 View & Delete Bookings
# =======================
with tab_view:
    rows = get_all_bookings()
    if not rows:
        st.info("No bookings found.")
    else:
        import pandas as pd
        df = pd.DataFrame(rows)

        cA, cB, cC = st.columns(3)
        cA.metric("Total bookings", len(df))
        cB.metric("Unique schools", df["School"].nunique())
        cC.metric("Unique teachers", df["Teacher"].nunique())

        with st.expander("Filters", expanded=False):
            f1, f2, f3, f4 = st.columns(4)
            subj = f1.selectbox("Subject", ["(All)"] + sorted(df["Subject"].dropna().unique().tolist()))
            sp   = f2.selectbox("Salesperson", ["(All)"] + sorted(df["Salesperson"].dropna().unique().tolist()))
            sch  = f3.selectbox("School", ["(All)"] + sorted(df["School"].dropna().unique().tolist()))
            day  = f4.date_input("Date", value=None, format="YYYY-MM-DD")
            query = st.text_input("Search", placeholder="School / Subject / Teacher").strip().lower()

        fdf = df.copy()
        if subj != "(All)": fdf = fdf[fdf["Subject"] == subj]
        if sp   != "(All)": fdf = fdf[fdf["Salesperson"] == sp]
        if sch  != "(All)": fdf = fdf[fdf["School"] == sch]
        if isinstance(day, date): fdf = fdf[fdf["Date"] == str(day)]
        if query:
            mask = (
                fdf["School"].str.lower().str.contains(query, na=False) |
                fdf["Subject"].str.lower().str.contains(query, na=False) |
                fdf["Teacher"].str.lower().str.contains(query, na=False)
            )
            fdf = fdf[mask]

        st.subheader("All Bookings")
        page_size = st.slider("Rows per page", 10, 100, 25, key="pg_size")
        pages = max(1, (len(fdf) + page_size - 1) // page_size)
        page = st.number_input("Page", 1, pages, 1, key="pg_no")
        start = (page - 1) * page_size
        view_df = fdf.drop(columns=["id"]).iloc[start:start + page_size]
        st.dataframe(view_df, use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("Delete a Booking")

        if fdf.empty:
            st.info("No rows to delete based on current filters.")
        else:
            fdf["label"] = (
                fdf["id"].astype(str) + " | " + fdf["School"] + " | " + fdf["Subject"] + " | " +
                fdf["Date"] + " " + fdf["Slot"] + " | " + fdf["Teacher"]
            )
            choice = st.selectbox("Select booking", fdf["label"].tolist(), key="del_choice")
            chosen_id = int(choice.split(" | ", 1)[0])
            chosen_row = fdf[fdf["id"] == chosen_id].iloc[0].to_dict()

            confirm_key = "confirm_delete_open"
            if st.button("Delete Booking ❌", type="primary"):
                st.session_state[confirm_key] = True

            if st.session_state.get(confirm_key):
                st.warning("This will delete the booking and trigger cancellation emails.")
                st.json({k: chosen_row[k] for k in ["School","Subject","Date","Slot","Teacher","Salesperson"]})
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Yes, delete", type="primary", use_container_width=True, key="confirm_del_yes"):
                        try:
                            send_cancellation_emails(chosen_row)  # send emails first
                            delete_booking(chosen_id)
                            st.session_state[confirm_key] = False
                            st.success("Booking deleted and cancellation emails triggered.")
                            st.rerun()
                        except Exception as e:
                            st.session_state[confirm_key] = False
                            st.exception(e)
                with c2:
                    if st.button("Cancel", use_container_width=True, key="confirm_del_no"):
                        st.session_state[confirm_key] = False
                        st.info("Deletion cancelled.")

# =======================
# 🧑‍🏫 Teacher Unavailability
# =======================
with tab_unavail:
    st.subheader("Mark Teacher Unavailable")

    from teacher_mapping import TEACHER_MAP
    all_from_map = {t for lst in TEACHER_MAP.values() for t in lst}
    rows_for_teachers = get_all_bookings()
    all_from_bookings = {r["Teacher"] for r in rows_for_teachers} if rows_for_teachers else set()

    def prettify_key(k: str) -> str:
        s = k.upper().replace("_MAAM", " Ma'am").replace("_SIR", " Sir").replace("_", " ").title()
        return s.replace("Ma'Am", "Ma'am")

    all_from_secrets = {prettify_key(k) for k in st.secrets.get("TEACHER_EMAILS", {}).keys()}
    teacher_options = sorted(all_from_map | all_from_bookings | all_from_secrets)

    colA, colB, colC = st.columns(3)
    teacher = colA.selectbox("Teacher", ["— Select teacher —"] + teacher_options + ["(Type name manually)"])
    manual  = colA.text_input("Or type teacher name", value="") if teacher == "(Type name manually)" else ""
    day     = colB.date_input("Date", value=date.today(), format="YYYY-MM-DD")
    slot    = colC.selectbox("Slot (optional = full day)", ["(Full Day)",
        "10:00–10:40","10:40–11:20","11:20–12:00","12:20–13:00",
        "13:00–13:40","13:40–14:20","14:20–15:00","15:00–15:40"
    ])

    chosen_teacher = (manual.strip() if teacher == "(Type name manually)" else teacher)
    if st.button("Mark Unavailable", type="primary"):
        if (not chosen_teacher) or (chosen_teacher == "— Select teacher —") or (teacher == "(Type name manually)" and not manual.strip()):
            st.error("Please select or type a teacher name.")
        else:
            try:
                mark_unavailable(chosen_teacher, str(day), None if slot == "(Full Day)" else slot)
                st.success(f"Marked {chosen_teacher} unavailable on {day} "
                           f"{'(full day)' if slot == '(Full Day)' else slot}.")
                st.rerun()
            except Exception as e:
                st.exception(e)

    st.divider()
    st.subheader("Current Unavailability")
    urows = list_unavailability()
    if not urows:
        st.info("No unavailability entries.")
    else:
        import pandas as pd
        udf = pd.DataFrame(urows)
        st.dataframe(udf[["Teacher","Date","Slot"]], use_container_width=True, hide_index=True)

        labels = [f"{r['id']} | {r['Teacher']} | {r['Date']} | {r['Slot'] or 'Full Day'}" for r in urows]
        to_remove = st.selectbox("Remove entry", labels, key="unavail_pick")
        unavail_id = int(to_remove.split(" | ", 1)[0])

        u_confirm_key = "confirm_unavail_delete_open"
        if st.button("Unmark (Delete Entry) ✅"):
            st.session_state[u_confirm_key] = True

        if st.session_state.get(u_confirm_key):
            st.warning("Remove this unavailability entry?")
            st.write(to_remove)
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Yes, remove", type="primary", use_container_width=True, key="u_confirm_yes"):
                    try:
                        delete_unavailability(unavail_id)
                        st.session_state[u_confirm_key] = False
                        st.success("Unavailability removed.")
                        st.rerun()
                    except Exception as e:
                        st.session_state[u_confirm_key] = False
                        st.exception(e)
            with c2:
                if st.button("Cancel", use_container_width=True, key="u_confirm_no"):
                    st.session_state[u_confirm_key] = False
                    st.info("Removal cancelled.")

# =======================
# 📧 Email Log (view + resend)
# =======================
with tab_email:
    st.subheader("Email Log (latest 200)")
    import pandas as pd
    events = get_email_events(200)
    if not events:
        st.info("No email events yet.")
    else:
        df = pd.DataFrame(events)
        st.dataframe(df, use_container_width=True, hide_index=True)

        ids = [f"{r['id']} | {r['ts']} | {r['to']} | {r['status']}" for r in events]
        pick = st.selectbox("Select an event to resend", ids, key="resend_pick")
        event_id = int(pick.split(" | ", 1)[0])
        if st.button("Resend selected email"):
            try:
                resend_email(event_id)
                st.success("Resend queued/sent (check Email Log for new entry).")
            except Exception as e:
                st.exception(e)
