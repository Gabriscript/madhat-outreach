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
from scraper.drafts import RETRIES, gmail_service
from scraper.routine import run_routine
from settings import DAILY_DRAFTS, OUTPUT_PATH, SEND_PAUSE


def log(message):
    with open(OUTPUT_PATH + "automatico.log", "a", encoding="utf-8") as f:
        f.write(f"{leads.now()}   {message}\n")


def send():
    """Drafts this app made before today and still in Gmail (deleted = not sent, edited = sent as edited),
    oldest first, at most DAILY_DRAFTS, spaced out. Personal drafts and older ones are never touched."""
    db = leads.connect()
    try:
        imported_at = leads.get_meta(db, "gmail_importato") or ""
        ours = {thread for (thread,) in db.execute(
            "SELECT thread FROM events WHERE kind IN ('promemoria', 'sito') AND thread IS NOT NULL AND at > ? AND at < ?",
            (imported_at, leads.today()))}
    finally:
        db.close()
    api = gmail_service().users().drafts()
    ready = []
    request = api.list(userId="me", maxResults=500)
    while request is not None:
        response = request.execute(num_retries=RETRIES)
        ready += [d["id"] for d in response.get("drafts", []) if d["message"]["threadId"] in ours]
        request = api.list_next(request, response)
    ready = ready[::-1][:DAILY_DRAFTS]  # Gmail lists newest first
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
        {"prepara": run_routine, "invia": send}[sys.argv[1]]()
    except Exception as e:
        log(f"Errore ({sys.argv[1:]}): {e}")
