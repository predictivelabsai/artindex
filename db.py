import os, csv
from pathlib import Path
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.environ["DB_URL"]

def get_conn():
    return psycopg2.connect(DB_URL)

def init_db():
    schema_sql = (Path(__file__).parent / "sql" / "schema.sql").read_text()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
        conn.commit()

def load_csv(csv_path: str, provider: str):
    """Import CSV data into auction_lots table, skipping duplicates."""
    rows = []
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append((
                int(r["date"]),
                r["author"].strip(),
                int(r["start_price"]),
                int(r["end_price"]),
                int(r["year"]) if r.get("year") else None,
                int(r["decade"]) if r.get("decade") else None,
                r.get("tech", "").strip() or None,
                r.get("category", "").strip() or None,
                float(r["dimension"]) if r.get("dimension") else None,
                provider,
            ))
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Clear existing rows for this provider before re-import
            cur.execute("DELETE FROM artindex.auction_lots WHERE auction_provider = %s", (provider,))
            execute_values(
                cur,
                """INSERT INTO artindex.auction_lots
                   (auction_date, author, start_price, end_price, year, decade, tech, category, dimension, auction_provider)
                   VALUES %s""",
                rows,
            )
        conn.commit()
    return len(rows)

def _sanitize_int(v, default=0, max_val=2**31 - 1):
    """Ensure value is a valid integer for PostgreSQL."""
    if v is None:
        return None if default is None else default
    try:
        v = int(v)
        return v if abs(v) <= max_val else default
    except (ValueError, TypeError):
        return default

def insert_lots(lots: list[dict]):
    """Insert scraped auction lots into DB."""
    rows = []
    for r in lots:
        rows.append((
            _sanitize_int(r.get("auction_date"), 2024),
            (r.get("author") or "").strip(),
            _sanitize_int(r.get("start_price", 0)),
            _sanitize_int(r.get("end_price", 0)),
            _sanitize_int(r.get("year"), default=None),
            _sanitize_int(r.get("decade"), default=None),
            r.get("tech"),
            r.get("category"),
            r.get("dimension"),
            r.get("auction_provider"),
        ))
    with get_conn() as conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
                """INSERT INTO artindex.auction_lots
                   (auction_date, author, start_price, end_price, year, decade, tech, category, dimension, auction_provider)
                   VALUES %s""",
                rows,
            )
        conn.commit()
    return len(rows)

def fetch_lots(provider: str | None = None):
    """Fetch lots as list of dicts, optionally filtered by provider."""
    q = "SELECT auction_date, author, start_price, end_price, year, decade, tech, category, dimension, auction_provider FROM artindex.auction_lots"
    params = []
    if provider:
        q += " WHERE auction_provider = %s"
        params.append(provider)
    q += " ORDER BY auction_date DESC, author"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(q, params)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

if __name__ == "__main__":
    print("Initializing database...")
    init_db()
    csv_path = Path(__file__).parent / "data" / "allee_clean.csv"
    if csv_path.exists():
        n = load_csv(str(csv_path), "allee")
        print(f"Imported {n} rows from allee_clean.csv")
    else:
        print(f"CSV not found at {csv_path}")
