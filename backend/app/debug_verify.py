from sqlmodel import Session, select
from app.models import Greenhouse, Zone, Crop, CropObservation, Controller, Sensor

def verify_cleanup(session: Session, greenhouse_id):
    """Verify that no orphaned records remain after greenhouse deletion."""
    checks = {
        "greenhouses": session.exec(select(Greenhouse).where(Greenhouse.id == greenhouse_id)).all(),
        "zones": session.exec(select(Zone).where(Zone.greenhouse_id == greenhouse_id)).all(),
        "controllers": session.exec(select(Controller).where(Controller.greenhouse_id == greenhouse_id)).all(),
        "sensors": session.exec(select(Sensor).join(Controller).where(Controller.greenhouse_id == greenhouse_id)).all(),
        "crops": session.exec(select(Crop).join(Zone).where(Zone.greenhouse_id == greenhouse_id)).all(),
        "observations": session.exec(select(CropObservation).join(Crop).join(Zone).where(Zone.greenhouse_id == greenhouse_id)).all(),
    }
    return {key: len(value) for key, value in checks.items()}
