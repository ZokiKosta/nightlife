"""
migrate.py — lightweight DB migrations.
Called once at app startup. Safe to run multiple times.
"""
from utils.logger import setup_logger

logger = setup_logger()


def run_migrations(db):
    """Widen columns that were too short in earlier versions."""
    with db.engine.connect() as conn:
        try:
            # Check if image_url column exists and is too narrow
            # SQLite: recreating column width isn't possible, but TEXT type = unlimited
            # For SQLite we just try ALTER TABLE — if column is already TEXT it's a no-op effectively
            dialect = db.engine.dialect.name

            if dialect == "sqlite":
                # SQLite doesn't support ALTER COLUMN, but we can check pragma
                result = conn.execute(
                    db.text("PRAGMA table_info(events)")
                ).fetchall()
                col_types = {row[1]: row[2] for row in result}

                # If image_url is VARCHAR(500), we need to recreate the table
                if col_types.get("image_url", "").upper().startswith("VARCHAR"):
                    logger.info("[migrate] widening image_url column from VARCHAR to TEXT")
                    _sqlite_widen_image_url(conn, db)
                else:
                    logger.debug(f"[migrate] image_url type is '{col_types.get('image_url')}' — OK")

            elif dialect in ("postgresql", "mysql", "mariadb"):
                conn.execute(db.text(
                    "ALTER TABLE events ALTER COLUMN image_url TYPE TEXT"
                    if dialect == "postgresql" else
                    "ALTER TABLE events MODIFY COLUMN image_url LONGTEXT"
                ))
                conn.commit()
                logger.info("[migrate] widened image_url to TEXT")

        except Exception as e:
            logger.debug(f"[migrate] migration note: {e}")


def _sqlite_widen_image_url(conn, db):
    """
    SQLite doesn't support ALTER COLUMN.
    Rename → recreate → copy → drop old.
    """
    try:
        conn.execute(db.text("ALTER TABLE events RENAME TO events_old"))
        conn.execute(db.text("""
            CREATE TABLE events (
                id INTEGER PRIMARY KEY,
                title VARCHAR(200) NOT NULL,
                venue VARCHAR(200),
                location VARCHAR(300),
                date VARCHAR(100),
                start_time VARCHAR(50),
                entry_price VARCHAR(100),
                phone VARCHAR(50),
                description TEXT,
                genre VARCHAR(100),
                dress_code VARCHAR(100),
                age_limit VARCHAR(50),
                instagram_profile VARCHAR(100),
                instagram_post_url VARCHAR(1000),
                image_url TEXT,
                raw_caption TEXT,
                scraped_at DATETIME,
                created_at DATETIME
            )
        """))
        conn.execute(db.text("""
            INSERT INTO events SELECT
                id, title, venue, location, date, start_time,
                entry_price, phone, description, genre, dress_code,
                age_limit, instagram_profile, instagram_post_url,
                image_url, raw_caption, scraped_at, created_at
            FROM events_old
        """))
        conn.execute(db.text("DROP TABLE events_old"))
        conn.commit()
        logger.info("[migrate] image_url column widened successfully")
    except Exception as e:
        logger.error(f"[migrate] SQLite widen failed: {e}")
        conn.execute(db.text("ALTER TABLE events_old RENAME TO events"))
        conn.commit()