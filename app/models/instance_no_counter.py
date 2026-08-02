from __future__ import annotations

from sqlalchemy import Column, Integer, String

from app.models.base import Base


class InstanceNoCounter(Base):
    """Instance number daily counter.

    Tracks the last used sequence number per day (YYYYMMDD) so that instance
    numbers are never reused even if the instance is later deleted.
    """

    __tablename__ = "instance_no_counters"

    date = Column(String(8), primary_key=True)
    last_seq = Column(Integer, nullable=False, default=0)
