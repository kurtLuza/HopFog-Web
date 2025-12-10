from sqlalchemy import Column, Integer, String
from .connection import Base

class FogDevice(Base):
    __tablename__ = "fog_devices"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100))
    status = Column(String(50))
