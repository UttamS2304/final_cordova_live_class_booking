# backend.py — MAIL-ROBUST FINAL

from __future__ import annotations
import sqlite3, re, smtplib, ssl
from datetime import datetime
from typing import Optional, Dict, Any, List
from concurrent.futures import ThreadPoolExecutor

import streamlit as st
from init_db import initialize_database
from teacher_mapping import candidates_for_subject

# -------------------------------
# DB init (schema + email_events)
# -------------------------------
initialize_database()
DB_PATH = "cordova_publication.db"

def _ensure_email_log_table():
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS email_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ts TEXT NOT NULL,
              to_addr TEXT NOT NULL,
              subject TEXT NOT NULL,
              status TEXT NOT NULL,
              error TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_email_ts ON email_events(ts);
            """)
    except Exception as e:
        print(f"[EMAIL][INIT-LOG-FAIL] {e}")

_ensure_email_log_table()

# -------------------------------
# DB connection / helpers
# -------------------------------
@st.cache_resource
def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def _exec(q: str, args: tuple = ()) -> sqlite3.Cursor:
    cur = get_conn().cursor()
    cur.execute(q, args)
    return cur

# -------------------------------
# Availability & assignment
# -------------------------------
def is_teacher_unavailable(teacher: str, date: str, slot: str) -> bool:
    cur = _exec(
        """SELECT COUNT(*) FROM teacher_unavailability
           WHERE teacher=? AND date=? AND (slot IS NULL OR slot=?)""",
        (teacher, date, slot),
    )
    return cur.fetchone()[0] > 0

def pick_teacher(subject: str, date: str, slot: str) -> Optional[str]:
    for t in candidates_for_subject(subject):
        if not is_teacher_unavailable(t, date, slot):
            return t
    return None

# -------------------------------
# Guards
# -------------------------------
def exists_booking(school: str, subject: str, day: str, slot: str) -> bool:
    cur = _exec(
        "SELECT 1 FROM bookings WHERE school_name=? AND subject=? AND date=? AND slot=? LIMIT 1",
        (school, subject, day, slot),
    )
    return cur.fetchone() is not None

def teacher_busy(teacher: str, day: str, slot: str) -> bool:
    cur = _exec(
        "SELECT 1 FROM bookings WHERE teacher=? AND date=? AND slot=? LIMIT 1",
        (teacher, day, slot),
    )
    return cur.fetchone() is not None

# -------------------------------
# Bookings CRUD
# -------------------------------
def record_booking(data: Dict[str, Any]) -> int:
    cur = _exec(
        """INSERT INTO bookings (
            booking_type, school_name, title_used, grade, curriculum, subject,
            date, slot, topic, salesperson_name, salesperson_number,
            salesperson_email, teacher, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data["booking_type"], data["school_name"], data.get("title_used"),
            data.get("grade"), data.get("curriculum"), data["subject"],
            data["date"], data["slot"], data.get("topic"),
            data["salesperson_name"], data["salesperson_number"],
            data["salesperson_email"], data["teacher"],
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    get_conn().commit()
    get_all_bookings.clear(); get_bookings_for_salesperson.clear()
    return cur.lastrowid

@st.cache_data(show_spinner=False, ttl=60)
def get_bookings_for_salesperson(email: str) -> List[Dict[str, Any]]:
    cur = _exec(
        """SELECT booking_type, school_name, subject, date, slot, topic, teacher, timestamp
           FROM bookings WHERE salesperson_email=?
           ORDER BY date DESC, timestamp DESC""",
        (email,),
    )
    cols = ["Type","School","Subject","Date","Slot","Topic","Teacher","Booked On"]
    return [dict(zip(cols, r)) for r in cur.fetchall()]

@st.cache_data(show_spinner=False, ttl=60)
def get_all_bookings() -> List[Dict[str, Any]]:
    cur = _exec(
        """SELECT id, booking_type, school_name, title_used, grade, curriculum, subject,
                  date, slot, topic, teacher, salesperson_name, salesperson_number,
                  salesperson_email, timestamp
           FROM bookings
           ORDER BY date DESC, timestamp DESC"""
    )
    cols = ["id","Type","School","Title Used","Grade","Curriculum","Subject","Date",
            "Slot","Topic","Teacher","Salesperson","Salesperson Number",
            "Salesperson Email","Booked On"]
    return [dict(zip(cols, r)) for r in cur.fetchall()]

def delete_booking(booking_id: int) -> None:
    _exec("DELETE FROM bookings WHERE id=?", (booking_id,))
    get_conn().commit()
    get_all_bookings.clear(); get_bookings_for_salesperson.clear()

# -------------------------------
# Email system (robust)
# -------------------------------
def _elog(msg: str):
    print(f"[EMAIL] {msg}")

def _norm_key(name: str) -> str:
    name = (name or "").upper()
    return re.sub(r"[^A-Z0-9]+", "_", name).strip("_")

def get_teacher_email(teacher: str) -> str:
    book = st.secrets.get("TEACHER_EMAILS", {})
    key  = _norm_key(teacher)
    addr = book.get(key, "")
    if not addr:
        _elog(f"teacher email missing for key={key} (teacher={teacher}) — skipping teacher mail")
    return addr

def _log_email(to_addr: str, subject: str, status: str, error: str | None = None):
    try:
        _exec(
            "INSERT INTO email_events (ts, to_addr, subject, status, error) VALUES (?, ?, ?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"), to_addr, subject, status, error),
        )
        get_conn().commit()
    except Exception as e:
        print(f"[EMAIL][LOG-FAIL] {e}")

