import sqlite3

DB_PATH = "cordova_publication.db"

def initialize_database():
    with sqlite3.connect(DB_PATH) as conn:
        with open("schema.sql", "r", encoding="utf-8") as f:
            conn.executescript(f.read())
