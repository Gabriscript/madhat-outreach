# MadHat Outreach

An end-to-end outbound pipeline for a one-person web studio: it finds local businesses on Google Maps,
pulls their email from their own website, and prepares personalised Gmail drafts, without ever
contacting the same business twice.

It replaced about 5 hours a week of manual prospecting and a pay-per-contact tool (Outscraper),
and runs at zero cost on a Windows PC plus a small Google Apps Script.

Built in a day with an AI coding agent (Claude Code): I designed the system and made the decisions,
the agent wrote most of the code, and every step was tested against real data.
Started from [Zubdata/Google-Maps-Scraper](https://github.com/Zubdata/Google-Maps-Scraper) (GPL v3, see `LICENSE`),
of which about a third survived.

## How it works

```
liste/ (cities x categories)          output/outreach.db (SQLite)
          |                                    ^   |
          v                                    |   v
  search queue --> Google Maps --> websites --> leads --> Gmail drafts --> Apps Script sends
  (max 4/day,      (Selenium,     (email,       (dedup,    (120/day,        (daily, also with
   captcha stop)    any UI         booking,      rules)     reply check)     the PC off)
                    language)      site age)
```

- **Search queue.** 118 Italian provincial capitals x 52 business categories, about 6,100 searches,
  worked through city by city. A search counts as done only when Maps' whole result list was read,
  so a page change leads to retries instead of silent gaps. At most 4 searches a day, random pauses,
  and a full stop until the next day if Google shows a captcha.
- **Just-in-time scraping.** Sending capacity is the bottleneck, not collection: the routine searches
  only while fewer than 10 days of leads are ready.
- **Email extraction.** Homepage, then up to 3 contact pages; handles `mailto:`, HTML entities and
  Cloudflare-obfuscated addresses; drops asset names, placeholders, error-tracker DSNs and PEC
  (certified) mailboxes; checks the domain has an MX record.
- **Lead scoring from the same page.** Businesses already on a booking platform (MioDottore, Treatwell,
  Fresha...) skip the reminder offer; websites without HTTPS, a mobile viewport or a recent copyright
  year get the redesign offer first.
- **One rule for who gets what.** Never the same offer twice, never anyone already emailed for another
  reason, a 120-day gap between the two offers, nothing ever again after a reply. One business per
  email domain (shared providers like gmail.com are matched by address). The rule lives in one SQL query
  used by every path.
- **Replies and bounces without reading mail.** Each draft's Gmail thread ID is stored; any inbox
  message in one of those threads marks the business as replied. Only the `gmail.metadata` scope is
  used, never message bodies.
- **First run imports history.** Every recipient already in Drafts and Sent is recorded, so past
  outreach and personal contacts are never pitched.
- **Gmail API limits.** Rate-limited calls are retried with exponential backoff.

## Daily operation

| Time | Where | What |
|---|---|---|
| 09:00 | Google Apps Script | sends the queued drafts (works with the PC off) |
| 11:00 | Windows Task Scheduler | searches if needed, prepares up to 120 new drafts, exports `output/contatti.xlsx` |

Everything unattended is logged to `output/automatico.log`. The desktop app (Tkinter) runs the same
routine on demand and also offers single searches and drafts from a results file.

## Setup (Windows)

Needs Python 3.11 and Google Chrome. From the project folder:

```
python -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\python app\run.py
```

Gmail: put an OAuth "Desktop app" client from Google Cloud Console (Gmail API enabled) in
`client_secret.json`. The first run opens the browser to log in; the token is saved in `token.json`.
Both files, and everything in `output/`, are gitignored.

Scheduled runs: `venv\Scripts\pythonw.exe app\automatico.py prepara`, started from the project folder.

## Configuration

- Cities and categories: one per line in `liste/`
- Daily limits, pauses, the 120-day gap: `app/settings.py`
- Email subjects and texts (Italian): `TEMPLATES` in `app/scraper/drafts.py`

## Tests

```
venv\Scripts\python app\test_app.py    # unit tests, Gmail faked
venv\Scripts\python app\e2e_check.py   # real Google Maps search, about 2 minutes
```

The unit tests cover email extraction, the search queue, the pitch rules (120-day gap, replies,
shared domains), the Gmail history import and reply detection, with a fake Gmail service.
