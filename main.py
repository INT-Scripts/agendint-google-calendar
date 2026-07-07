import asyncio
import logging
import argparse
import os
import json
from datetime import date, timedelta, datetime
from dotenv import load_dotenv

from scraper import fetch_events
from gcal_sync import sync_events

# Setup basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("sync.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

async def do_sync(dry_run: bool = False, hydrate: bool = True) -> bool:
    """
    Performs a single synchronization pass over the current school year.
    Returns True if successful, False if an error occurred.
    """
    try:
        today = date.today()
        # Logique d'année scolaire (Août à Août)
        # Si on est entre janvier et juillet, l'année scolaire a commencé l'année dernière.
        # Si on est entre août et décembre, la nouvelle année scolaire commence.
        if today.month < 8:
            start_date = date(today.year - 1, 8, 1)
            end_date = date(today.year, 8, 31)
        else:
            start_date = date(today.year, 8, 1)
            end_date = date(today.year + 1, 8, 31)
        
        logger.info(f"=== Starting Agenda Sync: {start_date} to {end_date} ===")
        
        # 1. Fetch events via agendint
        scraped_events = await fetch_events(start_date, end_date, hydrate=hydrate)
        
        if scraped_events is None:
            logger.warning("Scraper returned None (possible authentication or network error).")
            return False
            
        if not scraped_events:
            logger.warning("No events returned from scraper. Exiting pass.")
            return True # No events is technically a success, just nothing to sync
            
        # Save scraped events to a JSON file for history
        os.makedirs("scrape_history", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        history_file = f"scrape_history/events_{timestamp}.json"
        
        try:
            with open(history_file, "w", encoding="utf-8") as f:
                # Pydantic v2 uses model_dump()
                json.dump([evt.model_dump() for evt in scraped_events], f, ensure_ascii=False, indent=2)
            logger.info(f"Saved raw scraped data to {history_file}")
        except Exception as e:
            logger.warning(f"Failed to save JSON history: {e}")
            
        # 2. Sync to Google Calendar
        sync_events(scraped_events, start_date, end_date, dry_run=dry_run)
        
        logger.info("=== Sync finished ===")
        return True
    except Exception as e:
        logger.error(f"An unexpected error occurred during sync: {e}")
        return False

async def run_daemon(dry_run: bool, hydrate: bool, interval_hours: int, retry_hours: int):
    """
    Runs the synchronization in an infinite loop.
    """
    logger.info(f"Starting in Daemon mode. Interval: {interval_hours}h, Retry delay: {retry_hours}h")
    while True:
        success = await do_sync(dry_run, hydrate)
        
        if success:
            sleep_time = interval_hours * 3600
            logger.info(f"Sync successful. Sleeping for {interval_hours} hours until next run.")
        else:
            sleep_time = retry_hours * 3600
            logger.warning(f"Sync failed. Retrying in {retry_hours} hours.")
            
        await asyncio.sleep(sleep_time)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agendint to Google Calendar Sync")
    parser.add_argument("--dry-run", action="store_true", help="Perform a dry run without modifying Google Calendar")
    parser.add_argument("--no-hydrate", action="store_true", help="Skip event hydration (faster but misses room and trainer info)")
    
    # Daemon options
    parser.add_argument("--daemon", action="store_true", help="Run in a continuous loop")
    parser.add_argument("--interval", type=int, default=24, help="Hours to wait between successful runs in daemon mode (default: 24)")
    parser.add_argument("--retry-delay", type=int, default=1, help="Hours to wait before retrying on failure in daemon mode (default: 1)")
    
    args = parser.parse_args()
    
    load_dotenv()
    hydrate = not args.no_hydrate
    
    if args.daemon:
        asyncio.run(run_daemon(args.dry_run, hydrate, args.interval, args.retry_delay))
    else:
        asyncio.run(do_sync(args.dry_run, hydrate))
