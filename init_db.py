"""Create or update the application tables from schema.sql in PostgreSQL."""
from pathlib import Path

from app import db_connect


def main():
    statements = [part.strip() for part in Path(__file__).with_name("schema.sql").read_text().split(";") if part.strip()]
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            for statement in statements:
                cur.execute(statement)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    print("Database schema is ready")


if __name__ == "__main__":
    main()
