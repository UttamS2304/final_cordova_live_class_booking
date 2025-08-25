# backend.py — FINAL (Supabase Postgres + SQLite fallback, timezone-safe, enforced rules)

from __future__ import annotations

import os, re, ssl, smtplib
from typing import Optional, Dict, Any, List, Tuple
from email.message import EmailMessage
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo

import streamlit as st

# -----------------------------------------------------------------------------
# Timezone config & helpers
# -----------------------------------------------------------------------------
TZ = os.getenv("TIMEZONE") or st.secrets.get("TIMEZONE", "Asia/Kolkata")
try:
    TZINFO = ZoneInfo(TZ)
except Exception:
    TZINFO = ZoneInfo("Asia/Kolkata")

def now_local() -> datetime:
    return datetime.now(TZINFO)

def parse_session_date(d) -> date:
    if isinstance(d, date):
        return d
    s = str(d).strip()
    try:
        return datetime.fromisoformat(s).date()
    except Exception:
        return datetime.strptime(s, "%Y-%m-%d").date()

def parse_slot_range(slot_str: str) -> tuple[Optional[time], Optional[time]]:
    if not slot_str:
        return None, None
    parts = re.split(r"\s*[–-]\s*", str(slot_str).strip())
    if len(parts) != 2:
        return None, None
    try:
        t1 = datetime.strptime(parts[0], "%H:%M").time()
        t2 = datetime.strptime(parts[1], "%H:%M").time()
        return t1, t2
    except Exception:
        return None, None


# -----------------------------------------------------------------------------
# DB connection (Postgres via SUPABASE_*; fallback to SQLite for local)
# -----------------------------------------------------------------------------
def _db_url() -> str | None:
    for key in ("SUPABASE_DB_URL", "SUPABASE_CONNECTION_STRING", "DATABASE_URL"):
        val = (st.secrets.get(key) if hasattr(st, "secrets") else None) or os.getenv(key)
        if val and str(val).strip():
            return str(val).strip()
    return None

def _is_postgres_conn(conn) -> bool:
    return conn.__class__.__module__.startswith("psycopg2")

def _is_dml(sql: str) -> bool:
    head = sql.strip().split()[0].upper() if sql else ""
    return head in {"INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER"}

def _adapt_sql(sql: str, conn) -> str:
    # Use %s for Postgres, ? for SQLite
    if _is_postgres_conn(conn):
        return sql
    return sql.replace("%s", "?")

