-- Bookings
CREATE TABLE IF NOT EXISTS bookings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  booking_type TEXT NOT NULL,                  -- Live Class / Product Training
  school_name TEXT NOT NULL,
  title_used TEXT,
  grade TEXT,                                  -- nullable for Product Training
  curriculum TEXT,
  subject TEXT NOT NULL,
  date TEXT NOT NULL,                          -- YYYY-MM-DD
  slot TEXT NOT NULL,                          -- e.g., 10:00–10:40
  topic TEXT,
  salesperson_name TEXT NOT NULL,
  salesperson_number TEXT NOT NULL,
  salesperson_email TEXT NOT NULL,
  teacher TEXT NOT NULL,
  timestamp TEXT NOT NULL                      -- ISO timestamp
);

-- Teacher unavailability (full day or specific slot)
CREATE TABLE IF NOT EXISTS teacher_unavailability (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  teacher TEXT NOT NULL,
  date TEXT NOT NULL,
  slot TEXT                                    -- NULL = full day
);

-- Helpful indexes
CREATE INDEX IF NOT EXISTS idx_bookings_date ON bookings(date);
CREATE INDEX IF NOT EXISTS idx_bookings_teacher ON bookings(teacher);
CREATE INDEX IF NOT EXISTS idx_unavail_teacher_date ON teacher_unavailability(teacher, date);

-- Safeguards
-- Prevent same School+Subject on same Date+Slot
CREATE UNIQUE INDEX IF NOT EXISTS uniq_booking_key
ON bookings (school_name, subject, date, slot);

-- Prevent teacher double-booking in a slot
CREATE UNIQUE INDEX IF NOT EXISTS uniq_teacher_slot
ON bookings (teacher, date, slot);

-- Email event log (for debugging + resend)
CREATE TABLE IF NOT EXISTS email_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  to_addr TEXT NOT NULL,
  subject TEXT NOT NULL,
  status TEXT NOT NULL,   -- 'sent' | 'failed'
  error TEXT              -- nullable
);

CREATE INDEX IF NOT EXISTS idx_email_ts ON email_events(ts);

