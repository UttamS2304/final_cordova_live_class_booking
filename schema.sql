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
  topic TEXT,                                  -- optional
  salesperson_name TEXT NOT NULL,
  salesperson_number TEXT NOT NULL,
  salesperson_email TEXT NOT NULL,
  teacher TEXT NOT NULL,
  timestamp TEXT NOT NULL                      -- ISO time of booking
);

-- Teacher unavailability (full day or specific slot)
CREATE TABLE IF NOT EXISTS teacher_unavailability (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  teacher TEXT NOT NULL,
  date TEXT NOT NULL,                          -- YYYY-MM-DD
  slot TEXT                                    -- NULL = full day
);

-- Helpful indexes
CREATE INDEX IF NOT EXISTS idx_bookings_date ON bookings(date);
CREATE INDEX IF NOT EXISTS idx_bookings_teacher ON bookings(teacher);
CREATE INDEX IF NOT EXISTS idx_unavail_teacher_date ON teacher_unavailability(teacher, date);
