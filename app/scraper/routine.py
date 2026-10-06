"""
Daily routine: today's Gmail drafts from the archive first, then new Google Maps searches from the
queue, only while ready leads run low. Runs in a worker thread, reports through Communicator.
"""

import random

from scraper import leads
from scraper.common import Common
from scraper.communicator import Communicator
from scraper.drafts import draft_today, gmail_service
from scraper.scraper import Backend
from settings import DAILY_DRAFTS, SEARCH_PAUSE, SEARCHES_PER_DAY, STOCK_DAYS


def run_routine():
    db = leads.connect()
    try:
        draft_today(gmail_service(), db)
    except Exception as e:  # no network, login refused: the searches can still run
        Communicator.show_message(f"Bozze non preparate: {e}")
    try:
        refill(db)
    except Exception as e:  # Chrome missing, driver download failed...
        Communicator.show_message(f"Ricerche interrotte: {e}")
    if leads.drafted_today(db) < DAILY_DRAFTS and not Common.close_thread_is_set():
        try:  # first day, or the archive ran dry: today's quota from the leads just found
            draft_today(gmail_service(), db)
        except Exception as e:
            Communicator.show_message(f"Bozze non preparate: {e}")
    try:
        leads.export(db)
        Communicator.show_message("Archivio aggiornato in output/contatti.xlsx")
    except PermissionError:
        Communicator.show_message("Non aggiorno output/contatti.xlsx: è aperto in Excel")
    finally:
        db.close()


def refill(db):
    """Searches from the queue until STOCK_DAYS of leads are ready: at most SEARCHES_PER_DAY a day,
    none after a captcha, a random pause between two"""
    while not Common.close_thread_is_set():
        ready = len(leads.pick(db))
        if ready >= DAILY_DRAFTS * STOCK_DAYS:
            Communicator.show_message(f"{ready} contatti pronti: bastano per i prossimi {STOCK_DAYS} giorni")
            return
        if leads.get_meta(db, "captcha") == leads.today() or leads.searches_today(db) >= SEARCHES_PER_DAY:
            Communicator.show_message("Ricerche di oggi finite, la coda riprende domani")
            return
        search = leads.next_search(db)
        if search is None:
            Communicator.show_message("Coda finita: aggiungi città o categorie nella cartella liste")
            return

        query, campaign, category, city = search
        leads.start_search(db, query)
        Communicator.show_message(f"Ricerca dalla coda: {query}")
        backend = Backend(query, Communicator.get_output_format(), healdessmode=1)
        completed = backend.mainscraping()
        added = leads.add_leads(db, backend.scroller.parser.finalData, campaign, category, city)
        leads.finish_search(db, query, added, completed)
        Communicator.show_message(f"{added} nuovi contatti in archivio da «{query}»")
        if Common.blocked.is_set():
            leads.set_meta(db, "captcha", leads.today())
            Communicator.show_message("Google ha chiesto un captcha: niente più ricerche fino a domani")
            return
        Common.closeThread.wait(random.uniform(*SEARCH_PAUSE))  # Ferma cuts the pause short
