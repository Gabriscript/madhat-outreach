"""
Unattended runs for the Windows Task Scheduler: no window, everything goes to output/automatico.log.
  prepara: the daily routine, same as the "Prepara le bozze di oggi" button
  invia:   sends the drafts this app prepared before today, so there was a day to read them
Run from the repo root: venv\\Scripts\\pythonw.exe app\\automatico.py prepara|invia
"""

import random
import sys
import time
from types import SimpleNamespace

from scraper import drafts, leads
from scraper.communicator import Communicator
from scraper.drafts import RETRIES, gmail_service, scan_replies, waiting_drafts
from scraper.routine import run_routine
from settings import DAILY_DRAFTS, OUTPUT_PATH, SEND_PAUSE


def log(message):
    with open(OUTPUT_PATH + "automatico.log", "a", encoding="utf-8") as f:
        f.write(f"{leads.now()}   {message}\n")


def send():
    """Pitch drafts prepared before today and still in Gmail (deleted = not sent, edited = sent as edited),
    oldest first, at most DAILY_DRAFTS, spaced out. Personal drafts and replies are never touched."""
    service = gmail_service()
    db = leads.connect()
    try:
        scan_replies(service, db)  # a reply that came in overnight keeps its thread out
        ready = [draft_id for draft_id, at in waiting_drafts(service, db) if at < leads.today()][:DAILY_DRAFTS]
    finally:
        db.close()
    api = service.users().drafts()
    log(f"Invio {len(ready)} bozze preparate nei giorni scorsi")
    for i, draft_id in enumerate(ready):
        if i:
            time.sleep(random.uniform(*SEND_PAUSE))
        api.send(userId="me", body={"id": draft_id}).execute(num_retries=RETRIES)
    log(f"Inviate {len(ready)} email")


if __name__ == "__main__":
    drafts.INTERACTIVE = False
    Communicator.set_frontend_object(SimpleNamespace(
        messageshowing=log, progressshowing=lambda done, total: None, end_processing=lambda: None,
        outputFormatValue="excel"))
    try:
        # sending is done by the Google Apps Script trigger (runs with the PC off); uncomment to send from here
        {"prepara": run_routine,
         # "invia": send,
         }[sys.argv[1]]()
    except Exception as e:
        log(f"Errore ({sys.argv[1:]}): {e}")
