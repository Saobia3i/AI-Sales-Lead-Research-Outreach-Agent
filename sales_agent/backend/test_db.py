import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.db import init_db, save_leads, get_stored_leads, get_discovered_names, delete_stored_lead
from app.schemas import LeadBusiness

def test_db_flow():
    print("Initializing test database...")
    init_db()
    
    # Create fake leads
    lead1 = LeadBusiness(
        business_name="Test Gym Alpha",
        category="Gyms",
        address="123 Alpha St, NY",
        phone="555-1111",
        email="alpha@gym.com",
        google_maps_url="http://maps.google.com/alpha",
        has_website=False,
        website_url="",
        has_social_media=False,
        social_links=[],
        source_url="http://google.com/test",
        confidence_no_website=0.9
    )
    
    lead2 = LeadBusiness(
        business_name="Test Gym Beta",
        category="Gyms",
        address="456 Beta St, NY",
        phone="555-2222",
        email="beta@gym.com",
        google_maps_url="http://maps.google.com/beta",
        has_website=True,
        website_url="http://betagym.com",
        has_social_media=True,
        social_links=["http://facebook.com/betagym"],
        source_url="http://google.com/test",
        confidence_no_website=0.1
    )
    
    print("Saving test leads...")
    saved = save_leads([lead1, lead2], "New York, USA")
    print(f"Saved {saved} leads.")
    
    # Verify name exclusions
    print("Fetching discovered names...")
    names = get_discovered_names("Gyms", "New York, USA")
    print(f"Discovered names: {names}")
    assert "Test Gym Alpha" in names
    assert "Test Gym Beta" in names
    
    # Retrieve leads
    print("Querying stored leads...")
    stored = get_stored_leads(category="Gyms", location="New York, USA")
    print(f"Retrieved {len(stored)} leads.")
    assert len(stored) == 2
    
    # Delete lead
    lead_id = stored[0]["id"]
    print(f"Deleting lead {lead_id}...")
    deleted = delete_stored_lead(lead_id)
    print(f"Deleted successfully: {deleted}")
    assert deleted is True
    
    # Verify deletion
    stored_after = get_stored_leads(category="Gyms", location="New York, USA")
    print(f"Retrieved {len(stored_after)} leads after deletion.")
    assert len(stored_after) == 1
    
    print("All SQLite Database Flow Tests Passed successfully!")

if __name__ == "__main__":
    test_db_flow()
