"""
These are settings of the scraper. To see thier details, please visit:
https://zubdata.com/docs/google-maps-scraper/getting-started/settings/
"""


OUTPUT_PATH = "output/"

DRIVER_EXECUTABLE_PATH = None

# Gmail drafts, relative to the folder you launch the app from (the repo root). Both are secrets: gitignored
GMAIL_CLIENT_SECRET = "client_secret.json"  # OAuth client downloaded from Google Cloud Console
GMAIL_TOKEN = "token.json"  # written after the first login, delete it to log in again
# Every draft created, so the same business never gets the same draft twice. Delete a row to draft
# that email again. If the file is missing it's rebuilt from the drafts and sent mail in Gmail
DRAFTS_LOG = OUTPUT_PATH + "bozze_create.csv"