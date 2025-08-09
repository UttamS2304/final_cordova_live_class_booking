import streamlit as st
from datetime import date
import pandas as pd

from backend import (
    pick_teacher,
    record_booking,
    get_bookings_for_salesperson,
    send_confirmation_emails
)

# -------------------------
# Page setup
# -------------------------
st.set_page_config(page_title="Salesperson Portal", page_icon="🧑‍💼", layout="wide")

# -------------------------
# Session Login
# -------------------------
def salesperson_logged_in():
    return st.session_state.get("role") == "sales" and st.session_state.get("salesperson_email")

def salesperson_login_form():
    st.title("Salesperson Login")
    with st.form("sp_login", clear_on_submit=False):
        name  = st.text_input("Your Name")
        phone = st.text_input("Your Phone Number")
        email = st.text_input("Your Email")
        ok = st.form_submit_button("Login")
    if ok:
        if not name or not phone or not email:
            st.error("Please fill name, phone, and email.")
        else:
            st.session_state["role"] = "sales"
            st.session_state["salesperson_name"] = name
            st.session_state["salesperson_number"] = phone
            st.session_state["salesperson_email"] = email
            st.success(f"Welcome, {name}!")
            st.rerun()

if not salesperson_logged_in():
    salesperson_login_form()
    st.stop()

with st.sidebar:
    st.caption(f"Logged in as: {st.session_state.get('salesperson_name')}")
    if st.button("Logout", use_container_width=True):
        st.session_state.clear()
        st.success("Logged out.")
        st.rerun()

# -------------------------
# Form Constants
# -------------------------
SLOTS = [
    "10:00–10:40", "10:40–11:20", "11:20–12:00",
    "12:20–13:00", "13:00–13:40", "13:40–14:20",
    "14:20–15:00", "15:00–15:40"
]
SUBJECTS = [
    "Hindi", "Mathematics", "GK", "SST", "Science", "English",
    "Pre Primary", "EVS", "Computer"
]
CURRICULA = ["CBSE", "ICSE", "State Board", "Other"]

# -------------------------
# Booking Form
# -------------------------
st.title("📅 Create a Booking")

with st.form("booking_form", clear_on_submit=False):
    col1, col2 = st.columns(2)

    with col1:
        booking_type = st.selectbox("Booking Type", ["Live Class", "Product Training"])
        school_name  = st.text_input("School Name")
        title_used   = st.text_input("Title Used by School")
        curriculum   = st.selectbox("Curriculum", CURRICULA)
        subject      = st.selectbox("Subject", SUBJECTS)
        picked_date  = st.date_input("Date", value=date.today(), format="YYYY-MM-DD")
        slot         = st.selectbox("Slot", SLOTS)

    with col2:
        if booking_type == "Live Class":
            grade = st.text_input("Grade")
        else:
            grade = None
        topic = st.text_input("Topic (optional)")

        st.text_input("Salesperson Name", value=st.session_state["salesperson_name"], disabled=True)
        st.text_input("Salesperson Number", value=st.session_state["salesperson_number"], disabled=True)
        st.text_input("Salesperson Email", value=st.session_state["salesperson_email"], disabled=True)

    submit = st.form_submit_button("Book Session", type="primary")

# -------------------------
# Submission Handling
# -------------------------
if submit:
    if not school_name or not subject or not slot:
        st.error("Please fill all required fields.")
    elif booking_type == "Live Class" and not grade:
        st.error("Grade is required for Live Class.")
    else:
        teacher = pick_teacher(subject, str(picked_date), slot)
        if not teacher:
            st.error("No teacher available for this subject/date/slot.")
        else:
            data = {
                "booking_type": booking_type,
                "school_name": school_name,
                "title_used": title_used,
                "grade": grade if booking_type == "Live Class" else None,
                "curriculum": curriculum,
                "subject": subject,
                "date": str(picked_date),
                "slot": slot,
                "topic": topic,
                "salesperson_name": st.session_state["salesperson_name"],
                "salesperson_number": st.session_state["salesperson_number"],
                "salesperson_email": st.session_state["salesperson_email"],
                "teacher": teacher,
            }
            try:
                record_booking(data)
                send_confirmation_emails(data)  # Non-blocking emails
                st.success(f"✅ Booked! Teacher: {teacher} | {subject} | {data['date']} {slot}")
            except Exception as e:
                st.exception(e)

# -------------------------
# My Bookings Table
# -------------------------
st.divider()
st.subheader("📋 My Bookings")

my_rows = get_bookings_for_salesperson(st.session_state["salesperson_email"])
if not my_rows:
    st.info("No bookings found.")
else:
    st.dataframe(pd.DataFrame(my_rows), use_container_width=True, hide_index=True)
