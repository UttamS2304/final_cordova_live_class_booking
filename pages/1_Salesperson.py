import streamlit as st
from datetime import date, timedelta
import pandas as pd

from backend import (
    pick_teacher,
    exists_booking,
    record_booking,
    get_bookings_for_salesperson,
    send_confirmation_emails,
)

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
            st.session_state["salesperson_name"] = name.strip()
            st.session_state["salesperson_number"] = phone.strip()
            st.session_state["salesperson_email"] = email.strip()
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
# Constants (with 'Select …' placeholders)
# -------------------------
TODAY = date.today()
MAX_DAY = TODAY + timedelta(days=60)

SLOTS = [
    "— Select slot —",
    "10:00–10:40", "10:40–11:20", "11:20–12:00",
    "12:20–13:00", "13:00–13:40", "13:40–14:20",
    "14:20–15:00", "15:00–15:40",
]

SUBJECTS = [
    "— Select subject —",
    "Hindi", "Mathematics", "GK", "SST", "Science", "English",
    "Pre Primary", "EVS", "Computer",
]

CURRICULA = [
    "— Select curriculum —",
    "CBSE", "ICSE", "State Board", "Other",
]

BOOKING_TYPES = ["Live Class", "Product Training"]

# -------------------------
# Booking Form
# -------------------------
st.title("📅 Create a Booking")

with st.form("booking_form", clear_on_submit=False):
    col1, col2 = st.columns(2)

    with col1:
        booking_type = st.selectbox("Booking Type", BOOKING_TYPES, index=0)
        school_name  = st.text_input("School Name", placeholder="e.g., Springdale Public School")
        title_used   = st.text_input("Title Used by School", placeholder="e.g., Cordova EVS Series")
        curriculum   = st.selectbox("Curriculum", CURRICULA, index=0)
        subject      = st.selectbox("Subject", SUBJECTS, index=0)
        picked_date  = st.date_input("Date", value=TODAY, min_value=TODAY, max_value=MAX_DAY, format="YYYY-MM-DD")
        slot         = st.selectbox("Slot", SLOTS, index=0)

    with col2:
        grade = (
            st.text_input("Grade (Live Class only)", placeholder="e.g., 3")
            if booking_type == "Live Class" else None
        )
        topic = st.text_input("Topic (optional)", placeholder="e.g., Fractions basics / Reading practice")

        st.text_input("Salesperson Name", value=st.session_state["salesperson_name"], disabled=True)
        st.text_input("Salesperson Number", value=st.session_state["salesperson_number"], disabled=True)
        st.text_input("Salesperson Email", value=st.session_state["salesperson_email"], disabled=True)

    submit = st.form_submit_button("Book Session", type="primary")

# -------------------------
# Submission Handling
# -------------------------
def invalid(msg: str) -> bool:
    st.error(msg)
    return True

if submit:
    # Required-field validation
    if not school_name.strip(): invalid("School Name is required.")
    elif curriculum == CURRICULA[0]: invalid("Please select a curriculum.")
    elif subject == SUBJECTS[0]: invalid("Please select a subject.")
    elif slot == SLOTS[0]: invalid("Please select a slot.")
    elif booking_type == "Live Class" and (not grade or not grade.strip()):
        invalid("Grade is required for Live Class.")
    # Duplicate guard
    elif exists_booking(school_name.strip(), subject, str(picked_date), slot):
        st.warning("A booking already exists for this School, Subject, Date and Slot.")
    else:
        # Smart teacher pick (respects unavailability)
        teacher = pick_teacher(subject, str(picked_date), slot)
        if not teacher:
            st.error("No teacher available for this subject/date/slot.")
        else:
            data = {
                "booking_type": booking_type,
                "school_name": school_name.strip(),
                "title_used": title_used.strip(),
                "grade": grade.strip() if (booking_type == "Live Class" and grade) else None,
                "curriculum": curriculum,
                "subject": subject,
                "date": str(picked_date),
                "slot": slot,
                "topic": (topic or "").strip(),
                "salesperson_name": st.session_state["salesperson_name"],
                "salesperson_number": st.session_state["salesperson_number"],
                "salesperson_email": st.session_state["salesperson_email"],
                "teacher": teacher,
            }
            try:
                record_booking(data)
                # Non-blocking emails (Salesperson + Teacher + Admin)
                send_confirmation_emails(data)
                st.success(f"✅ Booked! Teacher: {teacher} | {subject} | {data['date']} {slot}")
                st.rerun()  # refresh "My Bookings"
            except Exception as e:
                st.exception(e)

# -------------------------
# My Bookings
# -------------------------
st.divider()
st.subheader("📋 My Bookings")

my_rows = get_bookings_for_salesperson(st.session_state["salesperson_email"])
if not my_rows:
    st.info("No bookings found.")
else:
    st.dataframe(pd.DataFrame(my_rows), use_container_width=True, hide_index=True)

# Footer
st.markdown("<hr style='opacity:.2'>", unsafe_allow_html=True)
st.caption("Made by Utt@m for Cordova Publications 2025")
