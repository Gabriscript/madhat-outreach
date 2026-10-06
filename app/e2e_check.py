"""
End-to-end check on the real Google Maps: opens the app window, searches with Chrome hidden,
presses Ferma after a few businesses and checks the saved file. Needs Chrome and internet, ~2 minutes.
Run it from the repo root when results look wrong, Google changes the Maps page from time to time:
venv\\Scripts\\python app\\e2e_check.py
"""

import glob
import os
import tempfile

import pandas as pd

import scraper.datasaver
from scraper.frontend import Frontend

QUERY, CARDS = "dentisti milano", 5

with tempfile.TemporaryDirectory() as folder:
    scraper.datasaver.OUTPUT_PATH = folder + os.sep  # test results stay out of output/

    app = Frontend()
    app.search_box.insert(0, QUERY)
    app.outputFormatButton.set("CSV")
    app.healdessCheckBoxVar.set(1)
    app.getinput()

    def watch():
        """Waits on the app's own state, never on fixed sleeps: Ferma once CARDS businesses are read"""
        reading_next = app.progress_label.cget("text").startswith(f"Scheda {CARDS + 1} ")
        if reading_next and str(app.stop_button["state"]) == "normal":
            app.stopscraping()
        if app.threadToStartBackend.is_alive():
            app.root.after(500, watch)
        else:
            app.root.destroy()

    app.root.after(500, watch)
    app.root.mainloop()

    files = glob.glob(os.path.join(folder, "*.csv"))
    assert files, "no results file saved"
    results = pd.read_csv(files[0])
    print(results[["Name", "Phone", "Website", "email"]].to_string())

    assert len(results) >= CARDS, f"only {len(results)} businesses saved"
    for column in ("Name", "Address", "Phone", "Website"):
        assert results[column].notna().any(), f"{column} empty for every business: the Maps page probably changed"
    assert results["email"].notna().any(), "no email found on any website"
    print(f"OK: {len(results)} attività salvate, {results['email'].notna().sum()} con email")
