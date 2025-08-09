import sqlite3
from datetime import datetime
import streamlit as st
from init_db import initialize_database
from teacher_mapping import candidates_for_subject

DB_PATH = "cordova_publication.db"
initialize_database()

def connect_db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def is_teacher_unavailable(teacher: str, date: str, slot: str) -> bool:
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM teacher_unavailability
            WHERE teacher=? AND date=? AND (slot IS NULL OR slot=?)
        """, (teacher, date, slot))
        return cur.fetchone()[0] > 0

def pick_teacher(subject: str, date: str, slot: str):
    from teacher_mapping import candidates_for_subject
    for t in candidates_for_subject(subject):
        if not is_teacher_unavailable(t, date, slot):
            return t
    return None

def record_booking(data: dict):
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("""
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
        conn.commit()

def get_bookings_for_salesperson(email: str):
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT booking_type, school_name, subject, date, slot, topic, teacher, timestamp
            FROM bookings
            WHERE salesperson_email=?
            ORDER BY date DESC, timestamp DESC
        """, (email,))
        rows = cur.fetchall()
    cols = ["Type","School","Subject","Date","Slot","Topic","Teacher","Booked On"]
    return [dict(zip(cols, r)) for r in rows]

def get_all_bookings():
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, booking_type, school_name, title_used, grade, curriculum, subject,
                   date, slot, topic, teacher, salesperson_name, salesperson_number,
                   salesperson_email, timestamp
            FROM bookings
            ORDER BY date DESC, timestamp DESC
        """)
        rows = cur.fetchall()
    cols = ["id","Type","School","Title Used","Grade","Curriculum","Subject","Date","Slot",
            "Topic","Teacher","Salesperson","Salesperson Number","Salesperson Email","Booked On"]
    return [dict(zip(cols, r)) for r in rows]

def delete_booking(booking_id: int):
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM bookings WHERE id=?", (booking_id,))
        conn.commit()

def mark_unavailable(teacher: str, date: str, slot: str | None):
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO teacher_unavailability (teacher, date, slot) VALUES (?, ?, ?)",
                    (teacher, date, slot))
        conn.commit()

def list_unavailability():
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, teacher, date, slot FROM teacher_unavailability ORDER BY date DESC")
        rows = cur.fetchall()
    cols = ["id","Teacher","Date","Slot"]
    return [dict(zip(cols, r)) for r in rows]

def delete_unavailability(unavail_id: int):
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM teacher_unavailability WHERE id=?", (unavail_id,))
        conn.commit()

