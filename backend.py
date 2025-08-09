# backend.py  — final version

from __future__ import annotations
import sqlite3
from datetime import datetime
import threading
import smtplib
import ssl
from typing import Optional, Dict, Any, List

import streamlit as st

from init_db import initialize_database
from teacher_mapping import candidates_for_subject

# Ensure DB schema exists
initialize_database()

DB_PATH = "cordova_publication.db"


# =========================
# Connection & Query Helpers
# =========================
@st.cache_resource
def get_conn() -> sqlite3.Connection:
    """Return a cached SQLite connection for the whole app session."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    # Light tuning for Streamlit Cloud
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def _exec(query: str, args: tuple = ()) -> sqlite3.Cursor:
    cur = get_conn().cursor()
    cur.execute(query, args)
    return cur


# =========================
# Availability & Assignment
# =========================
def is_teacher_unavailable(teacher: str, date: str, slot: str) -> bool:
    """True if teacher is unavailable for the day OR for the specific slot."""
    cur = _exec(
        """
        SELECT COUNT(*) FROM teacher_unavailability
        WHERE teacher=? AND date=? AND (slot IS NULL OR slot=?)
        """,
        (teacher, date, slot),
    )
    return cur.fetchone()[0] > 0


def pick_teacher(subject: str, date: str, slot: str) -> Optional[str]:
    """Pick the first available teacher for a subject based on mapping + unavailability."""
    for t in candidates_for_subject(subject):
        if not is_teacher_unavailable(t, date, slot):
            return t
    return None


# =========================
# Bookings CRUD
# =========================
def record_booking(data: Dict[str, Any]) -> int:
    """
    Insert a booking row. Returns the new booking ID.
    Expects keys:
      booking_type, school_name, title_used, grade, curriculum, subject,
      date, slot, topic, salesperson_name, salesperson_number,
      salesperson_email, teacher
    """
    cur = _exec(
        """
        INSERT INTO bookings (
            booking_type, school_name, title_used, grade, curriculum, subject,
            date, slot, topic, salesperson_name, salesperson_number,
            salesperson_email, teacher, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data["booking_type"],
            data["school_name"],
            data.get("title_used"),
            data.get("grade"),
            data.get("curriculum"),
            data["subject"],
            data["date"],
            data["slot"],
            data.get("topic"),
            data["salesperson_name"],
            data["salesperson_number"],
            data["salesperson_email"],
            data["teacher"],
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    get_conn().commit()
    # Invalidate caches
    get_all_bookings.clear()
    get_bookings_for_salesperson.clear()
    return cur.lastrowid


@st.cache_data(show_spinner=False)
def get_bookings_for_salesperson(email: str) -> List[Dict[str, Any]]:
    cur = _exec(
        """
        SELECT booking_type, school_name, subject, date, slot, topic, teacher, timestamp
        FROM bookings
        WHERE salesperson_email=?
        ORDER BY date DESC, timestamp DESC
        """,
        (email,),
    )
    cols = ["Type", "School", "Subject", "Date", "Slot", "Topic", "Teacher", "Booked On"]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


@st.cache_data(show_spinner=False)
def get_all_bookings() -> List[Dict[str, Any]]:
    cur = _exec(
        """
        SELECT id, booking_type, school_name, title_used, grade, curriculum, subject,
               date, slot, topic, teacher, salesperson_name, salesperson_number,
               salesperson_email, timestamp
        FROM bookings
        ORDER BY date DESC, timestamp DESC
        """
    )
    cols = [
        "id", "Type", "School", "Title Used", "Grade", "Curriculum", "Subject",
        "Date", "Slot", "Topic", "Teacher", "Salesperson", "Salesperson Number",
        "Salesperson Email", "Booked On"
    ]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def delete_booking(booking_id: int) -> None:
    _exec("DELETE FROM bookings WHERE id=?", (booking_id,))
    get_conn().commit()
    # Invalidate caches
    get_all_bookings.clear()
    get_bookings_for_salesperson.clear()


# =========================
# Teacher Unavailability
# =========================
def mark_unavailable(teacher: str, date: str, slot: Optional[str]) -> None:
    _exec(
        "INSERT INTO teacher_unavailability (teacher, date, slot) VALUES (?, ?, ?)",
        (teacher, date, slot),
    )
    get_conn().commit()


def list_unavailability() -> List[Dict[str, Any]]:
    cur = _exec(
        "SELECT id, teacher, date, slot FROM teacher_unavailability ORDER BY date DESC"
    )
    cols = ["id", "Teacher", "Date", "Slot"]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def delete_unavailability(unavail_id: int) -> None:
    _exec("DELETE FROM teacher_unavailability WHERE id=?", (unavail_id,))
    get_conn().commit()


# =========================
# Email Utilities (non-blocking)
# =========================
def _norm_teacher_key(name: str) -> str:
    return (name or "").upper().replace(" ", "")


def get_teacher_email(teacher: str) -> str:
    """
    Map teacher display name to email using secrets:
      TEACHER_EMAILS = { "BHARTIMA'AM" = "bharti@...", "VIVEKSIR" = "..." }
    Falls back to ADMIN_EMAIL if not found.
    """
    book = st.secrets.get("TEACHER_EMAILS", {})
    return book.get(_norm_teacher_key(teacher), st.secrets.get("ADMIN_EMAIL", ""))


def _smtp_send(to_addr: str, subject: str, body: str) -> None:
    """Send a single email with timeout, TLS by default."""
    if not to_addr:
        return
    host = st.secrets.get("EMAIL_HOST", "smtp.gmail.com")
    port = int(st.secrets.get("EMAIL_PORT", 587))
    user = st.secrets.get("EMAIL_USER", "")
    pwd = st.secrets.get("EMAIL_PASS", "")
    use_tls = str(st.secrets.get("EMAIL_USE_TLS", "true")).lower() == "true"

    msg = f"Subject: {subject}\r\nFrom: {user}\r\nTo: {to_addr}\r\n\r\n{body}"
    if use_tls:
        with smtplib.SMTP(host, port, timeout=8) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(user, pwd)
            s.sendmail(user, [to_addr], msg)
    else:
        with smtplib.SMTP_SSL(host, port, timeout=8) as s:
            s.login(user, pwd)
            s.sendmail(user, [to_addr], msg)


def _send_async(to_addr: str, subject: str, body: str) -> None:
    threading.Thread(target=_smtp_send, args=(to_addr, subject, body), daemon=True).start()


# -------------------------
# Public Email Entry Points
# -------------------------
def send_confirmation_emails(booking: Dict[str, Any]) -> None:
    """
    Trigger confirmation emails (non-blocking) to:
      - Salesperson (confirmation, no teacher personal details)
      - Teacher (assignment, no salesperson details)
      - Admin (summary)
    booking dict keys accepted: either DB-style caps or form keys.
    """
    # Normalize accessors
    def g(key_caps: str, key_form: str) -> Any:
        return booking.get(key_caps) if key_caps in booking else booking.get(key_form)

    sp_email = g("Salesperson Email", "salesperson_email")
    sp_name = g("Salesperson", "salesperson_name")
    school = g("School", "school_name")
    grade = g("Grade", "grade")
    subject = g("Subject", "subject")
    day = g("Date", "date")
    slot = g("Slot", "slot")
    btype = g("Type", "booking_type")
    topic = g("Topic", "topic") or "N/A"
    teacher = g("Teacher", "teacher")
    admin_to = st.secrets.get("ADMIN_EMAIL", "")

    # Salesperson
    _send_async(
        sp_email,
        "✅ Your Cordova Class is Confirmed",
        (
            f"Dear {sp_name},\n\n"
            "Your class has been successfully booked.\n\n"
            f"School: {school}\n"
            f"Grade: {grade}\n"
            f"Subject: {subject}\n"
            f"Date: {day}\n"
            f"Slot: {slot}\n"
            f"Type: {btype}\n"
            f"Topic: {topic}\n"
        ),
    )

    # Teacher
    teacher_email = get_teacher_email(teacher)
    _send_async(
        teacher_email,
        "✅ New Cordova Session Assigned",
        (
            "You have a new session to conduct.\n\n"
            f"Subject: {subject}\n"
            f"Date: {day}\n"
            f"Slot: {slot}\n"
            f"School: {school}\n"
            f"Grade: {grade}\n"
            f"Type: {btype}\n"
            f"Topic: {topic}\n"
        ),
    )

    # Admin
    _send_async(
        admin_to,
        "📢 New Cordova Booking Created",
        (
            "A new booking has been created:\n\n"
            f"School: {school}\n"
            f"Grade: {grade}\n"
            f"Subject: {subject}\n"
            f"Date: {day}\n"
            f"Slot: {slot}\n"
            f"Type: {btype}\n"
            f"Topic: {topic}\n"
            f"Teacher: {teacher}\n"
            f"Salesperson: {sp_name}\n"
            f"Salesperson Email: {sp_email}\n"
        ),
    )


def send_cancellation_emails(booking: Dict[str, Any]) -> None:
    """
    Trigger cancellation emails (non-blocking) to:
      - Salesperson
      - Teacher
    Accepts the row dict used in Admin dashboard.
    """
    def g(key_caps: str, key_form: str) -> Any:
        return booking.get(key_caps) if key_caps in booking else booking.get(key_form)

    sp_email = g("Salesperson Email", "salesperson_email")
    sp_name = g("Salesperson", "salesperson_name")
    school = g("School", "school_name")
    grade = g("Grade", "grade")
    subject = g("Subject", "subject")
    day = g("Date", "date")
    slot = g("Slot", "slot")
    teacher = g("Teacher", "teacher")

    # Salesperson
    _send_async(
        sp_email,
        "❌ Cordova Class Cancelled",
        (
            f"Dear {sp_name},\n\n"
            "Your scheduled class has been cancelled.\n\n"
            f"School: {school}\n"
            f"Grade: {grade}\n"
            f"Subject: {subject}\n"
            f"Date: {day}\n"
            f"Slot: {slot}\n"
        ),
    )

    # Teacher
    teacher_email = get_teacher_email(teacher)
    _send_async(
        teacher_email,
        "❌ Cordova Session Cancelled",
        (
            "Your assigned session has been cancelled.\n\n"
            f"Subject: {subject}\n"
            f"Date: {day}\n"
            f"Slot: {slot}\n"
            f"School: {school}\n"
            f"Grade: {grade}\n"
        ),
    )
