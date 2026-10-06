"""
Archive of the outreach: searches done, businesses found, every email drafted or sent.
One SQLite file (Python standard library): every write is on disk at once, Excel can't lock it,
and each thread opens its own connection.
"""

import os
import sqlite3
import time

import pandas as pd

from scraper.parser import EMAIL_RE
from settings import DAILY_DRAFTS, DB_PATH, LISTS_PATH, OUTPUT_PATH, SECOND_PITCH_DAYS

# ponytail: the common Italian providers only; a business on another shared provider is matched by its
# full address instead of its domain. Extend when one slips through
FREEMAIL = {
    "gmail.com", "googlemail.com", "libero.it", "hotmail.it", "hotmail.com", "outlook.it", "outlook.com",
    "live.it", "live.com", "msn.com", "yahoo.it", "yahoo.com", "icloud.com", "me.com", "alice.it", "tin.it",
    "tiscali.it", "virgilio.it", "email.it", "inwind.it", "fastwebnet.it", "aol.com",
}

# events.kind: "promemoria" / "sito" = that pitch drafted (or found already sent in Gmail),
# "altro" = any other mail we sent to them (never cold-pitched), "risposta" = a reply or bounce to a pitch
SCHEMA = """
CREATE TABLE IF NOT EXISTS searches (
    query TEXT PRIMARY KEY, started_at TEXT, done_at TEXT, attempts INTEGER DEFAULT 0, found INTEGER);
CREATE TABLE IF NOT EXISTS leads (
    email TEXT PRIMARY KEY, domain TEXT, name TEXT, category TEXT, city TEXT, phone TEXT, website TEXT,
    campaign TEXT, site_old INTEGER DEFAULT 0, added_at TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS one_business_per_domain ON leads(domain) WHERE domain IS NOT NULL;
CREATE TABLE IF NOT EXISTS events (email TEXT, domain TEXT, kind TEXT, at TEXT, thread TEXT);
CREATE INDEX IF NOT EXISTS events_by_email ON events(email);
CREATE INDEX IF NOT EXISTS events_by_domain ON events(domain);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""

# Who can get which pitch, for the routine and for drafts from a file alike. Nothing may block it:
# no email of the same kind, no other mail from us, no reply, nothing at all in the last SECOND_PITCH_DAYS.
# A business gets its own campaign first; the other one only as a second pitch.
# Order: second pitches due, then Promemoria, then Sito web from the most dated sites
BLOCKED = """EXISTS (SELECT 1 FROM events e WHERE (e.email = {email} OR e.domain = {domain})
             AND (e.kind IN ({kind}, 'altro', 'risposta') OR e.at > :cutoff))"""
PICK = f"""
SELECT l.email, l.name, k.kind FROM leads l JOIN (SELECT 'promemoria' AS kind UNION ALL SELECT 'sito') k
WHERE NOT {BLOCKED.format(email="l.email", domain="l.domain", kind="k.kind")}
  AND (k.kind = l.campaign OR EXISTS (SELECT 1 FROM events e WHERE (e.email = l.email OR e.domain = l.domain)
                                      AND e.kind IN ('promemoria', 'sito')))
ORDER BY k.kind <> l.campaign DESC, k.kind = 'sito', l.site_old DESC, l.added_at
LIMIT :limit
"""


def connect():
    """A new connection (one per thread), tables created on first use, autocommit"""
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    db = sqlite3.connect(DB_PATH, isolation_level=None, timeout=30)
    db.executescript(SCHEMA)
    return db


def now():
    return time.strftime("%Y-%m-%d %H:%M")


def today():
    return time.strftime("%Y-%m-%d")


def cutoff():
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() - SECOND_PITCH_DAYS * 86400))


def own_domain(email):
    """The business's own mail domain, None on shared providers (gmail.com, libero.it...)"""
    domain = email.rsplit("@", 1)[1]
    return None if domain in FREEMAIL else domain


def record(db, email, kind, at=None, thread=None):
    db.execute("INSERT INTO events VALUES (?, ?, ?, ?, ?)", (email, own_domain(email), kind, at or now(), thread))


