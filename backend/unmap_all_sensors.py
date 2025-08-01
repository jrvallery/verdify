from app.core.db import engine
from sqlmodel import Session, text

def unmap_all_sensors():
    """Unmap all sensors from all zones and set is_mapped = false"""
    with Session(engine) as session:
        # Update all sensor foreign keys in zone table to NULL
        sensor_types = ['temperature', 'humidity', 'co2', 'light', 'soil_moisture']
        
        for sensor_type in sensor_types:
            session.exec(text(f"UPDATE zone SET {sensor_type}_sensor_id = NULL"))
        
        # Set all sensors to unmapped
        session.exec(text("UPDATE sensor SET is_mapped = false"))
        
        session.commit()
        print("All sensors have been unmapped from zones")

if __name__ == "__main__":
    unmap_all_sensors()
