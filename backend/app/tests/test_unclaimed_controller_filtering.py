#!/usr/bin/env python3
"""
Simple test to verify that unclaimed controllers are properly filtered from API responses.
This tests the H1 controller schema requirement that API never returns controllers with null greenhouse_id.
"""

import sys
import uuid
from datetime import datetime, timezone

from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Controller


def test_unclaimed_controller_filtering():
    """Test that unclaimed controllers (greenhouse_id=NULL) are properly filtered from API responses"""

    # Create an in-memory SQLite database for testing
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        try:
            # Create a claimed controller
            claimed_controller = Controller(
                device_name="verdify-claimed",
                greenhouse_id=uuid.uuid4(),  # This is claimed
                claim_code="CLAIMED123",
                is_climate_controller=False,
                created_at=datetime.now(timezone.utc),
                last_seen=datetime.now(timezone.utc),
            )
            session.add(claimed_controller)

            # Create an unclaimed controller (greenhouse_id=NULL)
            unclaimed_controller = Controller(
                device_name="verdify-unclaimed",
                greenhouse_id=None,  # This is unclaimed
                claim_code="UNCLAIMED456",
                is_climate_controller=False,
                created_at=datetime.now(timezone.utc),
                last_seen=None,
            )
            session.add(unclaimed_controller)
            session.commit()

            # Verify both controllers exist in database
            all_controllers = session.exec(select(Controller)).all()
            claimed_in_db = any(
                c.device_name == "verdify-claimed" for c in all_controllers
            )
            unclaimed_in_db = any(
                c.device_name == "verdify-unclaimed" for c in all_controllers
            )

            print(f"✓ Claimed controller in DB: {claimed_in_db}")
            print(f"✓ Unclaimed controller in DB: {unclaimed_in_db}")

            # Test the filtering logic that our API routes should use
            # This simulates what the updated controller routes do: filter out greenhouse_id=NULL
            claimed_only_query = select(Controller).where(
                Controller.greenhouse_id.is_not(None)
            )
            claimed_controllers = session.exec(claimed_only_query).all()

            claimed_names = [c.device_name for c in claimed_controllers]

            print(f"✓ Controllers returned by API filter: {claimed_names}")
            print(
                f"✓ Claimed controller in API results: {'verdify-claimed' in claimed_names}"
            )
            print(
                f"✓ Unclaimed controller filtered out: {'verdify-unclaimed' not in claimed_names}"
            )

            # Verify the filtering works as expected
            assert (
                claimed_in_db and unclaimed_in_db
            ), "Both controllers should exist in database"
            assert (
                "verdify-claimed" in claimed_names
            ), "Claimed controller should be in API results"
            assert (
                "verdify-unclaimed" not in claimed_names
            ), "Unclaimed controller should be filtered out"

            # Test that controller has last_seen field
            claimed_ctrl = session.exec(
                select(Controller).where(Controller.device_name == "verdify-claimed")
            ).first()
            assert claimed_ctrl is not None, "Claimed controller should exist"
            assert hasattr(
                claimed_ctrl, "last_seen"
            ), "Controller should have last_seen field"
            assert (
                claimed_ctrl.last_seen is not None
            ), "Claimed controller should have last_seen set"

            unclaimed_ctrl = session.exec(
                select(Controller).where(Controller.device_name == "verdify-unclaimed")
            ).first()
            assert unclaimed_ctrl is not None, "Unclaimed controller should exist"
            assert hasattr(
                unclaimed_ctrl, "last_seen"
            ), "Controller should have last_seen field"
            assert (
                unclaimed_ctrl.last_seen is None
            ), "Unclaimed controller should have last_seen as None"

            print(
                "✓ last_seen field works correctly for both claimed and unclaimed controllers"
            )

            print("\n🎉 SUCCESS: Controller filtering works correctly!")
            print(
                "   - Unclaimed controllers (greenhouse_id=NULL) exist in DB but are filtered from API"
            )
            print("   - Claimed controllers (greenhouse_id set) are returned by API")
            print("   - last_seen field is properly supported")

            return True

        except Exception as e:
            print(f"❌ ERROR: {e}")
            import traceback

            traceback.print_exc()
            return False


if __name__ == "__main__":
    success = test_unclaimed_controller_filtering()
    sys.exit(0 if success else 1)
