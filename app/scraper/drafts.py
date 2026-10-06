"""
Gmail drafts for the scraped leads: one draft per business, nothing is sent automatically.
Who was already contacted lives in the archive (leads.py). Ported from creaBozze.py.
"""

import base64
import os
import time
from email.message import EmailMessage

import pandas as pd
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from scraper import leads
from scraper.communicator import Communicator
from scraper.parser import EMAIL_RE
from settings import DAILY_DRAFTS, GMAIL_CLIENT_SECRET, GMAIL_TOKEN

SCOPES = [
    "https://www.googleapis.com/auth/gmail.compose",  # create the drafts
    "https://www.googleapis.com/auth/gmail.metadata",  # read To/Subject of drafts and sent mail, never the body
]
# Gmail caps requests per minute per user: on "rate limit exceeded" the client library waits
# (2, 4, 8... seconds, randomized) and retries, up to this many times
RETRIES = 8
SCAN_LIMIT = 3000  # first-use import: newest drafts and sent mails checked, ~40 outreach mails a day fit easily
# Subjects of the outreach sent before this app, found in Sent: they count as that campaign when importing
OLD_SUBJECTS = {"Un restyling per il sito": "sito", "Il vostro sito": "sito", "Proposta sito web": "sito"}
INBOX_SCAN = 2000  # newest inbox messages checked for replies at every run (list only, cheap)

TEMPLATES = {
    "promemoria": (
        "Promemoria WhatsApp per gli appuntamenti di {name}",
        """Buongiorno,

quanti appuntamenti saltano ogni mese perché il cliente si è semplicemente dimenticato? E quanto tempo perdete a ricordarlo a mano?

Sono Gabriele di MadHat Works. La mattina dell'appuntamento il vostro cliente riceve su WhatsApp un messaggio automatico con tre pulsanti: Confermo, Cancello, Arrivo tardi. Se disdice o avvisa che è in ritardo, vi arriva subito una mail e potete usare meglio quel tempo. Voi non dovete fare nulla.

Costa 39€/mese + IVA, e i primi due mesi sono a 29€.
Se preferite l'email a WhatsApp: 19€/mese + IVA, primi due mesi a 9,90€.

Rispondete "esempio" e vi mando il messaggio esatto che riceverebbero i vostri clienti, con il nome della vostra attività.

Gabriele — MadHat Works
www.madhatworks.com""",
    ),
    "sito": (
        "Un nuovo look per il sito di {name}",
        """Buongiorno,

sono Gabriele di MadHat Works. Rinnovo i siti web delle piccole attività locali: li rendo moderni, veloci e comodi da usare anche da cellulare, con hosting e manutenzione inclusi a partire da 29€/mese + IVA.

Il sito è spesso la prima cosa che un nuovo cliente vede di voi: se è curato, trasmette professionalità e fiducia ancora prima del primo contatto.

Se vi interessa, preparo un'anteprima di come potrebbe diventare il vostro, senza impegno.

Vi va di vederla?

A presto,
Gabriele — MadHat Works
www.madhatworks.com""",
    ),
}

