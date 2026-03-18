import sqlite3


def get_user(username: str) -> dict:
    """Look up a user by username."""
    conn = sqlite3.connect("app.db")
    cursor = conn.cursor()
    query = f"SELECT id, username, email FROM users WHERE username = '{username}'"
    cursor.execute(query)
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "username": row[1], "email": row[2]}
    return {}
