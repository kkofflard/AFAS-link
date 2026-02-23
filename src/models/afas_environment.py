import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from src.database import Base


class AfasEnvironment(Base):
    __tablename__ = "afas_environments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    environment_nr = Column(String(20), nullable=False)
    token_env_var = Column(String(100), nullable=False)
    afas_connector_id = Column(String(100), default="HrPersonContact")
    enabled = Column(Boolean, default=True)
    sync_interval_minutes = Column(Integer, default=15)
    last_incremental_sync_at = Column(DateTime, nullable=True)
    last_full_sync_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<AfasEnvironment(name={self.name}, env_nr={self.environment_nr})>"
