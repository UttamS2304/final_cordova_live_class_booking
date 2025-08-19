# backend.py — FINAL (friendly messages + caps + robust email)

from __future__ import annotations
import sqlite3, re, smtplib, ssl
from datetime import datetime, date, time, timedelta
from typing import Optional, Dict, Any, List, Tuple
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage

import streamlit as st
from init_db import initialize_database
from teacher_mapping import candidates_for_subject

# -----------------------------------------------------------------------------
# DB bootstrap
# -----------------------------------------------------------------------------
initialize_database()
DB_PATH = "cordova_publication.db"

def _ensure_email_log_table() -> None:
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

# -----------------------------------------------------------------------------
# Connection helpers
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# Capacity configuration (overridable via secrets)
# -----------------------------------------------------------------------------
DEFAULT_MAX_PER_TEACHER = int(st.secrets.get("MAX_CLASSES_PER_TEACHER_PER_DAY", 2))
MAX_PARALLEL_CLASSES_PER_SLOT = int(st.secrets.get("MAX_PARALLEL_CLASSES_PER_SLOT", 3))

def _norm_key(name: str) -> str:
    name = (name or "").upper()
    return re.sub(r"[^A-Z0-9]+", "_", name).strip("_")

def _per_teacher_limits() -> dict:
    """
    Optional overrides in secrets:
      [PER_TEACHER_LIMITS]
      MEGHA = "1"
      VIVEK_SIR = "2"
    Hard default below ensures Megha = 1/day even if secrets omitted.
    """
    raw = st.secrets.get("PER_TEACHER_LIMITS", {})
    limits: dict[str, int] = {}
    for k, v in raw.items():
        try:
            limits[_norm_key(k)] = int(v)
        except Exception:
            pass
    limits.setdefault("MEGHA", 1)  # Hard rule: Megha = 1/day
    return limits

@st.cache_data(show_spinner=False, ttl=60)
def daily_limit_for_teacher(teacher: str) -> int:
    return _per_teacher_limits().get(_norm_key(teacher), DEFAULT_MAX_PER_TEACHER)

# -----------------------------------------------------------------------------
# Availability & guards
# -----------------------------------------------------------------------------
def is_teacher_unavailable(teacher: str, date: str, slot: str) -> bool:
    cur = _exec(
        """SELECT COUNT(*) FROM teacher_unavailability
           WHERE teacher=? AND date=? AND (slot IS NULL OR slot=?)""",
        (teacher, date, slot),
    )
    return cur.fetchone()[0] > 0

def teacher_busy(teacher: str, day: str, slot: str) -> bool:
    cur = _exec("SELECT 1 FROM bookings WHERE teacher=? AND date=? AND slot=? LIMIT 1",
                (teacher, day, slot))
    return cur.fetchone() is not None

def exists_booking(school: str, subject: str, day: str, slot: str) -> bool:
    cur = _exec("SELECT 1 FROM bookings WHERE school_name=? AND subject=? AND date=? AND slot=? LIMIT 1",
                (school, subject, day, slot))
    return cur.fetchone() is not None

def count_teacher_on_day(teacher: str, day: str) -> int:
    cur = _exec("SELECT COUNT(*) FROM bookings WHERE teacher=? AND date=?", (teacher, day))
    return int(cur.fetchone()[0])

def count_parallel_on_slot(day: str, slot: str) -> int:
    cur = _exec("SELECT COUNT(*) FROM bookings WHERE date=? AND slot=?", (day, slot))
    return int(cur.fetchone()[0])

# -----------------------------------------------------------------------------
# Teacher choice (availability + caps)
# -----------------------------------------------------------------------------
def pick_teacher(subject: str, date: str, slot: str) -> Optional[str]:
    """
    Pick first candidate who:
      - not unavailable,
      - not already booked in slot,
      - under per-teacher daily limit for that date.
    """
    for t in candidates_for_subject(subject):
        if is_teacher_unavailable(t, date, slot):
            continue
        if teacher_busy(t, date, slot):
            continue
        if count_teacher_on_day(t, date) >= daily_limit_for_teacher(t):
            continue
        return t
    return None

