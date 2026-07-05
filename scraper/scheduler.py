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
        # Schedule the crawling to run every day at 6:00 AM
        scheduler.add_job(
            scheduled_crawl_job, 
            'cron', 
            hour=6, 
            minute=0, 
            id='daily_crawl_job',
            replace_existing=True
        )
        scheduler.start()
        logger.info("APScheduler Background Thread Started. Crawl task scheduled daily at 06:00 AM.")

def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("APScheduler Background Thread Shutdown.")