def _secrets_ok() -> bool:
    req = ("EMAIL_HOST","EMAIL_PORT","EMAIL_USER","EMAIL_PASS")
    return all(st.secrets.get(k) for k in req)

# Core SMTP with one retry + DB logging
def _smtp_send(to_addr: str, subject: str, body: str) -> None:
    if not to_addr:
        _elog("skip: empty to_addr"); return

    if not _secrets_ok():
        _elog("skip: incomplete secrets")
        _log_email(to_addr, subject, "failed", "incomplete secrets")
        return

    host = st.secrets.get("EMAIL_HOST", "smtp.gmail.com")
    port = int(st.secrets.get("EMAIL_PORT", 587))
    user = st.secrets.get("EMAIL_USER", "")
    pwd  = st.secrets.get("EMAIL_PASS", "")
    use_tls = str(st.secrets.get("EMAIL_USE_TLS", "true")).lower() == "true"

    msg = f"Subject: {subject}\r\nFrom: {user}\r\nTo: {to_addr}\r\n\r\n{body}"
    last_err = None

    for attempt in (1, 2):
        try:
            _elog(f"sending (try {attempt}) → to={to_addr}, host={host}:{port}, tls={use_tls}")
            if use_tls:
                with smtplib.SMTP(host, port, timeout=12) as s:
                    s.starttls(context=ssl.create_default_context())
                    s.login(user, pwd)
                    s.sendmail(user, [to_addr], msg)
            else:
                ssl_port = 465 if port == 587 else port
                with smtplib.SMTP_SSL(host, ssl_port, timeout=12) as s:
                    s.login(user, pwd)
                    s.sendmail(user, [to_addr], msg)
            _elog(f"sent ✓ to={to_addr}")
            _log_email(to_addr, subject, "sent", None)
            return
        except Exception as e:
            last_err = str(e)
            _elog(f"FAIL try {attempt} to={to_addr}: {e}")

    _log_email(to_addr, subject, "failed", last_err)

# persistent executor
@st.cache_resource
def get_mail_executor() -> ThreadPoolExecutor:
    return ThreadPoolExecutor(max_workers=4)

def _email_sync_mode() -> bool:
    # Default ON for reliability; set EMAIL_SYNC="false" to queue async
    return str(st.secrets.get("EMAIL_SYNC", "true")).lower() == "true"