@st.cache_resource
def get_conn():
    url = _db_url()
    if url:
        import psycopg2
        conn = psycopg2.connect(url, sslmode="require")
        conn.autocommit = True
        _ensure_schema(conn)
        return conn
    else:
        import sqlite3
        conn = sqlite3.connect("cordova_publication.db", check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        _ensure_schema(conn)
        return conn

def _exec(sql: str, args: tuple = ()):
    conn = get_conn()
    sql2 = _adapt_sql(sql, conn)
    cur = conn.cursor()
    cur.execute(sql2, args)
    # Auto-commit for SQLite if DML (Postgres autocommit already True)
    if not _is_postgres_conn(conn) and _is_dml(sql):
        conn.commit()
    return cur

def _fetchall_dict(sql: str, args: tuple = ()) -> List[Dict[str, Any]]:
    conn = get_conn()
    sql2 = _adapt_sql(sql, conn)
    cur = conn.cursor()
    cur.execute(sql2, args)
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    cur.close()
    return [dict(zip(cols, r)) for r in rows]

def _fetchone_val(sql: str, args: tuple = ()):
    conn = get_conn()
    sql2 = _adapt_sql(sql, conn)
    cur = conn.cursor()
    cur.execute(sql2, args)
    row = cur.fetchone()
    cur.close()
    if row is None:
        return None
    if isinstance(row, (list, tuple)) and len(row) == 1:
        return row[0]
    return row

def _ensure_schema(conn) -> None:
    """Create required tables/indexes if missing for Postgres or SQLite."""
    pg = _is_postgres_conn(conn)
    cur = conn.cursor()
    if pg:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id SERIAL PRIMARY KEY,
                booking_type TEXT,
                school_name TEXT,
                title_used TEXT,
                grade TEXT,
                curriculum TEXT,
                subject TEXT,
                date DATE,
                slot TEXT,
                topic TEXT,
                salesperson_name TEXT,
                salesperson_number TEXT,
                salesperson_email TEXT,
                teacher TEXT,
                timestamp TIMESTAMPTZ DEFAULT NOW()
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS teacher_unavailability (
                id SERIAL PRIMARY KEY,
                teacher TEXT NOT NULL,
                date DATE NOT NULL,
                slot TEXT
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS email_events (
                id SERIAL PRIMARY KEY,
                ts TIMESTAMPTZ NOT NULL,
                to_addr TEXT NOT NULL,
                subject TEXT NOT NULL,
                status TEXT NOT NULL,
                error TEXT
            );
        """)
        cur.execute("""CREATE INDEX IF NOT EXISTS idx_bookings_date_slot
                       ON bookings(date, slot);""")
        cur.execute("""CREATE INDEX IF NOT EXISTS idx_unavail_teacher_date
                       ON teacher_unavailability(teacher, date);""")
        cur.execute("""CREATE INDEX IF NOT EXISTS idx_email_ts
                       ON email_events(ts);""")
    else:
        # SQLite types are permissive; use AUTOINCREMENT for id and TEXT for dates
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_type TEXT,
                school_name TEXT,
                title_used TEXT,
                grade TEXT,
                curriculum TEXT,
                subject TEXT,
                date TEXT,
                slot TEXT,
                topic TEXT,
                salesperson_name TEXT,
                salesperson_number TEXT,
                salesperson_email TEXT,
                teacher TEXT,
                timestamp TEXT
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS teacher_unavailability (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher TEXT NOT NULL,
                date TEXT NOT NULL,
                slot TEXT
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS email_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                to_addr TEXT NOT NULL,
                subject TEXT NOT NULL,
                status TEXT NOT NULL,
                error TEXT
            );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_bookings_date_slot ON bookings(date, slot);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_unavail_teacher_date ON teacher_unavailability(teacher, date);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_email_ts ON email_events(ts);")
        conn.commit()
    cur.close()


# -----------------------------------------------------------------------------
# Capacity configuration
# -----------------------------------------------------------------------------
from teacher_mapping import candidates_for_subject

DEFAULT_MAX_PER_TEACHER = int(st.secrets.get("MAX_CLASSES_PER_TEACHER_PER_DAY", 2))
MAX_PARALLEL_CLASSES_PER_SLOT = int(st.secrets.get("MAX_PARALLEL_CLASSES_PER_SLOT", 3))

def _norm_key(name: str) -> str:
    name = (name or "").upper()
    return re.sub(r"[^A-Z0-9]+", "_", name).strip("_")

def _per_teacher_limits() -> dict:
    raw = st.secrets.get("PER_TEACHER_LIMITS", {})
    limits: dict[str, int] = {}
    for k, v in raw.items():
        try:
            limits[_norm_key(k)] = int(v)
        except Exception:
            pass
    limits.setdefault("MEGHA", 1)  # Hard rule unless overridden
    return limits

@st.cache_data(show_spinner=False, ttl=60)
def daily_limit_for_teacher(teacher: str) -> int:
    return _per_teacher_limits().get(_norm_key(teacher), DEFAULT_MAX_PER_TEACHER)


# -----------------------------------------------------------------------------
# Availability & guards
# -----------------------------------------------------------------------------
def is_teacher_unavailable(teacher: str, day: str, slot: str) -> bool:
    cnt = _fetchone_val(
        """SELECT COUNT(*) FROM teacher_unavailability
           WHERE teacher=%s AND date=%s AND (slot IS NULL OR slot=%s)""",
        (teacher, day, slot),
    ) or 0
    return int(cnt) > 0

def teacher_busy(teacher: str, day: str, slot: str) -> bool:
    row = _fetchone_val(
        "SELECT 1 FROM bookings WHERE teacher=%s AND date=%s AND slot=%s LIMIT 1",
        (teacher, day, slot),
    )
    return row is not None

def exists_booking(school: str, subject: str, day: str, slot: str) -> bool:
    row = _fetchone_val(
        "SELECT 1 FROM bookings WHERE school_name=%s AND subject=%s AND date=%s AND slot=%s LIMIT 1",
        (school, subject, day, slot),
    )
    return row is not None

def count_teacher_on_day(teacher: str, day: str) -> int:
    cnt = _fetchone_val("SELECT COUNT(*) FROM bookings WHERE teacher=%s AND date=%s", (teacher, day)) or 0
    return int(cnt)

def count_parallel_on_slot(day: str, slot: str) -> int:
    cnt = _fetchone_val("SELECT COUNT(*) FROM bookings WHERE date=%s AND slot=%s", (day, slot)) or 0
    return int(cnt)


# -----------------------------------------------------------------------------
# Teacher choice (availability + caps)
# -----------------------------------------------------------------------------
def pick_teacher(subject: str, day: str, slot: str) -> Optional[str]:
    for t in candidates_for_subject(subject):
        if is_teacher_unavailable(t, day, slot):
            continue
        if teacher_busy(t, day, slot):
            continue
        if count_teacher_on_day(t, day) >= daily_limit_for_teacher(t):
            continue
        return t
    return None


# -----------------------------------------------------------------------------
# Booking rules + CRUD
# -----------------------------------------------------------------------------
def _enforce_booking_window(day_str: str, slot_str: str) -> Tuple[bool, str]:
    local_now = now_local()
    today = local_now.date()
    session_date = parse_session_date(day_str)

    # Must be strictly after today
    if session_date <= today:
        return False, "❌ Sessions must be booked at least one day in advance."
    # Tomorrow allowed only before 2 PM today
    if session_date == today + timedelta(days=1) and local_now.time() >= time(14, 0):
        return False, "❌ You can only book for tomorrow before 02:00 PM."
    return True, ""

def record_booking(data: Dict[str, Any]) -> Tuple[bool, str, Optional[int]]:
    day   = data["date"]
    slot  = data["slot"]
    subj  = data["subject"]
    school = data["school_name"]
    teacher = data["teacher"]

    ok, msg = _enforce_booking_window(day, slot)
    if not ok:
        return False, msg, None

    if count_parallel_on_slot(day, slot) >= MAX_PARALLEL_CLASSES_PER_SLOT:
        return False, "This slot is full. Please choose another time.", None

    if exists_booking(school, subj, day, slot):
        return False, "This school & subject is already booked for that date & slot.", None

    if is_teacher_unavailable(teacher, day, slot) or teacher_busy(teacher, day, slot):
        return False, "Selected teacher is not available in this slot.", None

    if count_teacher_on_day(teacher, day) >= daily_limit_for_teacher(teacher):
        return False, f"{teacher} has reached the daily limit ({daily_limit_for_teacher(teacher)}).", None

    booked_ts = now_local().isoformat(timespec="seconds")

    cur = _exec(
        """INSERT INTO bookings (
            booking_type, school_name, title_used, grade, curriculum, subject,
            date, slot, topic, salesperson_name, salesperson_number,
            salesperson_email, teacher, timestamp
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            data["booking_type"], data["school_name"], data.get("title_used"),
            data.get("grade"), data.get("curriculum"), data["subject"],
            day, slot, data.get("topic"),
            data["salesperson_name"], data["salesperson_number"],
            data["salesperson_email"], teacher, booked_ts,
        ),
    )
    # Return ID in a portable way
    new_id = None
    try:
        # Postgres: RETURNING id (not used here to remain portable)
        new_id = _fetchone_val("SELECT MAX(id) FROM bookings")
    except Exception:
        pass
    cur.close()
    get_all_bookings.clear(); get_bookings_for_salesperson.clear()
    return True, "Booking successfully created.", int(new_id) if new_id else None

@st.cache_data(show_spinner=False, ttl=60)
def get_bookings_for_salesperson(email: str) -> List[Dict[str, Any]]:
    sql = """
    SELECT booking_type AS "Type",
           school_name  AS "School",
           subject      AS "Subject",
           date         AS "Date",
           slot         AS "Slot",
           topic        AS "Topic",
           teacher      AS "Teacher",
           timestamp    AS "Booked On"
    FROM bookings
    WHERE salesperson_email=%s
    ORDER BY date DESC, timestamp DESC
    """
    return _fetchall_dict(sql, (email,))

@st.cache_data(show_spinner=False, ttl=60)
def get_all_bookings() -> List[Dict[str, Any]]:
    sql = """
    SELECT id                                   AS "id",
           booking_type                          AS "Type",
           school_name                           AS "School",
           title_used                            AS "Title Used",
           grade                                 AS "Grade",
           curriculum                            AS "Curriculum",
           subject                               AS "Subject",
           date                                  AS "Date",
           slot                                  AS "Slot",
           topic                                 AS "Topic",
           teacher                               AS "Teacher",
           salesperson_name                      AS "Salesperson",
           salesperson_number                    AS "Salesperson Number",
           salesperson_email                     AS "Salesperson Email",
           timestamp                             AS "Booked On"
    FROM bookings
    ORDER BY date DESC, timestamp DESC
    """
    return _fetchall_dict(sql)

def delete_booking(booking_id_or_row) -> None:
    if isinstance(booking_id_or_row, int):
        _exec("DELETE FROM bookings WHERE id=%s", (booking_id_or_row,))
    elif isinstance(booking_id_or_row, dict) and "id" in booking_id_or_row:
        _exec("DELETE FROM bookings WHERE id=%s", (booking_id_or_row["id"],))
    else:
        row = booking_id_or_row
        _exec("""DELETE FROM bookings
                 WHERE school_name=%s AND subject=%s AND date=%s AND slot=%s 
                       AND salesperson_name=%s AND teacher=%s""",
              (row["school_name"], row["subject"], row["date"], row["slot"],
               row["salesperson_name"], row["teacher"]))
    get_all_bookings.clear(); get_bookings_for_salesperson.clear()


# -----------------------------------------------------------------------------
# Attempt booking API (applies rules, sends mail)
# -----------------------------------------------------------------------------
def attempt_booking(form_data: Dict[str, Any]) -> Tuple[bool, str, Optional[int]]:
    day  = form_data["date"]
    slot = form_data["slot"]
    subj = form_data["subject"]

    ok, msg = _enforce_booking_window(day, slot)
    if not ok:
        return False, msg, None

    if count_parallel_on_slot(day, slot) >= MAX_PARALLEL_CLASSES_PER_SLOT:
        return False, "This slot is full. Please choose another time.", None
    if exists_booking(form_data["school_name"], subj, day, slot):
        return False, "This school & subject is already booked for that date & slot.", None

    teacher = pick_teacher(subj, day, slot)
    if not teacher:
        return False, "No suitable teacher available (busy/unavailable/daily cap reached).", None
    if count_teacher_on_day(teacher, day) >= daily_limit_for_teacher(teacher):
        return False, f"{teacher} has reached the daily limit ({daily_limit_for_teacher(teacher)}).", None

    row = dict(form_data); row["teacher"] = teacher
    ok, msg, booking_id = record_booking(row)
    if not ok:
        return False, msg, None

    try:
        send_confirmation_emails({
            "Salesperson Email": row.get("salesperson_email") or row.get("email"),
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
    _exec(
        "INSERT INTO email_events (ts, to_addr, subject, status, error) VALUES (%s, %s, %s, %s, %s)",
        (now_local().isoformat(timespec="seconds"), to_addr, subject, status, error),
    )

def _smtp_send(to_addr: str, subject: str, body: str) -> None:
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
    return str(st.secrets.get("EMAIL_SYNC", "true")).lower() == "true"

def _send_async(to_addr: str, subject: str, body: str):
    if _email_sync_mode():
        _smtp_send(to_addr, subject, body)
    else:
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
    sql = """SELECT id,
                    ts,
                    to_addr AS "to",
                    subject,
                    status,
                    error
             FROM email_events
             ORDER BY id DESC
             LIMIT %s"""
    return _fetchall_dict(sql, (limit,))

def resend_email(event_id: int):
    row = _fetchone_val("SELECT to_addr, subject FROM email_events WHERE id=%s", (event_id,))
    if not row:
        return
    # row could be tuple or dict depending on engine; handle both
    if isinstance(row, dict):
        to_addr, subject = row["to_addr"], row["subject"]
    else:
        to_addr, subject = row
    _smtp_send(to_addr, subject, f"[RESEND] This is a resend attempt for '{subject}'.")


# -----------------------------------------------------------------------------
# Teacher Unavailability (and admin API compatibility)
# -----------------------------------------------------------------------------
def mark_unavailable(teacher: str, day: str, slot: Optional[str]) -> None:
    _exec("INSERT INTO teacher_unavailability (teacher, date, slot) VALUES (%s, %s, %s)",
          (teacher, day, slot))

def list_unavailability() -> List[Dict[str, Any]]:
    sql = 'SELECT id, teacher AS "Teacher", date AS "Date", slot AS "Slot" FROM teacher_unavailability ORDER BY date DESC'
    return _fetchall_dict(sql)

def delete_unavailability(unavail_id: int) -> None:
    _exec("DELETE FROM teacher_unavailability WHERE id=%s", (unavail_id,))

# Backward-compatible names used by your admin UI
def mark_teacher_unavailable(teacher: str, day: str, slot: Optional[str]):
    return mark_unavailable(teacher, day, slot)

def get_teacher_unavailability():
    return list_unavailability()

def delete_teacher_unavailability(teacher_or_id, day=None, slot=None):
    if isinstance(teacher_or_id, int):
        return delete_unavailability(teacher_or_id)
    if teacher_or_id and day:
        if slot:
            _exec("DELETE FROM teacher_unavailability WHERE teacher=%s AND date=%s AND slot=%s",
                  (teacher_or_id, day, slot))
        else:
            _exec("DELETE FROM teacher_unavailability WHERE teacher=%s AND date=%s AND slot IS NULL",
                  (teacher_or_id, day))
