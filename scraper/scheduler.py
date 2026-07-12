from apscheduler.schedulers.background import BackgroundScheduler
import logging
from db.database import SessionLocal
from scraper.crawler import crawl_all_sources

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()

def scheduled_crawl_job():
    logger.info("Executing daily automated crawl scheduler job.")
    db = SessionLocal()
    try:
        import datetime
        today = datetime.date.today()
        results = crawl_all_sources(db, fallback=False, until_date=today)
        logger.info(f"Scheduled crawl job finished. Extracted updates: {results}")
    except Exception as e:
        logger.error(f"Error during scheduled crawl execution: {e}")
    finally:
        db.close()

def start_scheduler():
    if not scheduler.running:
        # Run every 6 hours so crawls aren't missed if Render free-tier sleeps
        # and the service is asleep at the exact 6 AM cron window
        scheduler.add_job(
            scheduled_crawl_job,
            'interval',
            hours=6,
            id='crawl_job',
            replace_existing=True
        )
        scheduler.start()
        logger.info("APScheduler Background Thread Started. Crawl task scheduled every 6 hours.")
        # Run an immediate crawl on startup so fresh data is always loaded on wake-up
        import threading
        threading.Thread(target=scheduled_crawl_job, daemon=True).start()
        logger.info("Immediate startup crawl triggered in background thread.")

def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("APScheduler Background Thread Shutdown.")
