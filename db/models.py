from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, text
from sqlalchemy.orm import relationship
from .database import Base
import datetime

class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    last_crawled = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, server_default=text("1"))
    scraper_type = Column(String, default="generic", nullable=False, server_default=text("'generic'"))

    updates = relationship("LawUpdate", back_populates="source", cascade="all, delete-orphan")



class LawUpdate(Base):
    __tablename__ = "updates"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    url = Column(String, nullable=True)
    pdf_url = Column(String, nullable=True)
    category = Column(String, nullable=True)  # Bill / Act / Ordinance
    date_found = Column(DateTime, default=datetime.datetime.utcnow, server_default=text("CURRENT_TIMESTAMP"))
    is_notified = Column(Boolean, default=False)

    source = relationship("Source", back_populates="updates")


class Admin(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=True)
    email = Column(String, unique=True, nullable=False, index=True)