def can_pitch(db, email, kind):
    query = "SELECT " + BLOCKED.format(email=":email", domain=":domain", kind=":kind")
    return not db.execute(query, {"email": email, "domain": own_domain(email), "kind": kind,
                                  "cutoff": cutoff()}).fetchone()[0]


def pick(db, limit=-1):
    """[(email, name, kind)] that can be drafted now, best first (-1 = all)"""
    return db.execute(PICK, {"cutoff": cutoff(), "limit": limit}).fetchall()


def drafted_today(db):
    return db.execute("SELECT COUNT(*) FROM events WHERE kind IN ('promemoria', 'sito') AND at >= ?",
                      (today(),)).fetchone()[0]


def add_leads(db, rows, campaign, category, city):
    """Businesses with an email from one search, each email and own domain kept once.
    Online booking already sends reminders: those businesses start with the website pitch."""
    added = 0
    for row in rows:
        match = EMAIL_RE.search(str(row.get("email") or ""))
        if match:
            email = match.group().lower()
            added += db.execute(
                "INSERT OR IGNORE INTO leads VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (email, own_domain(email), row.get("Name"), category, city, row.get("Phone"), row.get("Website"),
                 "sito" if row.get("Prenotazione online") else campaign, row.get("Sito datato") or 0, now()),
            ).rowcount
    return added


def read_list(name):
    with open(LISTS_PATH + name, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]


def queue():
    """[(query, campaign, category, city)] in order: Promemoria categories city by city (largest first),
    then the Sito web ones. Rebuilt from liste/ every time, so editing the lists just works."""
    cities = read_list("citta.txt")
    categories = {campaign: read_list(f"{campaign}.txt") for campaign in ("promemoria", "sito")}
    return [(f"{category} {city}", campaign, category, city)
            for campaign in categories for city in cities for category in categories[campaign]]


def next_search(db):
    """First search not done yet; one already tried today, or failed 3 times, is skipped"""
    skip = {query for (query,) in db.execute(
        "SELECT query FROM searches WHERE done_at IS NOT NULL OR started_at >= ? OR attempts >= 3", (today(),))}
    return next((search for search in queue() if search[0] not in skip), None)


def start_search(db, query):
    db.execute("INSERT INTO searches (query, started_at, attempts) VALUES (?, ?, 1) ON CONFLICT(query) "
               "DO UPDATE SET started_at = excluded.started_at, attempts = attempts + 1", (query, now()))


def finish_search(db, query, found, completed):
    """found adds up across attempts; done only when Maps' whole list was read"""
    db.execute("UPDATE searches SET found = coalesce(found, 0) + ?, done_at = ? WHERE query = ?",
               (found, now() if completed else None, query))


def searches_today(db):
    return db.execute("SELECT COUNT(*) FROM searches WHERE started_at >= ?", (today(),)).fetchone()[0]


def get_meta(db, key):
    row = db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def set_meta(db, key, value):
    db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, value))


def status(db):
    done = db.execute("SELECT COUNT(*) FROM searches WHERE done_at IS NOT NULL").fetchone()[0]
    return (f"Contatti pronti: {len(pick(db))}   ·   Ricerche fatte: {done} di {len(queue())}"
            f"   ·   Bozze di oggi: {drafted_today(db)} di {DAILY_DRAFTS}")


def export(db):
    """output/contatti.xlsx: every business found with its email history, to browse in Excel"""
    pd.read_sql("""
        SELECT l.name AS Nome, l.email AS Email, l.category AS Categoria, l.city AS "Città", l.phone AS Telefono,
               l.website AS Sito, l.campaign AS "Prima campagna", l.site_old AS "Sito datato (0-3)",
               (SELECT group_concat(e.kind || ' ' || substr(e.at, 1, 10), ', ') FROM events e
                WHERE e.email = l.email) AS Storia
        FROM leads l ORDER BY l.added_at""", db).to_excel(OUTPUT_PATH + "contatti.xlsx", index=False)
