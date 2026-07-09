from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.schemas import LeadBusiness
from app.services import db


class LeadDatabaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = str(Path(self.temp_dir.name) / "test_leads.db")
        db.init_db()

    def tearDown(self) -> None:
        db.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_save_retrieve_deduplicate_and_delete(self) -> None:
        lead = LeadBusiness(
            business_name="Atlas Gym",
            category="Gyms",
            address="123 Main St",
            phone="555-0100",
            email="hello@atlas.example",
            has_website=False,
            social_links=["https://facebook.com/atlasgym"],
            source_url="https://example.com/listing",
        )

        self.assertEqual(db.save_leads([lead], "New York"), 1)
        self.assertEqual(db.save_leads([lead], "New York"), 0)

        stored = db.get_stored_leads(category="gyms", location="new york")
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["business_name"], "Atlas Gym")
        self.assertEqual(stored[0]["social_links"], ["https://facebook.com/atlasgym"])

        names = db.get_discovered_names("Gyms", "New York")
        self.assertEqual(names, ["Atlas Gym"])

        self.assertTrue(db.delete_stored_lead(stored[0]["id"]))
        self.assertEqual(db.get_stored_leads(), [])


if __name__ == "__main__":
    unittest.main()