def _send_async(to_addr: str, subject: str, body: str):
    if _email_sync_mode():
        _elog("SYNC MODE — sending immediately")
        _smtp_send(to_addr, subject, body)
    else:
        _elog("queueing (async)")
        get_mail_executor().submit(_smtp_send, to_addr, subject, body)

# Public email entry points
def send_confirmation_emails(booking: Dict[str, Any]) -> None:
    def g(CAPS: str, form: str) -> Any:
        return booking.get(CAPS) if CAPS in booking else booking.get(form)

    sp_email = g("Salesperson Email","salesperson_email")
    sp_name  = g("Salesperson","salesperson_name")
    school   = g("School","school_name")
    grade    = g("Grade","grade")
    subj     = g("Subject","subject")
    day      = g("Date","date")
    slot     = g("Slot","slot")
    btype    = g("Type","booking_type")
    topic    = g("Topic","topic") or "N/A"
    teacher  = g("Teacher","teacher")
    admin_to = st.secrets.get("ADMIN_EMAIL","")

    _send_async(sp_email, "✅ Your Cordova Class is Confirmed",
        f"Dear {sp_name},\n\nYour class has been successfully booked.\n\n"
        f"School: {school}\nGrade: {grade}\nSubject: {subj}\nDate: {day}\n"
        f"Slot: {slot}\nType: {btype}\nTopic: {topic}\n")

    t_email = get_teacher_email(teacher)
    if t_email:
        _send_async(t_email, "✅ New Cordova Session Assigned",
            "You have a new session to conduct.\n\n"
            f"Subject: {subj}\nDate: {day}\nSlot: {slot}\nSchool: {school}\n"
            f"Grade: {grade}\nType: {btype}\nTopic: {topic}\n")

    if admin_to:
        _send_async(admin_to, "📢 New Cordova Booking Created",
            "A new booking has been created:\n\n"
            f"School: {school}\nGrade: {grade}\nSubject: {subj}\nDate: {day}\n"
            f"Slot: {slot}\nType: {btype}\nTopic: {topic}\nTeacher: {teacher}\n"
            f"Salesperson: {sp_name}\nSalesperson Email: {sp_email}\n")

def send_cancellation_emails(booking: Dict[str, Any]) -> None:
    def g(CAPS: str, form: str) -> Any:
        return booking.get(CAPS) if CAPS in booking else booking.get(form)

    sp_email = g("Salesperson Email","salesperson_email")
    sp_name  = g("Salesperson","salesperson_name")
    school   = g("School","school_name")
    grade    = g("Grade","grade")
    subj     = g("Subject","subject")
    day      = g("Date","date")
    slot     = g("Slot","slot")
    teacher  = g("Teacher","teacher")

    _send_async(sp_email, "❌ Cordova Class Cancelled",
        f"Dear {sp_name},\n\nYour scheduled class has been cancelled.\n\n"
        f"School: {school}\nGrade: {grade}\nSubject: {subj}\nDate: {day}\nSlot: {slot}\n")

    t_email = get_teacher_email(teacher)
    if t_email:
        _send_async(t_email, "❌ Cordova Session Cancelled",
            "Your assigned session has been cancelled.\n\n"
            f"Subject: {subj}\nDate: {day}\nSlot: {slot}\nSchool: {school}\nGrade: {grade}\n")

# -------------------------------
# Email log APIs (Admin → Analytics)
# -------------------------------
@st.cache_data(show_spinner=False, ttl=60)
def get_email_events(limit: int = 200):
    cur = _exec(
        "SELECT id, ts, to_addr, subject, status, error FROM email_events ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    cols = ["id","ts","to","subject","status","error"]
    return [dict(zip(cols, r)) for r in cur.fetchall()]

def resend_email(event_id: int):
    cur = _exec("SELECT to_addr, subject FROM email_events WHERE id=?", (event_id,))
    row = cur.fetchone()
    if not row:
        return
    to_addr, subject = row
    _smtp_send(to_addr, subject, f"[RESEND] This is a resend attempt for '{subject}'.")
