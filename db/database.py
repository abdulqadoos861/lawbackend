import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Load environmental variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Automatic fallback to local SQLite database if no PostgreSQL URL is configured
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///law_aggregator.db"
    # SQLite configuration for multithreading
    engine = create_engine(
        DATABASE_URL, 
        connect_args={"check_same_thread": False}
    )
else:
    # PostgreSQL configuration
    # Render/Supabase sometimes uses postgres:// which needs to be replaced with postgresql:// for SQLAlchemy
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Dependency helper for FastAPI routes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
