import sqlite3
from datetime import datetime
import streamlit as st

DB_PATH = "cordova_publication.db"

@st.cache_resource
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    # Lightly tune SQLite for Cloud
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def _exec(q, args=()):
    cur = get_conn().cursor()
    cur.execute(q, args)
    return cur

def is_teacher_unavailable(teacher: str, date: str, slot: str) -> bool:
    cur = _exec("""
        SELECT COUNT(*) FROM teacher_unavailability
        WHERE teacher=? AND date=? AND (slot IS NULL OR slot=?)
    """, (teacher, date, slot))
    return cur.fetchone()[0] > 0

def pick_teacher(subject: str, date: str, slot: str):
    from teacher_mapping import candidates_for_subject   # lazy import
    for t in candidates_for_subject(subject):
        if not is_teacher_unavailable(t, date, slot):
            return t
    return None

def record_booking(data: dict):
    _exec("""
      INSERT INTO bookings (
        booking_type, school_name, title_used, grade, curriculum, subject,
        date, slot, topic, salesperson_name, salesperson_number,
        salesperson_email, teacher, timestamp
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
      data["booking_type"], data["school_name"], data.get("title_used"),
      data.get("grade"), data.get("curriculum"), data["subject"],
      data["date"], data["slot"], data.get("topic"),
      data["salesperson_name"], data["salesperson_number"],
      data["salesperson_email"], data["teacher"],
      datetime.now().isoformat(timespec="seconds")
    ))
    get_conn().commit()
    # invalidate reads
    get_all_bookings.clear()
    get_bookings_for_salesperson.clear()

@st.cache_data(show_spinner=False)
def get_bookings_for_salesperson(email: str):
    cur = _exec("""
        SELECT booking_type, school_name, subject, date, slot, topic, teacher, timestamp
        FROM bookings
        WHERE salesperson_email=?
        ORDER BY date DESC, timestamp DESC
    """, (email,))
    cols = ["Type","School","Subject","Date","Slot","Topic","Teacher","Booked On"]
    return [dict(zip(cols, r)) for r in cur.fetchall()]

@st.cache_data(show_spinner=False)
def get_all_bookings():
    cur = _exec("""
        SELECT id, booking_type, school_name, title_used, grade, curriculum, subject,
               date, slot, topic, teacher, salesperson_name, salesperson_number,
               salesperson_email, timestamp
        FROM bookings
        ORDER BY date DESC, timestamp DESC
    """)
    cols = ["id","Type","School","Title Used","Grade","Curriculum","Subject","Date","Slot",
            "Topic","Teacher","Salesperson","Salesperson Number","Salesperson Email","Booked On"]
    return [dict(zip(cols, r)) for r in cur.fetchall()]
