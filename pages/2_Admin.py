# pages/2_Admin.py — FINAL

import streamlit as st
import pandas as pd
from datetime import date
from backend import (
    get_all_bookings,
    delete_booking,
    mark_unavailable,
    list_unavailability,
    delete_unavailability,
    send_cancellation_emails,
)

st.set_page_config(page_title="Admin Dashboard", page_icon="🔐", layout="wide")

# -------------------------
# Admin Gate
# -------------------------
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

# ======================================================
# 📋 View & Delete Bookings (filters • search • export)
# ======================================================
with tab_view:
    rows = get_all_bookings()
    if not rows:
        st.info("No bookings found.")
    else:
        df = pd.DataFrame(rows)

        # ------- Quick summary header -------
        left, mid, right = st.columns(3)
        left.metric("Total bookings", len(df))
        mid.metric("Unique schools", df["School"].nunique())
        right.metric("Unique teachers", df["Teacher"].nunique())

        # ------- Filters -------
        with st.expander("Filters", expanded=False):
            c1, c2, c3, c4 = st.columns(4)
            subj = c1.selectbox("Subject", ["(All)"] + sorted(df["Subject"].dropna().unique().tolist()))
            sp   = c2.selectbox("Salesperson", ["(All)"] + sorted(df["Salesperson"].dropna().unique().tolist()))
            sch  = c3.selectbox("School", ["(All)"] + sorted(df["School"].dropna().unique().tolist()))
            day  = c4.date_input("Date", value=None, format="YYYY-MM-DD")
            query = st.text_input("Search (School / Subject / Teacher)", placeholder="type to filter…").strip().lower()

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

        # ------- Pagination -------
        st.subheader("All Bookings")
        page_size = st.slider("Rows per page", 10, 100, 25, key="pg_size")
        pages = max(1, (len(fdf) + page_size - 1) // page_size)
        page = st.number_input("Page", 1, pages, 1, key="pg_no")
        start = (page - 1) * page_size

        view_df = fdf.drop(columns=["id"]).iloc[start:start + page_size]
        st.dataframe(view_df, use_container_width=True, hide_index=True)

        # ------- Export current view -------
        col_dl, _ = st.columns([1, 3])
        with col_dl:
            st.download_button(
                "Download CSV of current view",
                view_df.to_csv(index=False).encode(),
                "bookings_view.csv",
                use_container_width=True,
            )

        st.divider()
        st.subheader("Delete a Booking")

        if fdf.empty:
            st.info("No rows to delete based on current filters.")
        else:
            # Build readable labels
            fdf["label"] = (
                fdf["id"].astype(str) + " | " + fdf["School"] + " | " + fdf["Subject"] + " | " +
                fdf["Date"] + " " + fdf["Slot"] + " | " + fdf["Teacher"]
            )
            choice = st.selectbox("Select booking to delete", fdf["label"].tolist(), key="del_choice")
            chosen_id = int(choice.split(" | ", 1)[0])
            chosen_row = fdf[fdf["id"] == chosen_id].iloc[0].to_dict()

            if st.button("Delete Booking ❌", type="primary"):
                with st.modal("Confirm deletion"):
                    st.write("This will delete the booking and trigger cancellation emails:")
                    st.json({k: chosen_row[k] for k in ["School","Subject","Date","Slot","Teacher","Salesperson"]})
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("Yes, delete", type="primary", use_container_width=True, key="confirm_del"):
                            try:
                                # Fire emails first (non-blocking), then delete
                                send_cancellation_emails(chosen_row)
                                delete_booking(chosen_id)
                                st.success("Booking deleted and cancellation emails triggered.")
                                st.rerun()
                            except Exception as e:
                                st.exception(e)
                    with c2:
                        st.button("Cancel", use_container_width=True, key="cancel_del")

# ======================================================
# 🧑‍🏫 Teacher Unavailability (mark / list / unmark)
# ======================================================
with tab_unavail:
    st.subheader("Mark Teacher Unavailable")

    # Teacher list from existing bookings + manual entry option
    rows_for_teachers = get_all_bookings()
    teacher_options = sorted({r["Teacher"] for r in rows_for_teachers}) if rows_for_teachers else []
    colA, colB, colC = st.columns(3)
    pick = colA.selectbox("Teacher", teacher_options + ["(Type name manually)"])
    manual = colA.text_input("Or type teacher name", value="") if pick == "(Type name manually)" else ""
    day = colB.date_input("Date", value=date.today(), format="YYYY-MM-DD")
    slot = colC.selectbox(
        "Slot (optional = full day)",
        ["(Full Day)",
         "10:00–10:40","10:40–11:20","11:20–12:00",
         "12:20–13:00","13:00–13:40","13:40–14:20",
         "14:20–15:00","15:00–15:40"]
    )

    chosen_teacher = manual.strip() if manual else pick
    if st.button("Mark Unavailable", type="primary"):
        if not chosen_teacher or chosen_teacher == "(Type name manually)":
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
        udf = pd.DataFrame(urows)
        st.dataframe(udf[["Teacher","Date","Slot"]], use_container_width=True, hide_index=True)

        labels = [f"{r['id']} | {r['Teacher']} | {r['Date']} | {r['Slot'] or 'Full Day'}" for r in urows]
        to_remove = st.selectbox("Remove entry", labels, key="unavail_pick")
        unavail_id = int(to_remove.split(" | ", 1)[0])

        if st.button("Unmark (Delete Entry) ✅"):
            try:
                delete_unavailability(unavail_id)
                st.success("Unavailability removed.")
                st.rerun()
            except Exception as e:
                st.exception(e)

# ======================================================
# 📈 Analytics (placeholder)
# ======================================================
with tab_analytics:
    st.info("Charts coming soon: bookings by subject/teacher, peak slots, cancellations, fulfillment rates.")

# Footer
st.markdown("<hr style='opacity:.2'>", unsafe_allow_html=True)
st.caption("Made by Utt@m for Cordova Publications 2025")
