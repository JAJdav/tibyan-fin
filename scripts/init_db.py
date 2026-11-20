from pathlib import Path

from sqlalchemy import text

from app.persistence.db import get_engine


def main() -> None:
    sql = Path("scripts/init_db.sql").read_text(encoding="utf-8")
    with get_engine().begin() as conn:
        for statement in sql.split(";"):
            if statement.strip():
                conn.execute(text(statement))
    print("[OK] MySQL schema initialized")


if __name__ == "__main__":
    main()