def load_leads(path):
    """[(email, business name)] from a scraper output (xlsx/csv/json) or an Outscraper csv.
    First email of each business only, one draft per address."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".xlsx":
        df = pd.read_excel(path)
    elif ext == ".json":
        df = pd.read_json(path)
    else:  # sniffs comma vs tab (Outscraper); the sniffing engine keeps the BOM before "Name", utf-8-sig drops it
        df = pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig")

    column = next((c for c in ("email", "Email", "Contact email") if c in df.columns), None)
    if column is None:
        return []
    leads = {}
    for row in df.fillna("").to_dict("records"):
        match = EMAIL_RE.search(str(row[column]))
        if match:
            # " ".join(split()) also strips newlines: a name from Maps must not break the Subject header
            leads.setdefault(match.group().lower(), " ".join(str(row.get("Name", "")).split()))
    return list(leads.items())


def gmail_service():
    """Browser login only the first time, then the saved token is reused (and refreshed)."""
    creds = Credentials.from_authorized_user_file(GMAIL_TOKEN, SCOPES) if os.path.exists(GMAIL_TOKEN) else None
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:  # while the Google Cloud app is in "Testing", Google revokes the login after 7 days
            creds = None
    if not creds or not creds.valid:
        creds = InstalledAppFlow.from_client_secrets_file(GMAIL_CLIENT_SECRET, SCOPES).run_local_server(port=0)
    with open(GMAIL_TOKEN, "w") as token:
        token.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def import_gmail(service, db):
    """Once, on first use: everyone already emailed from this Gmail (drafts and sent mail) goes in the archive,
    with date and thread. Our two subjects count as that campaign; any other mail as "altro", which is never
    cold-pitched: clients, friends and older outreach with other subjects. Only To and Subject are read."""
    prefixes = {subject.split("{name}")[0]: kind for kind, (subject, _) in TEMPLATES.items()} | OLD_SUBJECTS
    messages = service.users().messages()
    checked = 0
    # ponytail: one request per message (~10/s), a big Sent folder takes a few minutes, once;
    # switch to batch requests if that wait becomes a problem
    for label in ("DRAFT", "SENT"):
        request = messages.list(userId="me", labelIds=[label], maxResults=500)
        start = checked
        # ponytail: newest SCAN_LIMIT per label only (Gmail lists newest first), older outreach isn't seen
        while request is not None and checked - start < SCAN_LIMIT:
            response = request.execute(num_retries=RETRIES)
            for item in response.get("messages", []):
                message = messages.get(
                    userId="me", id=item["id"], format="metadata", metadataHeaders=["To", "Subject"]
                ).execute(num_retries=RETRIES)
                headers = {h["name"].lower(): h["value"] for h in message.get("payload", {}).get("headers", [])}
                subject = headers.get("subject", "").strip()
                # the old website outreach went out without a subject too
                kind = next((k for prefix, k in prefixes.items() if subject.startswith(prefix)),
                            "altro" if subject else "sito")
                at = time.strftime("%Y-%m-%d %H:%M", time.localtime(int(message["internalDate"]) / 1000))
                for email in EMAIL_RE.findall(headers.get("to", "")):  # every recipient counts
                    leads.record(db, email.lower(), kind, at, item["threadId"])
                checked += 1
                if checked % 200 == 0:
                    Communicator.show_message(f"Controllati {checked} messaggi in Gmail...")
            request = messages.list_next(request, response)
    leads.set_meta(db, "gmail_importato", leads.now())


def scan_replies(service, db):
    """An inbox message inside a thread we started is a reply or a bounce: that business gets nothing more
    automatically. Matching threads needs no message bodies and only list calls."""
    ours = dict(db.execute("SELECT thread, email FROM events WHERE thread IS NOT NULL AND kind IN ('promemoria', 'sito')"))
    known = {email for (email,) in db.execute("SELECT email FROM events WHERE kind = 'risposta'")}
    request = service.users().messages().list(userId="me", labelIds=["INBOX"], maxResults=500)
    seen = 0
    while request is not None and seen < INBOX_SCAN:
        response = request.execute(num_retries=RETRIES)
        for item in response.get("messages", []):
            email = ours.get(item["threadId"])
            if email and email not in known:
                leads.record(db, email, "risposta", thread=item["threadId"])
                known.add(email)
                Communicator.show_message(f"Nuova risposta da {email}: non riceverà altre email automatiche")
        seen += len(response.get("messages", []))
        request = service.users().messages().list_next(request, response)


def prepare(service, db):
    """Before any draft: history from Gmail on first use, then replies"""
    if not leads.get_meta(db, "gmail_importato"):
        Communicator.show_message("Primo utilizzo: controllo bozze e posta inviata in Gmail per non ricontattare "
                                  "nessuno (una volta sola, può richiedere qualche minuto)...")
        import_gmail(service, db)
    scan_replies(service, db)


def draft(service, db, email, name, kind):
    """One Gmail draft, recorded in the archive at once with its thread (that's how replies are spotted)"""
    subject, body = TEMPLATES[kind]
    message = EmailMessage()
    message.set_content(body)
    message["To"] = email
    message["Subject"] = subject.format(name=name or "Spettabile Attività")
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    created = service.users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute(
        num_retries=RETRIES)
    leads.record(db, email, kind, thread=created["message"]["threadId"])


def draft_today(service, db):
    """Today's drafts from the archive, up to DAILY_DRAFTS a day whatever the number of runs"""
    prepare(service, db)
    todo = leads.pick(db, max(DAILY_DRAFTS - leads.drafted_today(db), 0))
    if not todo:
        Communicator.show_message("Nessuna bozza da preparare oggi")
        return
    Communicator.show_message(f"Preparo {len(todo)} bozze in Gmail...")
    created = 0
    for email, name, kind in todo:
        try:
            draft(service, db, email, name, kind)
            created += 1
        except HttpError as e:
            Communicator.show_message(f"Bozza non creata per {email}: {e}")
    Communicator.show_message(f"Fatto: {created} bozze salvate in Gmail, controllale prima di inviarle")


def create_drafts(kind, path):
    """Drafts from a results file. Runs in a worker thread: every outcome goes through Communicator, nothing raises."""
    db = leads.connect()
    try:
        rows = load_leads(path)
        if not rows:
            Communicator.show_message(f"Nessuna email trovata in {os.path.basename(path)}")
            return
        service = gmail_service()
        prepare(service, db)
        todo = [(email, name) for email, name in rows if leads.can_pitch(db, email, kind)]
        if not todo:
            Communicator.show_message(
                f"Nessuna bozza da creare: le {len(rows)} email di questo file sono già state contattate ({kind})")
            return
        skipped = len(rows) - len(todo)
        Communicator.show_message(
            f"Creo {len(todo)} bozze in Gmail..." + (f" ({skipped} saltate, già contattate)" if skipped else ""))
        created = 0
        for email, name in todo:
            # in the archive too, so the other campaign can follow after SECOND_PITCH_DAYS
            db.execute("INSERT OR IGNORE INTO leads (email, domain, name, campaign, added_at) VALUES (?, ?, ?, ?, ?)",
                       (email, leads.own_domain(email), name, kind, leads.now()))
            try:
                draft(service, db, email, name, kind)
                created += 1
            except HttpError as e:
                Communicator.show_message(f"Bozza non creata per {email}: {e}")
        Communicator.show_message(f"Fatto: {created} bozze salvate in Gmail, controllale prima di inviarle")
    except Exception as e:  # bad file, login refused, revoked token (delete token.json and retry)
        Communicator.show_message(f"Errore durante la creazione delle bozze: {e}")
    finally:
        db.close()
