import streamlit as st
import pandas as pd
from datetime import date
from backend import (
    get_all_bookings, delete_booking,
    mark_unavailable, list_unavailability, delete_unavailability,
    send_cancellation_emails
)

st.set_page_config(page_title="Admin Dashboard", page_icon="🔐", layout="wide")

# --- Admin Gate (same as before) ---
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
            st.success("Logged in as Admin.")
            st.rerun()
        else:
            st.error("Invalid admin credentials.")

if not admin_logged_in():
    admin_login_form()
    st.stop()

with st.sidebar:
    if st.button("Logout", use_container_width=True):
        st.session_state.clear()
        st.success("Logged out.")
        st.rerun()

st.title("Admin Dashboard")

tab_view, tab_unavail, tab_analytics = st.tabs(
    ["📋 View & Delete Bookings", "🧑‍🏫 Teacher Unavailability", "📈 Analytics (Coming Soon)"]
)

# =========================
# 📋 View & Delete Bookings
# =========================
with tab_view:
    rows = get_all_bookings()
    if not rows:
        st.info("No bookings found.")
    else:
        df = pd.DataFrame(rows)

        # Filters
        with st.expander("Filters", expanded=False):
            c1, c2, c3, c4 = st.columns(4)
            subj = c1.selectbox("Subject", ["(All)"] + sorted(df["Subject"].dropna().unique().tolist()))
            sp   = c2.selectbox("Salesperson", ["(All)"] + sorted(df["Salesperson"].dropna().unique().tolist()))
            sch  = c3.selectbox("School", ["(All)"] + sorted(df["School"].dropna().unique().tolist()))
            day  = c4.date_input("Date", value=None, format="YYYY-MM-DD")

        fdf = df.copy()
        if subj != "(All)": fdf = fdf[fdf["Subject"] == subj]
        if sp   != "(All)": fdf = fdf[fdf["Salesperson"] == sp]
        if sch  != "(All)": fdf = fdf[fdf["School"] == sch]
        if isinstance(day, date):
            fdf = fdf[fdf["Date"] == str(day)]

        st.subheader("All Bookings")
        st.dataframe(
            fdf.drop(columns=["id"]),  # hide internal id
            use_container_width=True,
            hide_index=True
        )

        st.divider()
        st.subheader("Delete a Booking")

        if fdf.empty:
            st.info("No rows to delete based on current filters.")
        else:
            # Build a readable label
            fdf["label"] = (
                fdf["id"].astype(str) + " | " + fdf["School"] + " | " + fdf["Subject"] + " | " +
                fdf["Date"] + " " + fdf["Slot"] + " | " + fdf["Teacher"]
            )
            choice = st.selectbox("Select booking to delete", fdf["label"].tolist())
            chosen_id = int(choice.split(" | ", 1)[0])
            chosen_row = fdf[fdf["id"] == chosen_id].iloc[0].to_dict()

            colA, colB = st.columns([1,2])
            with colA:
                if st.button("Delete Booking ❌", type="primary", use_container_width=True):
                    try:
                        # send emails first (non-blocking), then delete
                        send_cancellation_emails(chosen_row)
                        delete_booking(chosen_id)
                        st.success("Booking deleted and cancellation emails triggered.")
                        st.rerun()
                    except Exception as e:
                        st.exception(e)
            with colB:
                st.write("**Preview:**")
                st.json({k: chosen_row[k] for k in ["School","Subject","Date","Slot","Teacher","Salesperson"]})

# ===============================
# 🧑‍🏫 Teacher Unavailability
# ===============================
with tab_unavail:
    st.subheader("Mark Teacher Unavailable")
    # Teacher list derived from existing bookings + any manual entry
    existing_teachers = sorted({r["Teacher"] for r in rows} if rows else [])
    c1, c2, c3 = st.columns(3)
    teacher = c1.selectbox("Teacher", existing_teachers + ["(Type name manually)"])
    manual  = c1.text_input("Or type teacher name", value="") if teacher == "(Type name manually)" else ""
    day     = c2.date_input("Date", value=date.today(), format="YYYY-MM-DD")
    slot    = c3.selectbox("Slot (optional = full day)", ["(Full Day)",
        "10:00–10:40","10:40–11:20","11:20–12:00","12:20–13:00",
        "13:00–13:40","13:40–14:20","14:20–15:00","15:00–15:40"
    ])

    sel_teacher = manual.strip() if manual else teacher
    if st.button("Mark Unavailable", use_container_width=False, type="primary"):
        if not sel_teacher or sel_teacher == "(Type name manually)":
            st.error("Please select or type a teacher name.")
        else:
            try:
                mark_unavailable(sel_teacher, str(day), None if slot == "(Full Day)" else slot)
                st.success(f"Marked {sel_teacher} unavailable on {day} {'' if slot=='(Full Day)' else slot}.")
                st.rerun()
            except Exception as e:
                st.exception(e)

    st.divider()
    st.subheader("Current Unavailability")
    urows = list_unavailability()
    if not urows:
        st.info("No unavailability entries.")
    else:
        udf = pd.DataFrame(urows)
        st.dataframe(udf[["Teacher","Date","Slot"]], use_container_width=True, hide_index=True)
        # delete control
        labels = [f"{r['id']} | {r['Teacher']} | {r['Date']} | {r['Slot'] or 'Full Day'}" for r in urows]
        pick = st.selectbox("Remove entry", labels)
        unavail_id = int(pick.split(" | ", 1)[0])
        if st.button("Unmark (Delete Entry) ✅", use_container_width=False):
            try:
                delete_unavailability(unavail_id)
                st.success("Unavailability removed.")
                st.rerun()
            except Exception as e:
                st.exception(e)

# ===============================
# 📈 Analytics (Coming Soon)
# ===============================
with tab_analytics:
    st.info("Charts coming soon: bookings by subject/teacher, peak slots, cancellations, fulfillment rates.")
