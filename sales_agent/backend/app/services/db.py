"""SQLite persistence for discovered leads."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from threading import Lock

logger = logging.getLogger(__name__)

_DEFAULT_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "leads.db")
TABLE_NAME = "leads"

_COLUMNS: dict[str, str] = {
    "id": "TEXT PRIMARY KEY",
    "business_name": "TEXT NOT NULL",
    "category": "TEXT",
    "address": "TEXT",
    "phone": "TEXT",
    "email": "TEXT",
    "has_website": "INTEGER",
    "website_url": "TEXT",
    "google_maps_url": "TEXT",
    "social_links": "TEXT",
    "source_url": "TEXT",
    "location": "TEXT",
    "confidence_no_website": "REAL DEFAULT 0.0",
    "scanned_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    "website_status": "TEXT",
    "evidence": "TEXT",
    "sources": "TEXT",
    "dedupe_key": "TEXT",
    "rating": "REAL",
    "review_count": "INTEGER",
}
_initialized_for: str | None = None
_init_lock = Lock()


def db_path() -> str:
    return os.environ.get("LEADS_DB_PATH") or _DEFAULT_DB


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the table and add any columns missing from older databases."""
    global _initialized_for
    path = db_path()
    if _initialized_for == path:
        return
    with _init_lock:
        conn = get_connection()
        try:
            cols = ", ".join(f"{name} {decl}" for name, decl in _COLUMNS.items())
            conn.execute(f"CREATE TABLE IF NOT EXISTS {TABLE_NAME} ({cols})")
            existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({TABLE_NAME})")}
            for name, decl in _COLUMNS.items():
                if name not in existing:
                    conn.execute(f"ALTER TABLE {TABLE_NAME} ADD COLUMN {name} {decl.replace('PRIMARY KEY', '')}")
                    logger.info("Migrated leads table: added column %s", name)
            conn.execute(f"CREATE INDEX IF NOT EXISTS idx_leads_dedupe ON {TABLE_NAME}(dedupe_key)")
            conn.commit()
            _initialized_for = path
        finally:
            conn.close()


def generate_lead_id(name: str, category: str | None, address: str | None, dedupe_key: str | None = None) -> str:
    key = dedupe_key or f"{name.lower().strip()}|{(category or '').lower().strip()}|{(address or '').lower().strip()}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()


def save_leads(leads, location: str) -> int:
    """Insert new leads and refresh existing ones. Returns the number of rows written."""
    init_db()
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for lead in leads:
        rows.append({
            "id": generate_lead_id(lead.business_name, lead.category, lead.address, getattr(lead, "dedupe_key", None)),
            "business_name": lead.business_name.strip(),
            "category": (lead.category or "").strip(),
            "address": (lead.address or "").strip(),
            "phone": (lead.phone or "").strip(),
            "email": (lead.email or "").strip(),
            "has_website": 1 if lead.has_website else 0,
            "website_url": (lead.website_url or "").strip(),
            "google_maps_url": (lead.google_maps_url or "").strip(),
            "social_links": json.dumps(lead.social_links or []),
            "source_url": (lead.source_url or "").strip(),
            "location": location.strip(),
            "confidence_no_website": float(lead.confidence_no_website or 0.0),
            "scanned_at": now,
            "website_status": getattr(lead, "website_status", None),
            "evidence": json.dumps(getattr(lead, "evidence", []) or []),
            "sources": json.dumps(getattr(lead, "sources", []) or []),
            "dedupe_key": getattr(lead, "dedupe_key", None),
            "rating": getattr(lead, "rating", None),
            "review_count": getattr(lead, "review_count", None),
        })
    if not rows:
        return 0
    names = list(rows[0].keys())
    updates = ", ".join(f"{n}=excluded.{n}" for n in names if n != "id")
    sql = (f"INSERT INTO {TABLE_NAME} ({', '.join(names)}) VALUES ({', '.join(':' + n for n in names)}) "
           f"ON CONFLICT(id) DO UPDATE SET {updates}")
    conn = get_connection()
    try:
        conn.executemany(sql, rows)
        conn.commit()
    finally:
        conn.close()
    logger.info("Saved %d leads to SQLite.", len(rows))
    return len(rows)


def _row_to_dict(row: sqlite3.Row) -> dict:
    def _json_list(value: str | None) -> list:
        try:
            parsed = json.loads(value) if value else []
            return parsed if isinstance(parsed, list) else []
        except (TypeError, ValueError):
            return []

    status = row["website_status"] or ("has_website" if row["has_website"] else "unverified")
    return {
        "id": row["id"],
        "business_name": row["business_name"],
        "category": row["category"] or None,
        "address": row["address"] or None,
        "phone": row["phone"] or None,
        "email": row["email"] or None,
        "has_website": bool(row["has_website"]),
        "website_url": row["website_url"] or None,
        "website_status": status,
        "google_maps_url": row["google_maps_url"] or None,
        "social_links": _json_list(row["social_links"]),
        "has_social_media": bool(_json_list(row["social_links"])),
        "source_url": row["source_url"] or None,
        "confidence_no_website": max(0.0, min(1.0, float(row["confidence_no_website"] or 0.0))),
        "evidence": _json_list(row["evidence"]),
        "sources": _json_list(row["sources"]),
        "rating": row["rating"],
        "review_count": row["review_count"],
        "dedupe_key": row["dedupe_key"],
        "location": row["location"],
        "scanned_at": row["scanned_at"],
    }


def get_stored_leads(category: str | None = None, location: str | None = None,
                     status: str | None = None) -> list[dict]:
    """Stored leads, newest first, optionally filtered."""
    init_db()
    query = f"SELECT * FROM {TABLE_NAME} WHERE 1=1"
    params: list[str] = []
    if category:
        query += " AND LOWER(category) LIKE ?"
        params.append(f"%{category.lower().strip()}%")
    if location:
        query += " AND LOWER(location) LIKE ?"
        params.append(f"%{location.lower().strip()}%")
    query += " ORDER BY scanned_at DESC"
    conn = get_connection()
    try:
        rows = [_row_to_dict(r) for r in conn.execute(query, params).fetchall()]
    finally:
        conn.close()
    if status:
        rows = [r for r in rows if r["website_status"] == status]
    return rows


def get_known_lead_keys(category: str, location: str) -> tuple[set[str], set[str]]:
    """Dedupe keys and compact names of businesses already stored for this search."""
    from app.leads.matching import compact, normalize_name

    init_db()
    loc_term = location.lower().strip().split(",")[0].strip()
    conn = get_connection()
    try:
        rows = conn.execute(
            f"SELECT business_name, dedupe_key FROM {TABLE_NAME} WHERE LOWER(location) LIKE ?",
            (f"%{loc_term}%",),
        ).fetchall()
    finally:
        conn.close()
    keys = {r["dedupe_key"] for r in rows if r["dedupe_key"]}
    names = {compact(normalize_name(r["business_name"])) for r in rows}
    return keys, names


def get_discovered_names(category: str, location: str) -> list[str]:
    """Kept for backwards compatibility with older scripts."""
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            f"SELECT business_name FROM {TABLE_NAME} WHERE LOWER(category) LIKE ? AND LOWER(location) LIKE ?",
            (f"%{category.lower().strip()}%", f"%{location.lower().strip().split(',')[0].strip()}%"),
        ).fetchall()
    finally:
        conn.close()
    return [r["business_name"] for r in rows]


def delete_stored_lead(lead_id: str) -> bool:
    init_db()
    conn = get_connection()
    try:
        cur = conn.execute(f"DELETE FROM {TABLE_NAME} WHERE id = ?", (lead_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
