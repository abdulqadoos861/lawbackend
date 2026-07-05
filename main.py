import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from db.database import engine, Base, SessionLocal
from db.models import Source, LawUpdate, Admin
from routes import updates, admin
from scraper.scheduler import start_scheduler, shutdown_scheduler

load_dotenv()

# Initialize database schemas
Base.metadata.create_all(bind=engine)

# Database seed function to populate targets if empty
def seed_database():
    db = SessionLocal()
    try:
        # 1. Seed / Update Sources
        source_specs = {
            1: {"name": "National Assembly of Pakistan", "url": "https://na.gov.pk", "scraper_type": "na"},
            2: {"name": "Senate of Pakistan", "url": "https://www.senate.gov.pk/en/publication.php?id=-1&catid=7&subcatid=246&cattitle=Rules%20and%20Acts", "scraper_type": "senate"},
            3: {"name": "Ministry of Law & Justice (Pakistan Code)", "url": "https://pakistancode.gov.pk/english/index.php", "scraper_type": "molaw"},
            4: {"name": "Punjab Assembly", "url": "https://pap.gov.pk/bills/show/en", "scraper_type": "punjab"},
            5: {"name": "Sindh Assembly", "url": "https://www.pas.gov.pk/bills", "scraper_type": "sindh"}
        }
        for src_id, spec in source_specs.items():
            db_source = db.query(Source).filter(Source.id == src_id).first()
            if db_source:
                db_source.name = spec["name"]
                db_source.url = spec["url"]
                db_source.scraper_type = spec["scraper_type"]
            else:
                new_src = Source(id=src_id, name=spec["name"], url=spec["url"], scraper_type=spec["scraper_type"], is_active=True)
                db.add(new_src)
        db.commit()
        print("Successfully updated/seeded database sources.")


        # 2. Seed Admins
        if db.query(Admin).count() == 0:
            admins = [
                Admin(id=1, name="Attorney General Office", email="attorney.general@law.gov.pk"),
                Admin(id=2, name="Lead Legislative Draftsman", email="drafting.desk@molaw.gov.pk")
            ]
            db.bulk_save_objects(admins)
            db.commit()
            print("Successfully seeded database admins.")

        # 3. Seed Initial Updates
        if db.query(LawUpdate).count() == 0:
            import datetime
            now = datetime.datetime.utcnow()
            updates_seed = [
                LawUpdate(
                    id=1,
                    source_id=1,
                    title="The National Commission for Human Rights (Amendment) Bill, 2026 - Bill No. 43 of 2026",
                    url="https://na.gov.pk/en/bills.php",
                    pdf_url="https://na.gov.pk/uploads/documents/bills/1719582210_928.pdf",
                    category="Bill",
                    date_found=now - datetime.timedelta(hours=10),
                    is_notified=True
                ),
                LawUpdate(
                    id=2,
                    source_id=4,
                    title="The Punjab Civil Servants (Amendment) Act, 2026 (Act VI of 2026)",
                    url="http://punjablaws.gov.pk/laws/3482.html",
                    pdf_url="http://punjablaws.gov.pk/laws/pdf/punjab_civil_servants_amendment_2026.pdf",
                    category="Act",
                    date_found=now - datetime.timedelta(hours=12),
                    is_notified=True
                ),
                LawUpdate(
                    id=3,
                    source_id=2,
                    title="The Islamabad Capital Territory Local Government (Amendment) Bill, 2026",
                    url="https://senate.gov.pk/en/bills_status.php",
                    pdf_url="https://senate.gov.pk/uploads/documents/bills/ict_local_govt_amend_2026.pdf",
                    category="Bill",
                    date_found=now - datetime.timedelta(hours=15),
                    is_notified=True
                )
            ]
            db.bulk_save_objects(updates_seed)
            db.commit()
            print("Successfully seeded initial law updates.")
            
    except Exception as e:
        print(f"Error seeding database: {e}")
        db.rollback()
    finally:
        db.close()

# Execute seeds
seed_database()

# Create FastAPI instance
app = FastAPI(
    title="Pakistan Law Aggregator API",
    description="Automated system daily crawling, parsing, and alerting for new Pakistani legislation, bills, and acts.",
    version="1.0.0"
)

# Configure CORS Middleware
origins_raw = os.getenv("CORS_ORIGINS", "http://localhost:3000")
origins = [origin.strip() for origin in origins_raw.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(updates.router, prefix="/api", tags=["Updates"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin Control"])

# Startup Event
@app.on_event("startup")
async def startup_event():
    start_scheduler()

# Shutdown Event
@app.on_event("shutdown")
async def shutdown_event():
    shutdown_scheduler()

@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": "Pakistan Law Aggregator Backend API Core",
        "scheduler": "active"
    }

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
