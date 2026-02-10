import sqlite3
from datetime import datetime

DB_PATH = 'rd6018_charge.db'

class Database:
    def __init__(self, db_path=DB_PATH):
        self.conn = sqlite3.connect(db_path)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS current_session (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                device_id TEXT,
                start_time TEXT,
                battery_type TEXT,
                state TEXT,
                stage_start_time TEXT,
                antisulfate_count INTEGER,
                v_max_mix REAL,
                i_min_mix REAL,
                ah_total REAL,
                finished INTEGER DEFAULT 0
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                timestamp TEXT,
                message TEXT
            )
        ''')
        self.conn.commit()

    def start_session(self, battery_type):
        now = datetime.now().isoformat()
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO current_session (start_time, battery_type, state, stage_start_time, antisulfate_count, v_max_mix, i_min_mix, ah_total, finished)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
        ''', (now, battery_type, 'IDLE', now, 0, None, None, 0.0))
        self.conn.commit()
        return cursor.lastrowid

    def update_session(self, session_id, **kwargs):
        keys = ', '.join([f'{k}=?' for k in kwargs.keys()])
        values = list(kwargs.values())
        values.append(session_id)
        cursor = self.conn.cursor()
        cursor.execute(f'UPDATE current_session SET {keys} WHERE id=?', values)
        self.conn.commit()

    def log(self, session_id, message):
        now = datetime.now().isoformat()
        cursor = self.conn.cursor()
        cursor.execute('INSERT INTO logs (session_id, timestamp, message) VALUES (?, ?, ?)', (session_id, now, message))
        self.conn.commit()

    def get_last_session(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM current_session WHERE finished=0 ORDER BY id DESC LIMIT 1')
        return cursor.fetchone()

    def finish_session(self, session_id):
        cursor = self.conn.cursor()
        cursor.execute('UPDATE current_session SET finished=1 WHERE id=?', (session_id,))
        self.conn.commit()

    def close(self):
        self.conn.close()
