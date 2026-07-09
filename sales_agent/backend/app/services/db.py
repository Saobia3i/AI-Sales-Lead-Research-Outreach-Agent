import sqlite3
import json
import hashlib
import os
import logging
from datetime import UTC, datetime
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "leads.db")
TABLE_NAME = "leads"

_DIRECTORY_OR_SOCIAL_DOMAINS: frozenset[str] = frozenset({
    "facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com",
    "youtube.com", "tiktok.com", "pinterest.com", "threads.net", "snapchat.com",
    "yelp.com", "tripadvisor.com", "yellowpages.com", "foursquare.com",
    "groupon.com", "mapquest.com", "justdial.com", "zomato.com", "swiggy.com",
    "foodpanda.com", "happycow.net", "yell.com", "bbb.org", "trustpilot.com",
    "angi.com", "homeadvisor.com", "thumbtack.com", "houzz.com", "nextdoor.com",
    "opentable.com", "alignable.com", "superpages.com", "local.com", "manta.com",
    "citysearch.com", "merchantcircle.com", "google.com", "maps.google.com",
})


def _looks_like_standalone_source_url(url: str | None) -> bool:
    if not url:
        return False
    try:
        parsed = urlparse(url.lower())
        domain = (parsed.netloc or parsed.path).removeprefix("www.")
        if not domain or "." not in domain:
            return False
        return not any(
            domain == blocked or domain.endswith("." + blocked)
            for blocked in _DIRECTORY_OR_SOCIAL_DOMAINS
        )
    except Exception:
        return False

def get_connection():
    """Returns a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database and creates the leads table if it doesn't exist."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                id TEXT PRIMARY KEY,
                business_name TEXT NOT NULL,
                category TEXT,
                address TEXT,
                phone TEXT,
                email TEXT,
                has_website INTEGER,
                website_url TEXT,
                google_maps_url TEXT,
                social_links TEXT,
                source_url TEXT,
                location TEXT,
                scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            SELECT name FROM sqlite_master WHERE type='table' AND name='stored_leads'
        """)
        if cursor.fetchone():
            cursor.execute(f"""
                INSERT OR IGNORE INTO {TABLE_NAME} (
                    id, business_name, category, address, phone, email, has_website,
                    website_url, google_maps_url, social_links, source_url, location, scanned_at
                )
                SELECT
                    id, business_name, category, address, phone, email, has_website,
                    website_url, google_maps_url, social_links, source_url, location, scanned_at
                FROM stored_leads
            """)
        conn.commit()
        logger.info(f"Database initialized successfully at: {DB_PATH}")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise e
    finally:
        conn.close()

def generate_lead_id(name: str, category: str | None, address: str | None) -> str:
    """Generates a unique hash ID for a lead based on name, category, and address."""
    key = f"{name.lower().strip()}|{(category or '').lower().strip()}|{(address or '').lower().strip()}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()

def save_leads(leads, location: str) -> int:
    """Saves a list of leads to the database. Returns count of newly inserted leads."""
    init_db()  # Ensure database is initialized
    conn = get_connection()
    saved_count = 0
    try:
        cursor = conn.cursor()
        for lead in leads:
            if lead.has_website or lead.website_url:
                continue

            # Generate stable unique ID
            lead_id = generate_lead_id(lead.business_name, lead.category, lead.address)
            
            # Serialize social links list to JSON string
            social_links_str = json.dumps(lead.social_links or [])
            
            cursor.execute(f"""
                INSERT OR IGNORE INTO {TABLE_NAME} (
                    id, business_name, category, address, phone, email, 
                    has_website, website_url, google_maps_url, social_links, source_url, location, scanned_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                lead_id,
                lead.business_name.strip(),
                (lead.category or "").strip(),
                (lead.address or "").strip(),
                (lead.phone or "").strip(),
                (lead.email or "").strip(),
                1 if lead.has_website else 0,
                (lead.website_url or "").strip(),
                (lead.google_maps_url or "").strip(),
                social_links_str,
                (lead.source_url or "").strip(),
                location.strip(),
                datetime.now(UTC).isoformat()
            ))
            saved_count += cursor.rowcount
        conn.commit()
        logger.info(f"Successfully saved {saved_count} leads to SQLite database.")
    except Exception as e:
        logger.error(f"Error saving leads to SQLite: {e}")
        conn.rollback()
    finally:
        conn.close()
    return saved_count

def get_stored_leads(category: str | None = None, location: str | None = None) -> list[dict]:
    """Retrieves stored no-website leads, optionally filtered by category/location."""
    init_db()
    conn = get_connection()
    results = []
    try:
        cursor = conn.cursor()
        query = f"SELECT * FROM {TABLE_NAME} WHERE has_website = 0 AND COALESCE(website_url, '') = ''"
        params = []
        
        if category:
            query += " AND LOWER(category) LIKE ?"
            params.append(f"%{category.lower().strip()}%")
        if location:
            query += " AND LOWER(location) LIKE ?"
            params.append(f"%{location.lower().strip()}%")
            
        query += " ORDER BY scanned_at DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        for row in rows:
            if _looks_like_standalone_source_url(row["source_url"]):
                continue

            social_links = []
            try:
                social_links = json.loads(row["social_links"]) if row["social_links"] else []
            except Exception:
                pass
                
            results.append({
                "id": row["id"],
                "business_name": row["business_name"],
                "category": row["category"],
                "address": row["address"],
                "phone": row["phone"],
                "email": row["email"],
                "has_website": bool(row["has_website"]),
                "website_url": row["website_url"],
                "google_maps_url": row["google_maps_url"],
                "social_links": social_links,
                "source_url": row["source_url"],
                "location": row["location"],
                "scanned_at": row["scanned_at"]
            })
    except Exception as e:
        logger.error(f"Error querying stored leads: {e}")
    finally:
        conn.close()
    return results

def get_discovered_names(category: str, location: str) -> list[str]:
    """Retrieves list of business names already discovered for this category and location."""
    init_db()
    conn = get_connection()
    names = []
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT business_name FROM {TABLE_NAME} WHERE LOWER(category) = ? AND LOWER(location) = ?",
            (category.lower().strip(), location.lower().strip())
        )
        rows = cursor.fetchall()
        names = [row["business_name"] for row in rows]
    except Exception as e:
        logger.error(f"Error fetching discovered business names: {e}")
    finally:
        conn.close()
    return names

def delete_stored_lead(lead_id: str) -> bool:
    """Deletes a lead by ID from the database. Returns True if deleted."""
    init_db()
    conn = get_connection()
    success = False
    try:
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM {TABLE_NAME} WHERE id = ?", (lead_id,))
        conn.commit()
        success = cursor.rowcount > 0
        logger.info(f"Deleted lead ID {lead_id} from SQLite database: {success}")
    except Exception as e:
        logger.error(f"Error deleting lead from SQLite: {e}")
        conn.rollback()
    finally:
        conn.close()
    return success
