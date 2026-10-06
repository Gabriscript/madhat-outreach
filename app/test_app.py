"""Run from the repo root: venv\\Scripts\\python app\\test_app.py"""

import os
import tempfile
import time
from collections import Counter
from types import SimpleNamespace

from scraper import drafts, leads
from scraper.communicator import Communicator
from scraper.drafts import load_leads
from scraper.parser import Parser, contact_links, domain_accepts_mail, extract_emails, site_signals

Communicator.set_frontend_object(SimpleNamespace(messageshowing=print))


def days_ago(days):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() - days * 86400))


def test_extract_emails():
    page = """
        <a href="mailto:Info@Pizzeria.it?subject=Ciao">Scrivici</a>
        <p>info@pizzeria.it - amministrazione@mail.pizzeria.co.uk - pec@pec.pizzeria.it - ditta@legalmail.it</p>
        <img src="logo@2x.png"> <p>tuo@example.com</p> <p>nome@dominio.it</p>
        <script>Sentry.init({dsn: "https://abc123@o123456.ingest.sentry.io/1"})</script>
        <p>ordini&#64;pizzeria.it</p>
        <span data-cfemail="5a39333b351a2a3320203f28333b74332e">[email protected]</span>
        <a href="/cdn-cgi/l/email-protection#5a39333b351a2a3320203f28333b74332e">mail</a>
        <span data-cfemail="ab"></span>
    """
    assert extract_emails(page) == [
        "info@pizzeria.it",
        "amministrazione@mail.pizzeria.co.uk",
        "ordini@pizzeria.it",
        "ciao@pizzeria.it",
    ]
    assert extract_emails("<p>nessuna email qui</p>") == []


def test_site_signals():
    old_site = '<p>Prenota su <a href="https://www.miodottore.it/x">MioDottore</a></p><footer>© 2015 Studio</footer>'
    assert site_signals(old_site, "http://studio.it/") == (True, 3)
    new_site = '<meta name="viewport" content="width=device-width"><footer>&copy; 2015 - 2026 Studio</footer>'
    assert site_signals(new_site, "https://studio.it/") == (False, 0)


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
    assert Parser(driver=None).find_mail("http://a..b/") == ("", False, None)  # malformed URL from Maps


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


def test_queue():
    with tempfile.TemporaryDirectory() as folder:
        leads.DB_PATH, leads.LISTS_PATH = os.path.join(folder, "test.db"), folder + os.sep
        for name, lines in (("citta.txt", "# capoluoghi\nRoma\nMilano"), ("promemoria.txt", "dentista\nbarbiere"),
                            ("sito.txt", "ristorante")):
            with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
                f.write(lines + "\n")
        assert [search[0] for search in leads.queue()] == [
            "dentista Roma", "barbiere Roma", "dentista Milano", "barbiere Milano", "ristorante Roma", "ristorante Milano"]
        assert leads.queue()[-1] == ("ristorante Milano", "sito", "ristorante", "Milano")

        db = leads.connect()
        assert leads.next_search(db)[0] == "dentista Roma"
        leads.start_search(db, "dentista Roma")
        assert leads.next_search(db)[0] == "barbiere Roma"  # never twice the same day, even if unfinished
        leads.finish_search(db, "dentista Roma", 12, completed=True)
        assert leads.searches_today(db) == 1

        for _ in range(3):  # a search that never finishes is dropped after 3 days
            leads.start_search(db, "barbiere Roma")
        db.execute("UPDATE searches SET started_at = '2020-01-01 09:00'")
        assert leads.next_search(db)[0] == "dentista Milano"
        db.close()


def test_pick_rules():
    with tempfile.TemporaryDirectory() as folder:
        leads.DB_PATH = os.path.join(folder, "test.db")
        db = leads.connect()
        rows = [
            {"Name": "Fresco", "email": "info@fresco.it"},
            {"Name": "Fresco bis", "email": "segreteria@fresco.it"},  # same own domain: one business
            {"Name": "Prenota", "email": "info@prenota.it", "Prenotazione online": True},  # booking: website first
            {"Name": "Gmail 1", "email": "uno@gmail.com"}, {"Name": "Gmail 2", "email": "due@gmail.com"},
            {"Name": "Vecchio", "email": "info@vecchio.it"}, {"Name": "Recente", "email": "info@recente.it"},
            {"Name": "Risposto", "email": "info@risposto.it"}, {"Name": "Cliente", "email": "info@cliente.it"},
            {"Name": "Senza email", "email": None},
        ]
        assert leads.add_leads(db, rows, "promemoria", "dentista", "Roma") == 8
        db.execute("UPDATE leads SET site_old = 3 WHERE email = 'info@prenota.it'")
        leads.record(db, "info@vecchio.it", "promemoria", days_ago(150))  # due for the website pitch
        leads.record(db, "info@recente.it", "promemoria", days_ago(30))  # too soon for a second pitch
        leads.record(db, "info@risposto.it", "promemoria", days_ago(200))
        leads.record(db, "info@risposto.it", "risposta", days_ago(190))  # replied: nothing more, ever
        leads.record(db, "altro@cliente.it", "altro", days_ago(400))  # we wrote to their domain before

        assert leads.pick(db) == [
            ("info@vecchio.it", "Vecchio", "sito"),  # second pitches first
            ("info@fresco.it", "Fresco", "promemoria"),
            ("uno@gmail.com", "Gmail 1", "promemoria"),  # shared provider: by address, not by domain
            ("due@gmail.com", "Gmail 2", "promemoria"),
            ("info@prenota.it", "Prenota", "sito"),
        ]
        assert leads.pick(db, 2) == leads.pick(db)[:2]
        assert not leads.can_pitch(db, "info@recente.it", "sito")
        assert leads.can_pitch(db, "info@vecchio.it", "sito")
        db.close()


