import sqlite3


def get_user(username: str) -> dict:
    """Look up a user by username."""
    conn = None
    try:
        conn = sqlite3.connect("app.db")
        cursor = conn.cursor()
        query = "SELECT id, username, email FROM users WHERE username = ?"
        cursor.execute(query, (username,))
        row = cursor.fetchone()
        if row:
            return {"id": row[0], "username": row[1], "email": row[2]}
        return {}
    except sqlite3.DatabaseError:
        return {}
    finally:
        if conn is not None:
            conn.close()
