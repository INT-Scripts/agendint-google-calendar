import asyncio
import os
import logging
from datetime import date
from typing import List, Optional
from agendint import AgendaClient
from agendint.models import Event

logger = logging.getLogger(__name__)

async def fetch_events(start_date: date, end_date: date, hydrate: bool = True) -> List[Event]:
    """
    Connects to Agendint, fetches events for the specified date range.
    Optionally hydrates them to get full details (room, trainers).
    """
    login = os.getenv("AGENDINT_LOGIN")
    password = os.getenv("AGENDINT_PASSWORD")
    target_cal_id = os.getenv("AGENDINT_CALENDAR_ID")

    if not login or not password:
        logger.error("Missing AGENDINT_LOGIN or AGENDINT_PASSWORD in .env")
        return []

    async with AgendaClient() as client:
        logger.info("Authenticating with Agendint...")
        success = await client.login(login, password)
        if not success:
            logger.error("Authentication failed. Check your credentials.")
            return []
        
        logger.info(f"Authenticated successfully. Fetching calendars...")
        calendars = await client.list_calendars()
        
        if not calendars:
            logger.warning("No calendars found for this user.")
            return []

        # Find the correct calendar
        selected_cal = calendars[0]
        if target_cal_id:
            for cal in calendars:
                if cal.id == target_cal_id or cal.name.upper() == target_cal_id.upper() or cal.category.upper() == target_cal_id.upper():
                    selected_cal = cal
                    break

        logger.info(f"Selected calendar: {selected_cal.name} ({selected_cal.id})")
        
        logger.info(f"Fetching events from {start_date} to {end_date}...")
        events = await client.get_events(selected_cal.id, start_date, end_date)
        
        if not events:
            logger.info("No events found in this date range.")
            return []
            
        if hydrate:
            logger.info(f"Found {len(events)} events. Hydrating details (rooms, trainers, learners)...")
            # Hydrate all events to get room, trainer, learners, etc.
            await client.hydrate_events(events, concurrency=5, include_learners=True)
            logger.info("Events hydrated successfully.")
        else:
            logger.info(f"Found {len(events)} events. Skipping hydration.")
            
        return events
