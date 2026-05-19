import sqlite3

class UnitOfWork:
    """
    Manages database transactions and consistency.
    """
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = None

    def __enter__(self):
        self.conn = sqlite3.connect(self.db_path)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()
        self.conn.close()

    def execute(self, sql: str, params: tuple = ()):
        return self.conn.execute(sql, params)
