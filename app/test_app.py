"""Run from the repo root: venv\\Scripts\\python app\\test_app.py"""

import os
import tempfile
from types import SimpleNamespace

from scraper import drafts
from scraper.communicator import Communicator
from scraper.drafts import load_leads
from scraper.parser import Parser, contact_links, domain_accepts_mail, extract_emails


def test_extract_emails():
    page = """
        <a href="mailto:Info@Pizzeria.it?subject=Ciao">Scrivici</a>
        <p>info@pizzeria.it - amministrazione@pec.pizzeria.co.uk</p>
        <img src="logo@2x.png"> <p>tuo@example.com</p> <p>nome@dominio.it</p>
        <script>Sentry.init({dsn: "https://abc123@o123456.ingest.sentry.io/1"})</script>
        <p>ordini&#64;pizzeria.it</p>
        <span data-cfemail="5a39333b351a2a3320203f28333b74332e">[email protected]</span>
        <a href="/cdn-cgi/l/email-protection#5a39333b351a2a3320203f28333b74332e">mail</a>
        <span data-cfemail="ab"></span>
    """
    assert extract_emails(page) == [
        "info@pizzeria.it",
        "amministrazione@pec.pizzeria.co.uk",
        "ordini@pizzeria.it",
        "ciao@pizzeria.it",
    ]
    assert extract_emails("<p>nessuna email qui</p>") == []


def test_contact_links():
    page = """
        <a href="/contatti">Contatti</a>
        <a href="/contatti/#mappa">Dove siamo</a>
        <a href="https://WWW.Pizzeria.it/contact-us/ ">Contact</a>
        <a href="/chi-siamo">Chi siamo</a>
        <a href="https://facebook.com/pizzeria/contact">Facebook</a>
        <a href="mailto:contact@pizzeria.it">Mail</a>
    """
    assert contact_links(page, "https://pizzeria.it/") == [
        "https://pizzeria.it/contatti",
        "https://WWW.Pizzeria.it/contact-us",
    ]


def test_find_mail_never_raises():
    Communicator.set_frontend_object(SimpleNamespace(messageshowing=print))
    assert Parser(driver=None).find_mail("http://a..b/") == ""  # malformed URL from Maps


def test_domain_accepts_mail():  # needs network (real DNS)
    assert domain_accepts_mail("gmail.com")
    assert not domain_accepts_mail("dominio-inesistente-gms-test-8471.it")


def test_load_leads():
    with tempfile.TemporaryDirectory() as folder:
        scraper_csv = os.path.join(folder, "scraper.csv")
        with open(scraper_csv, "w", encoding="utf-8") as f:
            f.write('Name,email\n"Pizzeria\nDa Mario","Info@Mario.it, eventi@mario.it"\nSenza Mail,\nCatena,info@mario.it\n')
        assert load_leads(scraper_csv) == [("info@mario.it", "Pizzeria Da Mario")]

        outscraper_csv = os.path.join(folder, "outscraper.csv")  # tab separated, BOM before "Name"
        with open(outscraper_csv, "w", encoding="utf-8-sig") as f:
            f.write("Name\tEmail\nStudio Rossi\tstudio@rossi.it\n")
        assert load_leads(outscraper_csv) == [("studio@rossi.it", "Studio Rossi")]


class FakeGmail:
    """Stands in for the Gmail API: drafts live in lists, nothing reaches Google."""

    def __init__(self, existing):
        self.existing = existing  # {label: [(To, Subject)]} already in Gmail before the app runs
        self.created = []
        self.listed = 0

    def users(self):
        return self

    def drafts(self):
        return self

    def messages(self):
        return self

    def create(self, userId, body):
        self.created.append(body)
        return SimpleNamespace(execute=dict)

    def list(self, userId, labelIds, maxResults):
        self.listed += 1
        ids = [f"{labelIds[0]}:{i}" for i in range(len(self.existing.get(labelIds[0], [])))]
        return SimpleNamespace(execute=lambda: {"messages": [{"id": i} for i in ids]})

    def list_next(self, request, response):
        return None

    def get(self, userId, id, format, metadataHeaders):
        label, index = id.split(":")
        to, subject = self.existing[label][int(index)]
        headers = [{"name": "To", "value": to}, {"name": "Subject", "value": subject}]
        return SimpleNamespace(execute=lambda: {"payload": {"headers": headers}})


def test_drafts_never_duplicated():
    Communicator.set_frontend_object(SimpleNamespace(messageshowing=print))
    gmail = FakeGmail(existing={
        "DRAFT": [("Studio A <a@studio.it>", "Promemoria WhatsApp per gli appuntamenti di Studio A")],  # creaBozze.py
        "SENT": [
            ("b@studio.it, c@studio.it", "Promemoria WhatsApp per gli appuntamenti di Studio B"),  # creaBozze.py, sent
            ("Mario <d@amici.it>", "Cena di domenica"),  # personal mail: not ours, must be ignored
        ],
    })
    drafts.gmail_service = lambda: gmail
    with tempfile.TemporaryDirectory() as folder:
        drafts.DRAFTS_LOG = os.path.join(folder, "output", "bozze_create.csv")
        leads_csv = os.path.join(folder, "leads.csv")
        with open(leads_csv, "w", encoding="utf-8") as f:
            f.write("Name,email\nStudio A,a@studio.it\nStudio B,b@studio.it\n")

        drafts.create_drafts("promemoria", leads_csv)  # A has a draft, B was already emailed: nothing to do
        assert len(gmail.created) == 0
        assert gmail.listed == 2  # drafts + sent mail scanned on the first run

        drafts.create_drafts("sito", leads_csv)
        drafts.create_drafts("sito", leads_csv)  # second click on the same file
        assert len(gmail.created) == 2
        assert gmail.listed == 2  # ...and only on the first run

        with open(leads_csv, "a", encoding="utf-8") as f:  # new businesses in the file: only those
            f.write("Studio C,c@studio.it\nStudio E,e@studio.it\n")
        drafts.create_drafts("promemoria", leads_csv)  # C was in the To of a sent mail: only E
        assert len(gmail.created) == 3
        assert drafts.drafted("promemoria") == {"a@studio.it", "b@studio.it", "c@studio.it", "e@studio.it"}
        assert "d@amici.it" not in drafts.drafted("promemoria") | drafts.drafted("sito")


if __name__ == "__main__":
    test_extract_emails()
    test_contact_links()
    test_find_mail_never_raises()
    test_domain_accepts_mail()
    test_load_leads()
    test_drafts_never_duplicated()
    print("OK")
