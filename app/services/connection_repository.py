from app.db import get_connection


def save_connection(person):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO connections (
        name,
        current_title,
        linkedin_url,
        status
    )
    VALUES (?, ?, ?, ?)
    """, (
        person["name"],
        person["current_title"],
        person["linkedin_url"],
        "pending"
    ))

    connection_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return connection_id


def update_connection_result(
    connection_id,
    result
):

    conn = get_connection()
    cursor = conn.cursor()

    status = result.get(
        "status",
        "awaiting_approval"
    )

    generated_message = (
        result.get("message")
        or result.get("referral_message")
    )

    cursor.execute("""
    UPDATE connections
    SET
        person_type = ?,
        company = ?,
        company_summary = ?,
        company_url = ?,
        job_title = ?,
        job_url = ?,
        required_experience = ?,
        job_match_score = ?,
        generated_message = ?,
        status = ?
    WHERE id = ?
    """, (

        result.get("type"),

        result.get("company"),

        result.get("company_summary"),

        result.get("company_url"),

        result.get("job_title"),

        result.get("job_url"),

        result.get("required_experience"),

        result.get("match_score"),

        generated_message,

        status,

        connection_id
    ))

    conn.commit()
    conn.close()


def update_connection_status(
    connection_id,
    status
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    UPDATE connections
    SET status = ?
    WHERE id = ?
    """, (
        status,
        connection_id
    ))

    conn.commit()
    conn.close()


def get_connection_by_id(
    connection_id
):

    conn = get_connection()

    conn.row_factory = __import__(
        "sqlite3"
    ).Row

    cursor = conn.cursor()

    cursor.execute("""
    SELECT *
    FROM connections
    WHERE id = ?
    """, (
        connection_id,
    ))

    row = cursor.fetchone()

    conn.close()

    if row is None:
        return None

    return dict(row)