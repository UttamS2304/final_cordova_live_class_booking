# salesperson_portal.py

import streamlit as st
import pandas as pd
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo

from backend import (
    pick_teacher, teacher_busy, exists_booking,
    record_booking, get_bookings_for_salesperson,
    send_confirmation_emails, is_teacher_unavailable
)
from teacher_mapping import candidates_for_subject

# ---------------------------------------------------------------------
# Page setup & light styling
# ---------------------------------------------------------------------
st.set_page_config(page_title="Salesperson Portal", page_icon="🧑‍💼", layout="wide")
st.markdown("""
<style>
#MainMenu, footer, header {visibility: hidden;}
[data-testid="stDecoration"] {display: none;}
.block-container {padding-top: 1.2rem; padding-bottom: 1.2rem;}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------
def salesperson_logged_in() -> bool:
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
            st.rerun()

if not salesperson_logged_in():
    salesperson_login_form()
    st.stop()

with st.sidebar:
    st.caption(f"Logged in as: {st.session_state.get('salesperson_name')}")
    if st.button("Logout", use_container_width=True):
        st.session_state.clear()
        st.rerun()

# ---------------------------------------------------------------------
# Timezone & constants
# ---------------------------------------------------------------------
TZ = st.secrets.get("TIMEZONE", "Asia/Kolkata")
_now = datetime.now(ZoneInfo(TZ))
TODAY = _now.date()
TOMORROW = TODAY + timedelta(days=1)
MAX_DAY = TODAY + timedelta(days=60)

SLOTS = [
    "— Select slot —", "10:00–10:40", "10:40–11:20", "11:20–12:00",
    "12:20–13:00", "13:00–13:40", "13:40–14:20", "14:20–15:00", "15:00–15:40"
]
SUBJECTS = ["— Select subject —","Hindi","Mathematics","GK","SST","Science","English","Pre Primary","EVS","Computer"]
CURRICULA = ["— Select curriculum —","CBSE","ICSE","State Board","Other"]
BOOKING_TYPES = ["Live Class","Product Training"]

# ---------------------------------------------------------------------
# Booking form
# ---------------------------------------------------------------------
st.title("📅 Create a Booking")

with st.form("booking_form", clear_on_submit=False):
    col1, col2 = st.columns(2, gap="large")

    with col1:
        booking_type = st.selectbox("Booking Type", BOOKING_TYPES, index=0)
        school_name  = st.text_input("School Name")
        title_used   = st.text_input("Title Used by School")
        curriculum   = st.selectbox("Curriculum", CURRICULA, index=0)
        subject      = st.selectbox("Subject", SUBJECTS, index=0)

        picked_date  = st.date_input(
            "Date",
            value=TOMORROW,
            min_value=TOMORROW,           # block today
            max_value=MAX_DAY,
            format="YYYY-MM-DD",
            help="Bookings must be made at least one day in advance."
        )
        slot = st.selectbox("Slot", SLOTS, index=0)

    with col2:
        grade = st.text_input("Grade (Live Class only)") if booking_type == "Live Class" else None
        topic = st.text_input("Topic (optional)")
        st.text_input("Salesperson Name", value=st.session_state["salesperson_name"], disabled=True)
        st.text_input("Salesperson Number", value=st.session_state["salesperson_number"], disabled=True)
        st.text_input("Salesperson Email", value=st.session_state["salesperson_email"], disabled=True)

        # ---- ONLY block booking for *tomorrow* after 2 PM local time ----
        local_now = datetime.now(ZoneInfo(TZ))
        today = local_now.date()

        # make sure we compare date objects
        picked_day = picked_date.date() if hasattr(picked_date, "date") else picked_date
        delta_days = (picked_day - today).days
        disable_submit = (delta_days == 1) and (local_now.time() >= time(14, 0))

        if disable_submit:
            st.warning("📯 It’s past 02:00 PM today. You can’t book for **tomorrow** anymore. Please choose a later date.")

        # submit button INSIDE the form (fixes 'missing submit' warning)
        submit = st.form_submit_button("Book Session", type="primary", disabled=disable_submit)

# ---------------------------------------------------------------------
# Availability hint (outside the form so it refreshes live)
# ---------------------------------------------------------------------
if subject != SUBJECTS[0] and slot != SLOTS[0]:
    tlist = candidates_for_subject(subject)
    if tlist:
        unavailable = [t for t in tlist if is_teacher_unavailable(t, picked_date.strftime("%Y-%m-%d"), slot)]
        available   = [t for t in tlist if t not in unavailable]
        if available:
            st.success(f"Likely teacher: {available[0]}")
        else:
            st.error("All mapped teachers are unavailable for this slot.")

# ---------------------------------------------------------------------
# Submit handling
# ---------------------------------------------------------------------
def invalid(msg: str):
    st.error(msg)
    return True

if submit:
    if not school_name.strip():
        invalid("School Name is required.")
    elif curriculum == CURRICULA[0]:
        invalid("Please select a curriculum.")
    elif subject == SUBJECTS[0]:
        invalid("Please select a subject.")
    elif slot == SLOTS[0]:
        invalid("Please select a slot.")
    elif booking_type == "Live Class" and (not grade or not grade.strip()):
        invalid("Grade is required for Live Class.")
    elif exists_booking(school_name.strip(), subject, picked_date.strftime("%Y-%m-%d"), slot):
        st.warning("A booking already exists for this School, Subject, Date and Slot.")
    else:
        teacher = pick_teacher(subject, picked_date.strftime("%Y-%m-%d"), slot)
        if not teacher:
            st.error("No teacher available for this subject/date/slot.")
        elif teacher_busy(teacher, picked_date.strftime("%Y-%m-%d"), slot):
            st.error("Selected teacher is already booked in this slot.")
        else:
            data = {
                "booking_type": booking_type,
                "school_name": school_name.strip(),
                "title_used": title_used.strip(),
                "grade": grade.strip() if (booking_type == "Live Class" and grade) else None,
                "curriculum": curriculum,
                "subject": subject,
                "date": picked_date.strftime("%Y-%m-%d"),
                "slot": slot,
                "topic": (topic or "").strip(),
                "salesperson_name": st.session_state["salesperson_name"],
                "salesperson_number": st.session_state["salesperson_number"],
                "salesperson_email": st.session_state["salesperson_email"],
                "teacher": teacher,
            }
            try:
                ok, msg, _ = record_booking(data)  # backend enforces tomorrow-after-2PM rule too
                if not ok:
                    st.error(msg)
                else:
                    send_confirmation_emails(data)
                    st.success(f"✅ Booked! Teacher: {teacher} | {subject} | {data['date']} {slot}")
                    st.rerun()
            except Exception as e:
                st.exception(e)

# ---------------------------------------------------------------------
# My Bookings (with local-time display for 'Booked On')
# ---------------------------------------------------------------------
st.divider()
st.subheader("📋 My Bookings")

rows = get_bookings_for_salesperson(st.session_state["salesperson_email"])
if not rows:
    st.info("No bookings found.")
else:
    df = pd.DataFrame(rows)

    # Pretty-print "Booked On" using your timezone
    if "Booked On" in df.columns:
        from datetime import datetime as _dt
        def _to_local(ts: str) -> str:
            s = str(ts)
            try:
                if s.endswith("Z"):
                    dt = _dt.fromisoformat(s.replace("Z", "+00:00"))
                else:
                    dt = _dt.fromisoformat(s)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
                return dt.astimezone(ZoneInfo(TZ)).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                return s
        df["Booked On"] = df["Booked On"].apply(_to_local)

    st.dataframe(df, use_container_width=True, hide_index=True)
