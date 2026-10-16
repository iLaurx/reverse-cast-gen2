"""Local SQLite history. Only allowlisted, non-credential fields are stored."""
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
          CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY, video_id TEXT NOT NULL, position REAL NOT NULL,
            kind TEXT NOT NULL, created_at TEXT NOT NULL);
        ''')
        self.db.commit()

    def get_host(self):
        with self.lock:
            row = self.db.execute("SELECT value FROM settings WHERE key='host'").fetchone()
            return row[0] if row else '192.168.1.6'

    def set_host(self, host):
        with self.lock, self.db:
            self.db.execute("INSERT OR REPLACE INTO settings VALUES ('host', ?)", (host,))

    def add(self, video, position, kind):
        with self.lock, self.db:
            self.db.execute('INSERT INTO history(video_id,position,kind,created_at) VALUES (?,?,?,?)',
                            (video, position, kind, datetime.now(timezone.utc).isoformat()))

    def history(self):
        with self.lock:
            return [dict(r) for r in self.db.execute('SELECT * FROM history ORDER BY id DESC LIMIT 100')]

    def checkpoint(self, row_id=None):
        with self.lock:
            sql = "SELECT * FROM history WHERE kind='checkpoint'"
            params = ()
            if row_id is not None:
                sql += ' AND id=?'
                params = (row_id,)
            row = self.db.execute(sql + ' ORDER BY id DESC LIMIT 1', params).fetchone()
            return dict(row) if row else None

    def close(self):
        with self.lock:
            self.db.close()