# -----------------------------------------------------------------------------
# Bookings CRUD (friendly messages, no tracebacks)
# -----------------------------------------------------------------------------
def record_booking(data: Dict[str, Any]) -> Tuple[bool, str, Optional[int]]:
    """
    Insert booking after guard checks.
    Returns (ok, message, booking_id|None). Never raises for user errors.
    """
    day = data["date"]; slot = data["slot"]; subj = data["subject"]
    school = data["school_name"]; teacher = data["teacher"]

    # Parallel cap
    if count_parallel_on_slot(day, slot) >= MAX_PARALLEL_CLASSES_PER_SLOT:
        return False, "This slot is full. Please choose another time.", None

    # Duplicate guard
    if exists_booking(school, subj, day, slot):
        return False, "This school & subject is already booked for that date & slot.", None

    # Teacher slot & daily cap
    if is_teacher_unavailable(teacher, day, slot) or teacher_busy(teacher, day, slot):
        return False, "Selected teacher is not available in this slot.", None
    if count_teacher_on_day(teacher, day) >= daily_limit_for_teacher(teacher):
        return False, f"{teacher} has reached the daily limit ({daily_limit_for_teacher(teacher)}).", None

    cur = _exec(
        """INSERT INTO bookings (
            booking_type, school_name, title_used, grade, curriculum, subject,
            date, slot, topic, salesperson_name, salesperson_number,
            salesperson_email, teacher, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data["booking_type"], data["school_name"], data.get("title_used"),
            data.get("grade"), data.get("curriculum"), data["subject"],
            day, slot, data.get("topic"),
            data["salesperson_name"], data["salesperson_number"],
            data["salesperson_email"], teacher,
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    get_conn().commit()
    get_all_bookings.clear(); get_bookings_for_salesperson.clear()
    return True, "Booking successfully created.", cur.lastrowid

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

# -----------------------------------------------------------------------------
# Attempt booking API (apply all rules, send mail)
# -----------------------------------------------------------------------------
def attempt_booking(form_data: Dict[str, Any]) -> Tuple[bool, str, Optional[int]]:
    """
    Applies constraints, picks teacher, records booking, sends emails.
    Caller should display the returned message to the user.
    """
    day  = form_data["date"]
    slot = form_data["slot"]
    subj = form_data["subject"]

    # ----------------------------
    # NEW: booking window limits
    # - Must book at least 1 day before the session date
    # - Bookings allowed only before 02:00 PM (current day)
    # ----------------------------
    # Parse session date robustly
    if isinstance(day, datetime):
        session_date = day.date()
    elif isinstance(day, date):
        session_date = day
    else:
        # Accept ISO formats like "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS"
        try:
            session_date = datetime.fromisoformat(str(day)).date()
        except ValueError:
            session_date = datetime.strptime(str(day), "%Y-%m-%d").date()

    now = datetime.now()
    today = now.date()

    # Must be at least 1 day in advance (no same-day or past bookings)
    if session_date <= today:
        return False, "❌ Sessions can only be booked at least one day in advance.", None

    # Only allow creating bookings before 2:00 PM local time
    if now.time() > time(14, 0):
        return False, "❌ New bookings are allowed only before 02:00 PM.", None
    # ----------------------------

    # Parallel capacity
    if count_parallel_on_slot(day, slot) >= MAX_PARALLEL_CLASSES_PER_SLOT:
        return False, "This slot is full. Please choose another time.", None

    # Duplicate guard
    if exists_booking(form_data["school_name"], subj, day, slot):
        return False, "This school & subject is already booked for that date & slot.", None

    # Teacher selection
    teacher = pick_teacher(subj, day, slot)
    if not teacher:
        return False, "No suitable teacher available (busy/unavailable/daily cap reached).", None

    # Final per-teacher cap (belt & suspenders)
    if count_teacher_on_day(teacher, day) >= daily_limit_for_teacher(teacher):
        return False, f"{teacher} has reached the daily limit ({daily_limit_for_teacher(teacher)}).", None

    row = dict(form_data); row["teacher"] = teacher

    ok, msg, booking_id = record_booking(row)
    if not ok:
        return False, msg, None

    # Emails (confirmation)
    try:
        send_confirmation_emails({
            "Salesperson Email": row["salesperson_email"],
            "Salesperson": row["salesperson_name"],
            "School": row["school_name"],
            "Grade": row.get("grade"),
            "Subject": row["subject"],
            "Date": row["date"],
            "Slot": row["slot"],
            "Type": row["booking_type"],
            "Topic": row.get("topic"),
            "Teacher": row["teacher"],
        })
    except Exception as e:
        _elog(f"post-booking email error: {e}")

    return True, f"Booked with {teacher}.", booking_id


# -----------------------------------------------------------------------------
# Email system (UTF-8 safe, logging, resend)
# -----------------------------------------------------------------------------
def _elog(msg: str): print(f"[EMAIL] {msg}")

def get_teacher_email(teacher: str) -> str:
    """
    Look up teacher email from [TEACHER_EMAILS] using a normalized key.
    Includes fallbacks and logs the key used.
    """
    book = st.secrets.get("TEACHER_EMAILS", {})
    if not teacher:
        _elog("teacher email lookup skipped: empty teacher"); return ""
    key_norm = _norm_key(teacher)
    val = book.get(key_norm)
    if not val:
        alt_keys = {
            key_norm.replace("MAAM", "MAM"),
            key_norm.replace("MA_AM", "MAAM"),
            key_norm.replace("__", "_"),
        }
        for k in alt_keys:
            if k in book:
                val = book[k]; key_norm = k; break
    if not val:
        lower_map = {k.lower(): v for k, v in book.items()}
        val = lower_map.get(key_norm.lower(), "")
    if not val:
        _elog(f"teacher email missing for key={key_norm} (teacher='{teacher}')")
        return ""
    _elog(f"teacher email found for key={key_norm} -> {val}")
    return val

def _log_email(to_addr: str, subject: str, status: str, error: str | None = None):
    try:
        _exec("INSERT INTO email_events (ts, to_addr, subject, status, error) VALUES (?, ?, ?, ?, ?)",
              (datetime.now().isoformat(timespec="seconds"), to_addr, subject, status, error))
        get_conn().commit()
    except Exception as e:
        print(f"[EMAIL][LOG-FAIL] {e}")

def _smtp_send(to_addr: str, subject: str, body: str) -> None:
    """UTF-8 safe SMTP with 1 retry + DB logging."""
    if not to_addr:
        _elog("skip: empty to_addr"); return

    host = st.secrets.get("EMAIL_HOST", "smtp.gmail.com")
    port = int(st.secrets.get("EMAIL_PORT", 587))
    user = st.secrets.get("EMAIL_USER", "")
    pwd  = st.secrets.get("EMAIL_PASS", "")
    use_tls = str(st.secrets.get("EMAIL_USE_TLS", "true")).lower() == "true"

    if not (host and port and user and pwd):
        _elog("skip: incomplete secrets")
        _log_email(to_addr, subject, "failed", "incomplete secrets")
        return

    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body, subtype="plain", charset="utf-8")

    last_err = None
    for attempt in (1, 2):
        try:
            _elog(f"sending (try {attempt}) → to={to_addr}, host={host}:{port}, tls={use_tls}")
            if use_tls:
                with smtplib.SMTP(host, port, timeout=12) as s:
                    s.starttls(context=ssl.create_default_context())
                    s.login(user, pwd)
                    s.send_message(msg)
            else:
                ssl_port = 465 if port == 587 else port
                with smtplib.SMTP_SSL(host, ssl_port, timeout=12) as s:
                    s.login(user, pwd)
                    s.send_message(msg)
            _elog(f"sent ✓ to={to_addr}")
            _log_email(to_addr, subject, "sent", None)
            return
        except Exception as e:
            last_err = str(e)
            _elog(f"FAIL try {attempt} to={to_addr}: {e}")
    _log_email(to_addr, subject, "failed", last_err)

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
    """Send cancellation emails synchronously (inline) to avoid losing them on rerun."""
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

    _smtp_send(
        sp_email,
        "❌ Cordova Class Cancelled",
        f"Dear {sp_name},\n\nYour scheduled class has been cancelled.\n\n"
        f"School: {school}\nGrade: {grade}\nSubject: {subj}\nDate: {day}\nSlot: {slot}\n"
    )

    t_email = get_teacher_email(teacher)
    if t_email:
        _smtp_send(
            t_email,
            "❌ Cordova Session Cancelled",
            "Your assigned session has been cancelled.\n\n"
            f"Subject: {subj}\nDate: {day}\nSlot: {slot}\nSchool: {school}\nGrade: {grade}\n"
        )

# -----------------------------------------------------------------------------
# Email log APIs (Admin → Email tab)
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# Teacher Unavailability (shared DB + ensure table)
# -----------------------------------------------------------------------------
def _ensure_unavailability_table() -> None:
    _exec("""
        CREATE TABLE IF NOT EXISTS teacher_unavailability (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          teacher TEXT NOT NULL,
          date TEXT NOT NULL,
          slot TEXT
        );
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_unavail_teacher_date ON teacher_unavailability(teacher, date)")
    get_conn().commit()

def mark_unavailable(teacher: str, date: str, slot: Optional[str]) -> None:
    _ensure_unavailability_table()
    _exec("INSERT INTO teacher_unavailability (teacher, date, slot) VALUES (?, ?, ?)",
          (teacher, date, slot))
    get_conn().commit()

def list_unavailability() -> List[Dict[str, Any]]:
    _ensure_unavailability_table()
    cur = _exec("SELECT id, teacher, date, slot FROM teacher_unavailability ORDER BY date DESC")
    cols = ["id","Teacher","Date","Slot"]
    return [dict(zip(cols, r)) for r in cur.fetchall()]

def delete_unavailability(unavail_id: int) -> None:
    _ensure_unavailability_table()
    _exec("DELETE FROM teacher_unavailability WHERE id=?", (unavail_id,))
    get_conn().commit()

