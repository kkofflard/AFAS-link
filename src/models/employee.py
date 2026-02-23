import enum
from datetime import datetime, date
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, Enum, ForeignKey, JSON
from sqlalchemy.orm import relationship
from src.database import Base


class EmployeeStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "actief"
    DISABLED = "uitgeschakeld"
    ERROR = "fout"


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    afas_employee_id = Column(String(50), nullable=False, index=True)
    afas_environment_id = Column(Integer, ForeignKey("afas_environments.id"), nullable=False)

    # Persoonsgegevens
    first_name = Column(String(100), nullable=True)
    initials = Column(String(20), nullable=True)
    last_name = Column(String(200), nullable=True)
    display_name = Column(String(300), nullable=True)

    # HR-attributen
    function = Column(String(200), nullable=True)
    department = Column(String(200), nullable=True)
    team = Column(String(200), nullable=True)
    cost_center = Column(String(100), nullable=True)

    # Dienstverband
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)

    # Gegenereerde identiteit
    generated_email = Column(String(300), nullable=True, index=True)
    generated_username = Column(String(100), nullable=True)

    # Externe systeem-ID's
    entra_id_object_id = Column(String(100), nullable=True, index=True)
    ad_dn = Column(String(500), nullable=True)

    # Status
    status = Column(Enum(EmployeeStatus), default=EmployeeStatus.PENDING, nullable=False)

    # Tijdstempels
    last_synced_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relaties
    sync_logs = relationship("SyncLog", back_populates="employee", lazy="dynamic")
    environment = relationship("AfasEnvironment")

    @property
    def full_name(self) -> str:
        parts = []
        if self.first_name:
            parts.append(self.first_name)
        if self.last_name:
            parts.append(self.last_name)
        return " ".join(parts) if parts else self.display_name or "Onbekend"

    @property
    def is_active(self) -> bool:
        return self.status == EmployeeStatus.ACTIVE

    @property
    def has_entra_id(self) -> bool:
        return bool(self.entra_id_object_id)

    @property
    def has_ad(self) -> bool:
        return bool(self.ad_dn)

    def __repr__(self) -> str:
        return f"<Employee(id={self.afas_employee_id}, name={self.full_name}, status={self.status})>"
