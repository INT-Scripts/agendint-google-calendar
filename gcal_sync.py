import os
import time
import hashlib
import logging
from datetime import datetime, date
from typing import List, Dict, Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from agendint.models import Event

logger = logging.getLogger(__name__)

# Scopes needed for Google Calendar API
SCOPES = ['https://www.googleapis.com/auth/calendar']

def get_google_calendar_service():
    """
    Handles Google OAuth2 authentication.
    Reads credentials.json, prompts for login if token.json is missing,
    and returns an authenticated Calendar service.
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired Google tokens...")
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                logger.error("Missing credentials.json. Please download it from Google Cloud Console.")
                return None
            
            logger.info("Starting Google OAuth2 flow...")
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
            
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    try:
        service = build('calendar', 'v3', credentials=creds)
        return service
    except Exception as e:
        logger.error(f"Failed to build calendar service: {e}")
        return None

def generate_event_hash(event: Event) -> str:
    """
    Generates a unique hash for an event based on its core properties.
    If the hash changes, it means the event was updated on Agendint.
    """
    # Join key properties to form a unique string representing the event's current state
    core_props = [
        event.id or "",
        event.name or "",
        event.type or "",
        event.date or "",
        event.start_time or "",
        event.end_time or "",
        event.room or "",
        ",".join(event.trainers or []),
        ",".join(event.groups or []),
        ",".join(event.learners or [])
    ]
    raw_str = "|".join(core_props).encode('utf-8')
    return hashlib.md5(raw_str).hexdigest()

def agendint_to_gcal_event(event: Event) -> Dict[str, Any]:
    """
    Converts an Agendint Event to a Google Calendar Event dict.
    """
    # Create valid RFC3339 datetime strings
    start_dt = f"{event.date}T{event.start_time}:00"
    end_dt = f"{event.date}T{event.end_time}:00"
    
    # Format description
    desc_lines = []
    if event.type:
        desc_lines.append(f"Type: {event.type}")
    if event.trainers:
        desc_lines.append(f"Intervenant(s): {', '.join(event.trainers)}")
    if event.groups:
        desc_lines.append(f"Groupe(s): {', '.join(event.groups)}")
    if event.projects:
        desc_lines.append(f"Projet: {event.projects}")
    if event.learners:
        desc_lines.append(f"Étudiant(s): {', '.join(event.learners)}")
        
    description = "\n".join(desc_lines)
    
    # Store agendint_id and hash in extendedProperties to track sync state
    evt_hash = generate_event_hash(event)
    
    gcal_event = {
        'summary': event.name,
        'location': event.room or "",
        'description': description,
        'start': {
            'dateTime': start_dt,
            'timeZone': 'Europe/Paris',
        },
        'end': {
            'dateTime': end_dt,
            'timeZone': 'Europe/Paris',
        },
        'extendedProperties': {
            'private': {
                'agendint_id': str(event.id),
                'agendint_hash': evt_hash
            }
        }
    }
    return gcal_event

def get_existing_gcal_events(service, calendar_id: str, time_min: str, time_max: str) -> Dict[str, Any]:
    """
    Fetches all Google Calendar events within a timeframe that were created by this script.
    Returns a dictionary mapping agendint_id to the Google Calendar event resource.
    """
    existing_events = {}
    page_token = None
    
    while True:
        try:
            # We fetch all events, but we'll filter those having our private extended property
            events_result = service.events().list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                maxResults=250,
                pageToken=page_token
            ).execute()
            
            for evt in events_result.get('items', []):
                private_props = evt.get('extendedProperties', {}).get('private', {})
                if 'agendint_id' in private_props:
                    a_id = private_props['agendint_id']
                    existing_events[a_id] = evt
                    
            page_token = events_result.get('nextPageToken')
            if not page_token:
                break
                
        except HttpError as error:
            logger.error(f"An error occurred while fetching existing events: {error}")
            break
            
    return existing_events

def sync_events(scraped_events: List[Event], start_date: date, end_date: date, dry_run: bool = False):
    """
    Main sync logic: Diff existing Google Calendar events with freshly scraped events
    and apply Inserts, Updates, and Deletes.
    """
    service = get_google_calendar_service()
    if not service:
        logger.error("Google Calendar Service not initialized. Aborting sync.")
        return

    calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")
    if not calendar_id:
        calendar_id = "primary"

    # RFC3339 format for GCal API
    time_min = f"{start_date.isoformat()}T00:00:00Z"
    time_max = f"{end_date.isoformat()}T23:59:59Z"

    logger.info(f"Fetching existing events from Google Calendar between {time_min} and {time_max}...")
    existing_events = get_existing_gcal_events(service, calendar_id, time_min, time_max)
    logger.info(f"Found {len(existing_events)} previously synced events.")

    # Scraped dictionary for easy lookup
    scraped_dict = {str(e.id): e for e in scraped_events}
    
    to_insert = []
    to_update = []
    to_delete = []

    # 1. Find Inserts and Updates
    for a_id, a_evt in scraped_dict.items():
        if a_id not in existing_events:
            to_insert.append(a_evt)
        else:
            g_evt = existing_events[a_id]
            g_hash = g_evt.get('extendedProperties', {}).get('private', {}).get('agendint_hash')
            a_hash = generate_event_hash(a_evt)
            
            if g_hash != a_hash:
                to_update.append((a_evt, g_evt['id']))

    # 2. Find Deletes (events on GCal that are no longer scraped)
    for a_id, g_evt in existing_events.items():
        if a_id not in scraped_dict:
            to_delete.append(g_evt['id'])

    logger.info(f"Diff results: {len(to_insert)} to insert, {len(to_update)} to update, {len(to_delete)} to delete.")

    if dry_run:
        logger.info("DRY RUN: No modifications will be made to Google Calendar.")
        return

    def _execute_with_retry(request, evt_name, action_name):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                request.execute()
                logger.info(f"{action_name}: {evt_name}")
                time.sleep(0.5)  # Rate limiting
                return True
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Error for {evt_name} ({e}). Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Failed to {action_name.lower()} {evt_name} after {max_retries} attempts: {e}")
                    return False
                    
    # Insert
    for i, a_evt in enumerate(to_insert):
        gcal_evt = agendint_to_gcal_event(a_evt)
        req = service.events().insert(calendarId=calendar_id, body=gcal_evt)
        _execute_with_retry(req, f"{a_evt.name} ({a_evt.date})", "Inserted")

    # Update
    for i, (a_evt, gcal_id) in enumerate(to_update):
        gcal_evt = agendint_to_gcal_event(a_evt)
        req = service.events().update(calendarId=calendar_id, eventId=gcal_id, body=gcal_evt)
        _execute_with_retry(req, f"{a_evt.name} ({a_evt.date})", "Updated")

    # Delete
    for i, gcal_id in enumerate(to_delete):
        req = service.events().delete(calendarId=calendar_id, eventId=gcal_id)
        _execute_with_retry(req, f"event ID: {gcal_id}", "Deleted")

    logger.info("Synchronization complete!")
