"""
Gmail drafts for the scraped leads: one draft per business, nothing is sent automatically.
Ported from creaBozze.py.
"""

import base64
import csv
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

from scraper.communicator import Communicator
from scraper.parser import EMAIL_RE
from settings import DRAFTS_LOG, GMAIL_CLIENT_SECRET, GMAIL_TOKEN

SCOPES = [
    "https://www.googleapis.com/auth/gmail.compose",  # create the drafts
    "https://www.googleapis.com/auth/gmail.metadata",  # read To/Subject of drafts and sent mail, never the body
]
# Gmail caps requests per minute per user: on "rate limit exceeded" the client library waits
# (2, 4, 8... seconds, randomized) and retries, up to this many times
RETRIES = 8
SCAN_LIMIT = 3000  # first-use import: newest drafts and sent mails checked, ~40 outreach mails a day fit easily

TEMPLATES = {
    "promemoria": (
        "Promemoria WhatsApp per gli appuntamenti di {name}",
        """Buongiorno,

quanti appuntamenti saltano ogni mese perché il cliente si è semplicemente dimenticato? E quanto tempo perdete a ricordarlo a mano?

Sono Gabriele di MadHat Works. La mattina dell'appuntamento il vostro cliente riceve su WhatsApp un messaggio automatico con tre pulsanti: Confermo, Cancello, Arrivo tardi. Se disdice o avvisa che è in ritardo, vi arriva subito una mail e potete usare meglio quel tempo. Voi non dovete fare nulla.

Costa 39€/mese + IVA. Per chi firma entro il 31 dicembre, i primi due mesi sono a 29€.
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


def drafted(kind):
    """Emails that already got a draft of this kind, read from DRAFTS_LOG: clicking twice must not draft them again."""
    try:
        with open(DRAFTS_LOG, newline="", encoding="utf-8") as log:
            return {row["email"] for row in csv.DictReader(log) if row["tipo"] == kind}
    except FileNotFoundError:
        return set()


def gmail_history(service):
    """{(kind, email)} already drafted or sent from this Gmail with one of TEMPLATES' subjects (e.g. via
    creaBozze.py). Only To and Subject are read, any other mail is ignored."""
    prefixes = {subject.split("{name}")[0]: kind for kind, (subject, _) in TEMPLATES.items()}
    messages = service.users().messages()
    found, checked = set(), 0
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
                kind = next((k for prefix, k in prefixes.items() if headers.get("subject", "").startswith(prefix)), None)
                if kind:  # every recipient counts: creaBozze.py could put several in To
                    found.update((kind, email.lower()) for email in EMAIL_RE.findall(headers.get("to", "")))
                checked += 1
                if checked % 200 == 0:
                    Communicator.show_message(f"Controllati {checked} messaggi in Gmail...")
            request = messages.list_next(request, response)
    return found


def create_drafts(kind, path):
    """Runs in a worker thread: every outcome is reported through Communicator, nothing raises."""
    try:
        subject, body = TEMPLATES[kind]
        leads = load_leads(path)
        if not leads:
            Communicator.show_message(f"Nessuna email trovata in {os.path.basename(path)}")
            return

        os.makedirs(os.path.dirname(DRAFTS_LOG) or ".", exist_ok=True)
        # opened before the first draft: if Excel locks the file we stop now, not after drafts we can't record
        with open(DRAFTS_LOG, "a", newline="", encoding="utf-8") as log:
            service = gmail_service()
            if log.tell() == 0:  # new or empty log: mail drafted or sent before this app (creaBozze.py) counts as done
                Communicator.show_message(
                    "Primo utilizzo: controllo bozze e posta inviata in Gmail per non ricontattare nessuno "
                    "(una volta sola, può richiedere qualche minuto)...")
                imported = sorted(gmail_history(service))
                log.write("tipo,email,data\n")
                log.writelines(f"{k},{e},importata da Gmail\n" for k, e in imported)
                log.flush()
                Communicator.show_message(f"{len(imported)} contatti già fatti trovati in Gmail, verranno saltati")

            done = drafted(kind)
            todo = [(email, name) for email, name in leads if email not in done]
            if not todo:
                Communicator.show_message(
                    f"Nessuna bozza da creare: le {len(leads)} email di questo file sono già state contattate ({kind})")
                return
            skipped = len(leads) - len(todo)
            Communicator.show_message(
                f"Creo {len(todo)} bozze in Gmail..." + (f" ({skipped} saltate, già contattate)" if skipped else ""))

            created = 0
            for email, name in todo:
                message = EmailMessage()
                message.set_content(body)
                message["To"] = email
                message["Subject"] = subject.format(name=name or "Spettabile Attività")
                raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
                try:
                    service.users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute(
                        num_retries=RETRIES)
                except HttpError as e:
                    Communicator.show_message(f"Bozza non creata per {email}: {e}")
                    continue
                log.write(f"{kind},{email},{time.strftime('%Y-%m-%d %H:%M')}\n")
                log.flush()  # recorded right away: survives a crash or the window closed mid-run
                created += 1
        Communicator.show_message(f"Fatto: {created} bozze salvate in Gmail, controllale prima di inviarle")
    except PermissionError:
        Communicator.show_message(f"Chiudi {os.path.abspath(DRAFTS_LOG)} (è aperto in Excel?) e riprova")
    except Exception as e:  # bad file, login refused, revoked token (delete token.json and retry)
        Communicator.show_message(f"Errore durante la creazione delle bozze: {e}")
