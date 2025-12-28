#!/usr/bin/env python3
"""Test script to call the decision API for claim 902."""

import asyncio
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

from decision_service.engine.decision_engine import DecisionEngine
from decision_service.repositories.claim_repository import ClaimRepository
from decision_service.schemas.response import DecisionResponse
import json


async def test_claim_902():
    """Test the decision API for claim 902."""
    try:
        # Set environment variable so Config picks it up
        from dotenv import load_dotenv
        load_dotenv()
        import os
        os.environ['DATABASE_URL'] = os.getenv('DATABASE_URL', '')
        
        repo = ClaimRepository()
        
        # Get claim by tracking number
        claim = await repo.get_claim_by_tracking_number("902")
        if not claim:
            print("❌ Claim 902 not found in database")
            print("   Checking database directly...")
            from sqlalchemy import create_engine, text
            from shared.config import Config
            if Config.DATABASE_URL:
                engine = create_engine(Config.DATABASE_URL)
                with engine.connect() as conn:
                    conn.execute(text("SET search_path TO claims, public"))
                    result = conn.execute(
                        text("SELECT id, claim_tracking_number FROM claims WHERE claim_tracking_number = :tn"),
                        {"tn": "902"}
                    )
                    row = result.fetchone()
                    if row:
                        print(f"   Found in DB: ID={row[0]}, Tracking={row[1]}")
                        print("   Using direct DB query...")
                        claim = {"id": row[0], "claim_tracking_number": row[1]}
                    else:
                        print("   Not found in database")
                        return
            else:
                print("   DATABASE_URL not configured")
                return
        
        print(f"✅ Found claim: ID={claim['id']}, Tracking={claim.get('claim_tracking_number', 'N/A')}")
        
        # Evaluate claim
        engine = DecisionEngine()
        decision = await engine.evaluate_claim(claim_id=claim["id"])
        
        # Create decision record
        decision_record = await repo.create_decision(decision, user_id="test_user")
        
        if not decision_record:
            print("❌ Failed to create decision record")
            return
        
        # Convert to response format
        response = DecisionResponse.from_decision_record(decision_record)
        
        # Print formatted JSON response
        print("\n" + "="*80)
        print("DECISION API RESPONSE FOR CLAIM 902")
        print("="*80 + "\n")
        print(json.dumps(response.model_dump(), indent=2, default=str))
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_claim_902())

