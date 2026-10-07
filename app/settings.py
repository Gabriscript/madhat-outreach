"""
These are settings of the scraper. To see thier details, please visit:
https://zubdata.com/docs/google-maps-scraper/getting-started/settings/
"""


OUTPUT_PATH = "output/"

DRIVER_EXECUTABLE_PATH = None

# Gmail drafts, relative to the folder you launch the app from (the repo root). Both are secrets: gitignored
GMAIL_CLIENT_SECRET = "client_secret.json"  # OAuth client downloaded from Google Cloud Console
GMAIL_TOKEN = "token.json"  # written after the first login, delete it to log in again

# Archive of searches, businesses and every email drafted or sent (personal data: output/ is gitignored).
# If it's deleted, the first run rebuilds the email history from the drafts and sent mail in Gmail
DB_PATH = OUTPUT_PATH + "outreach.db"
LISTS_PATH = "liste/"  # cities and categories the routine searches, one per line, edit them freely

# Daily routine
DAILY_DRAFTS = 120  # drafts prepared per day; they may pile up, the Apps Script trigger sends them
SEARCHES_PER_DAY = 4  # Google Maps searches per day at most: few and spaced out, like a person
STOCK_DAYS = 10  # search only when fewer days of leads than this are ready; raise it to collect ahead
SECOND_PITCH_DAYS = 120  # the other campaign only this long after the first email, never after a reply
CARD_PAUSE = (2, 6)  # random seconds between two business cards
SEARCH_PAUSE = (60, 180)  # random seconds between two searches
SEND_PAUSE = (60, 120)  # random seconds between two emails sent by the scheduled run