class FakeGmail:
    """Stands in for the Gmail API: mail lives in lists, nothing reaches Google."""

    def __init__(self, existing):
        self.existing = existing  # {label: [{"to", "subject", "at", "thread"}]} already in Gmail
        self.created, self.sent = [], []
        self.listed = Counter()

    def users(self):
        return self

    def drafts(self):
        return self

    def messages(self):
        return self

    def create(self, userId, body):
        self.created.append(body)
        thread = f"new-{len(self.created)}"
        return SimpleNamespace(execute=lambda **retry: {"message": {"threadId": thread}})

    def send(self, userId, body):
        self.sent.append(body["id"])
        return SimpleNamespace(execute=lambda **retry: {})

    def list(self, userId, maxResults, labelIds=None):
        if labelIds is None:  # drafts().list
            drafts = [{"id": d["id"], "message": {"threadId": d["thread"]}} for d in self.existing.get("DRAFTS", [])]
            return SimpleNamespace(execute=lambda **retry: {"drafts": drafts})
        label = labelIds[0]
        self.listed[label] += 1
        items = [{"id": f"{label}:{i}", "threadId": m["thread"]} for i, m in enumerate(self.existing.get(label, []))]
        return SimpleNamespace(execute=lambda **retry: {"messages": items})

    def list_next(self, request, response):
        return None

    def get(self, userId, id, format, metadataHeaders):
        label, index = id.split(":")
        mail = self.existing[label][int(index)]
        headers = [{"name": "To", "value": mail["to"]}, {"name": "Subject", "value": mail["subject"]}]
        at = time.mktime(time.strptime(mail["at"], "%Y-%m-%d %H:%M")) * 1000
        return SimpleNamespace(execute=lambda **retry: {"payload": {"headers": headers}, "internalDate": str(int(at))})


def test_drafts_never_duplicated():
    promemoria = "Promemoria WhatsApp per gli appuntamenti di "
    gmail = FakeGmail(existing={
        "DRAFT": [{"to": "Studio A <a@studioa.it>", "subject": promemoria + "Studio A", "at": days_ago(5),
                   "thread": "t1"}],  # made by creaBozze.py, not sent yet
        "SENT": [
            {"to": "b@studiob.it", "subject": promemoria + "Studio B", "at": days_ago(150), "thread": "t2"},
            {"to": "Mario <d@amici.it>", "subject": "Cena di domenica", "at": days_ago(40), "thread": "t3"},
        ],
    })
    drafts.gmail_service = lambda: gmail
    with tempfile.TemporaryDirectory() as folder:
        leads.DB_PATH = os.path.join(folder, "test.db")
        leads_csv = os.path.join(folder, "leads.csv")
        with open(leads_csv, "w", encoding="utf-8") as f:
            f.write("Name,email\nStudio A,a@studioa.it\nStudio B,b@studiob.it\nAmici,d@amici.it\n")

        drafts.create_drafts("promemoria", leads_csv)  # A has a draft, B was emailed, D is personal: nothing
        assert len(gmail.created) == 0

        drafts.create_drafts("sito", leads_csv)  # only B: its Promemoria is 150 days old, A's just 5
        drafts.create_drafts("sito", leads_csv)  # second click on the same file
        assert len(gmail.created) == 1
        assert gmail.listed["DRAFT"] == gmail.listed["SENT"] == 1  # Gmail history imported once

        gmail.existing["INBOX"] = [{"thread": "new-1"}]  # B answers the website pitch
        with open(leads_csv, "a", encoding="utf-8") as f:
            f.write("Studio B segreteria,segreteria@studiob.it\nNuovo,e@nuovo.it\n")
        drafts.create_drafts("promemoria", leads_csv)  # same domain as B: skipped; only E
        assert len(gmail.created) == 2

        db = leads.connect()
        history = dict(db.execute("SELECT email, group_concat(kind) FROM events GROUP BY email"))
        db.close()
        assert history == {
            "a@studioa.it": "promemoria",
            "b@studiob.it": "promemoria,sito,risposta",
            "d@amici.it": "altro",
            "e@nuovo.it": "promemoria",
        }


def test_send_only_our_drafts_from_before_today():
    import automatico
    with tempfile.TemporaryDirectory() as folder:
        leads.DB_PATH, automatico.OUTPUT_PATH = os.path.join(folder, "test.db"), folder + os.sep
        db = leads.connect()
        leads.record(db, "a@x.it", "sito", days_ago(20), "vecchia")  # old backlog found by the import: first
        leads.record(db, "b@x.it", "promemoria", days_ago(1), "ieri")  # prepared yesterday: goes out
        leads.record(db, "c@x.it", "sito", days_ago(2), "cancellata")  # prepared, then deleted in Gmail
        leads.record(db, "d@x.it", "sito", leads.now(), "oggi")  # prepared today: tomorrow
        leads.record(db, "e@x.it", "sito", days_ago(30), "risposto")  # they answered overnight: your draft there
        db.close()                                                     # is a reply in progress, never sent
        gmail = FakeGmail(existing={"INBOX": [{"thread": "risposto"}], "DRAFTS": [
            {"id": f"draft-{thread}", "thread": thread} for thread in ("oggi", "ieri", "risposto", "vecchia", "personale")]})
        automatico.gmail_service = lambda: gmail
        automatico.send()
        assert gmail.sent == ["draft-vecchia", "draft-ieri"]


if __name__ == "__main__":
    test_extract_emails()
    test_site_signals()
    test_contact_links()
    test_find_mail_never_raises()
    test_domain_accepts_mail()
    test_load_leads()
    test_queue()
    test_pick_rules()
    test_drafts_never_duplicated()
    test_send_only_our_drafts_from_before_today()
    print("OK")
