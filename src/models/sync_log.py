import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
from src.database import Base


class SyncAction(str, enum.Enum):
    PROVISION = "provision"
    UPDATE = "update"
    DEPROVISION = "deprovision"
    GROUP_ASSIGN = "group_assign"
    GROUP_REMOVE = "group_remove"
    LICENSE_ASSIGN = "license_assign"
    LICENSE_REVOKE = "license_revoke"
    OU_MOVE = "ou_move"
    SYNC_START = "sync_start"
    SYNC_COMPLETE = "sync_complete"


class SyncTarget(str, enum.Enum):
    ENTRA_ID = "entra_id"
    ACTIVE_DIRECTORY = "active_directory"
    SYSTEM = "system"


class SyncStatus(str, enum.Enum):
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    INFO = "info"


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True, index=True)
    afas_environment_id = Column(Integer, nullable=True)

    action = Column(Enum(SyncAction), nullable=False)
    target = Column(Enum(SyncTarget), nullable=False)
    status = Column(Enum(SyncStatus), nullable=False)

    message = Column(Text, nullable=True)
    details = Column(JSON, nullable=True)

    # Relaties
    employee = relationship("Employee", back_populates="sync_logs")

    def __repr__(self) -> str:
        return f"<SyncLog(action={self.action}, target={self.target}, status={self.status})>"
