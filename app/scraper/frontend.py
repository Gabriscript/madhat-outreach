"""
This module contain the code for frontend
"""

import threading
import time
import tkinter as tk
from tkinter import filedialog, ttk

from scraper import leads
from scraper.common import Common
from scraper.communicator import Communicator
from scraper.drafts import create_drafts
from scraper.routine import run_routine
from scraper.scraper import Backend
from settings import DAILY_DRAFTS, OUTPUT_PATH, SEARCHES_PER_DAY

# Teal palette from the design system, primary darkened to #0F766E so white text keeps 5.4:1 contrast
BG = "#F0FDFA"
CARD = "#FFFFFF"
BORDER = "#C7E3DF"
TEXT = "#134E4A"
MUTED = "#3F5E5A"
PRIMARY = "#0F766E"
PRIMARY_HOVER = "#115E59"
ERROR = "#B91C1C"
FONT = "Segoe UI"


class Frontend:
    def __init__(self):
        self.root = tk.Tk()
        self.root.iconphoto(True, tk.PhotoImage(file="app/images/GMS.png"))
        self.root.title("MadHat Outreach")
        self.root.configure(bg=BG)
        self.root.geometry("720x960")
        self.root.minsize(640, 860)
        self.init_styles()
        self.routine_running = False

        page = ttk.Frame(self.root, padding=24)
        page.pack(fill="both", expand=True)

        ttk.Label(page, text="MadHat Outreach", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            page, style="Muted.TLabel",
            text="Trova attività su Google Maps, estrai le loro email e prepara le bozze Gmail.",
        ).pack(anchor="w", pady=(2, 16))

        """Activity bar: shown only while something runs"""
        self.activity = ttk.Frame(page)
        self.stop_button = ttk.Button(
            self.activity, text="Ferma", style="Secondary.TButton", cursor="hand2", command=self.stopscraping)
        self.stop_button.pack(side="left")
        self.progress_label = ttk.Label(self.activity)
        self.progress_label.pack(side="right", padx=(8, 0))
        self.progress = ttk.Progressbar(self.activity, mode="indeterminate", style="Teal.Horizontal.TProgressbar")
        self.progress.pack(side="left", fill="x", expand=True, padx=(16, 0))

        """Step 1: daily routine, the everyday button"""
        routine = self.card(page, "1   Routine di oggi")
        self.routine_card = routine.master
        ttk.Label(
            routine, style="CardMuted.TLabel", wraplength=600, justify="left",
            text=f"Prepara fino a {DAILY_DRAFTS} bozze con i contatti dell'archivio, poi, se ne restano pochi, "
                 f"cerca nuove attività dalla coda: massimo {SEARCHES_PER_DAY} ricerche al giorno, con Chrome nascosto.",
        ).pack(anchor="w")
        self.status = ttk.Label(routine, style="Card.TLabel")
        self.status.pack(anchor="w", pady=(8, 0))
        self.routine_button = ttk.Button(
            routine, text="Prepara le bozze di oggi", style="Primary.TButton", cursor="hand2",
            command=self.startroutine)
        self.routine_button.pack(anchor="w", pady=(12, 0))

        """Step 2: one search by hand"""
        search = self.card(page, "2   Ricerca singola su Google Maps")
        self.search_box = ttk.Entry(search, font=(FONT, 12))
        self.search_box.pack(fill="x", pady=(0, 2), ipady=4)
        self.search_box.bind("<Return>", lambda _: self.getinput())
        self.search_error = ttk.Label(search, style="CardMuted.TLabel", text='Categoria e città, es. "dentisti roma"')
        self.search_error.pack(anchor="w")

        options = ttk.Frame(search, style="Card.TFrame")
        options.pack(fill="x", pady=(12, 0))
        self.submit_button = ttk.Button(
            options, text="Avvia ricerca", style="Secondary.TButton", cursor="hand2", command=self.getinput)
        self.submit_button.pack(side="left", padx=(0, 24))
        ttk.Label(options, text="Formato file", style="Card.TLabel").pack(side="left")
        self.outputFormatButton = ttk.Combobox(options, values=["Excel", "CSV", "JSON"], state="readonly", width=8)
        self.outputFormatButton.current(0)
        self.outputFormatButton.pack(side="left", padx=(8, 24))
        self.healdessCheckBoxVar = tk.IntVar()
        ttk.Checkbutton(
            options, text="Browser nascosto", variable=self.healdessCheckBoxVar, style="Card.TCheckbutton",
        ).pack(side="left")

        """Step 3: Gmail drafts from a results file"""
        drafts = self.card(page, "3   Bozze da un file")
        buttons = ttk.Frame(drafts, style="Card.TFrame")
        buttons.pack(fill="x")
        self.draft_buttons = []
        for text, kind in (("Bozze Promemoria", "promemoria"), ("Bozze Sito web", "sito")):
            button = ttk.Button(
                buttons, text=text, style="Secondary.TButton", cursor="hand2",
                command=lambda kind=kind: self.startdrafts(kind),
            )
            button.pack(side="left", padx=(0, 8))
            self.draft_buttons.append(button)
        ttk.Label(
            buttons, style="CardMuted.TLabel", text="Salta chi è già stato contattato",
        ).pack(side="left", padx=(8, 0))

        """Activity log"""
        ttk.Label(page, text="Attività", style="Heading.TLabel").pack(anchor="w", pady=(0, 4))
        log = tk.Frame(page, bg=CARD, highlightthickness=1, highlightbackground=BORDER, highlightcolor=BORDER)
        log.pack(fill="both", expand=True)
        self.show_text = tk.Text(
            log, font=(FONT, 10), height=6, wrap="word", state="disabled", relief="flat",
            bg=CARD, fg=TEXT, padx=12, pady=8,
        )
        scrollbar = ttk.Scrollbar(log, command=self.show_text.yview)
        self.show_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.show_text.pack(side="left", fill="both", expand=True)

        self.refreshstatus()
        self.__replacingtext("Pronto. Premi «Prepara le bozze di oggi», oppure fai una ricerca singola.")
        self.routine_button.focus_set()
        self.init_communicator()

    def init_styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")  # the only built-in theme that honours custom colours on Windows
        style.configure(".", font=(FONT, 10), background=BG, foreground=TEXT)
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD)
        style.configure("Title.TLabel", font=(FONT, 20, "bold"))
        style.configure("Heading.TLabel", font=(FONT, 11, "bold"))
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("Card.TLabel", background=CARD)
        style.configure("CardHeading.TLabel", background=CARD, font=(FONT, 12, "bold"))
        style.configure("CardMuted.TLabel", background=CARD, foreground=MUTED, font=(FONT, 9))
        style.configure("CardError.TLabel", background=CARD, foreground=ERROR, font=(FONT, 9))
        style.configure("Card.TCheckbutton", background=CARD)
        style.map("Card.TCheckbutton", background=[("active", CARD)])
        style.configure("TEntry", fieldbackground=CARD, bordercolor=BORDER, lightcolor=BORDER, padding=6)
        style.map("TEntry", bordercolor=[("focus", PRIMARY)], lightcolor=[("focus", PRIMARY)])
        style.configure(
            "TCombobox", fieldbackground=CARD, background=CARD, bordercolor=BORDER, lightcolor=BORDER,
            darkcolor=BORDER, arrowcolor=PRIMARY, arrowsize=14, padding=4)
        style.map("TCombobox", fieldbackground=[("readonly", CARD)], background=[("active", BG)],
                  bordercolor=[("focus", PRIMARY)])
        style.configure(
            "Vertical.TScrollbar", background=BG, troughcolor=CARD, bordercolor=CARD, lightcolor=BG,
            darkcolor=BG, arrowcolor=MUTED, gripcount=0)
        style.map("Vertical.TScrollbar", background=[("active", BORDER)])

        button = {"font": (FONT, 10, "bold"), "padding": (16, 8), "borderwidth": 1, "focuscolor": TEXT}
        style.configure("Primary.TButton", background=PRIMARY, foreground="white", bordercolor=PRIMARY, **button)
        style.map(
            "Primary.TButton",
            background=[("disabled", BORDER), ("active", PRIMARY_HOVER)],
            foreground=[("disabled", MUTED)],
        )
        style.configure("Secondary.TButton", background=CARD, foreground=PRIMARY, bordercolor=PRIMARY, **button)
        style.map(
            "Secondary.TButton",
            background=[("disabled", CARD), ("active", BG)],
            foreground=[("disabled", BORDER)],
            bordercolor=[("disabled", BORDER)],
        )
        style.configure("Teal.Horizontal.TProgressbar", background=PRIMARY, troughcolor=CARD, bordercolor=BORDER)

    def card(self, parent, title):
        """White bordered section, returns the inner frame to fill"""
        outer = tk.Frame(parent, bg=CARD, highlightthickness=1, highlightbackground=BORDER, highlightcolor=BORDER)
        outer.pack(fill="x", pady=(0, 16))
        inner = ttk.Frame(outer, style="Card.TFrame", padding=16)
        inner.pack(fill="x")
        ttk.Label(inner, text=title, style="CardHeading.TLabel").pack(anchor="w", pady=(0, 10))
        return inner

    def init_communicator(self):
        Communicator.set_frontend_object(self)

    def __replacingtext(self, text):
        """Append a timestamped line to the activity log"""

        self.show_text.config(state="normal")
        self.show_text.insert(tk.END, f"{time.strftime('%H:%M')}   {text}\n")
        self.show_text.see(tk.END)
        self.show_text.config(state="disabled")

    def refreshstatus(self):
        db = leads.connect()
        try:
            self.status.config(text=leads.status(db))
        except Exception as e:  # e.g. a list deleted from liste/
            self.status.config(text=f"Archivio non leggibile: {e}")
        finally:
            db.close()

    def busy(self, on):
        """One job at a time: every action greyed out while something runs, the activity bar shows it"""
        for button in (self.routine_button, self.submit_button, *self.draft_buttons):
            button.config(state="disabled" if on else "normal")
        if on:
            Common.closeThread.clear()  # a previous Ferma must not end this job right away
            Common.blocked.clear()
            self.stop_button.config(state="normal")
            self.progress.config(mode="indeterminate", value=0)
            self.activity.pack(fill="x", pady=(0, 16), before=self.routine_card)
            self.progress.start(12)
        else:
            self.progress.stop()
            self.activity.pack_forget()
            self.progress_label.config(text="")
            self.refreshstatus()

    def startroutine(self):
        self.outputFormatValue = self.outputFormatButton.get().lower()  # format of each search's own file
        self.routine_running = True
        self.busy(True)

        def run():
            try:
                run_routine()
            finally:
                self.routine_running = False
                self.busy(False)

        # not a daemon: on window close it must live long enough to quit Chrome
        self.threadToStartBackend = threading.Thread(target=run)
        self.threadToStartBackend.start()

    def getinput(self):
        if str(self.submit_button["state"]) == "disabled":
            return  # Enter pressed while a job is already running
        self.searchQuery = self.search_box.get().strip()
        if not self.searchQuery:
            self.search_error.config(text="Scrivi cosa cercare, es. \"dentisti roma\"", style="CardError.TLabel")
            self.search_box.focus_set()
            return
        self.search_error.config(text='Categoria e città, es. "dentisti roma"', style="CardMuted.TLabel")

        self.searchQuery = self.searchQuery.lower()
        self.outputFormatValue = self.outputFormatButton.get().lower()
        self.headlessMode = self.healdessCheckBoxVar.get()
        self.busy(True)

        # not a daemon: on window close it must live long enough to quit Chrome
        self.threadToStartBackend = threading.Thread(target=self.startscraping)
        self.threadToStartBackend.start()

    def stopscraping(self):
        Common.set_close_thread()
        self.stop_button.config(state="disabled")
        self.__replacingtext("Interrompo, salvo quello che ho già raccolto...")

    def closingbrowser(self):
        """It will close the browser when the app is closed"""

        Common.set_close_thread()
        self.root.destroy()

    def startscraping(self):
        try:
            backend = Backend(self.searchQuery, self.outputFormatValue, healdessmode=self.headlessMode)
        except Exception as e:  # Chrome missing, driver download failed... mainscraping never runs
            self.__replacingtext(f"Impossibile avviare Chrome: {e}")
            self.end_processing()
            return
        backend.mainscraping()

    def startdrafts(self, kind):
        """Pick a scraped file, then build its Gmail drafts off the Tk thread"""
        path = filedialog.askopenfilename(
            initialdir=OUTPUT_PATH, filetypes=[("Risultati della ricerca", "*.xlsx *.csv *.json")])
        if not path:
            return
        self.busy(True)

        def run():
            try:
                create_drafts(kind, path)
            finally:
                self.busy(False)

        threading.Thread(target=run, daemon=True).start()

    def progressshowing(self, done, total):
        """Scrolling phase: bar bounces. Reading phase: bar fills, one step per business"""
        if done == 1:  # a new search starts reading
            self.progress.stop()
            self.progress.config(mode="determinate", maximum=total)
        self.progress["value"] = done
        self.progress_label.config(text=f"Scheda {done} di {total}")

    def end_processing(self):
        """Called by the backend after every search; during the routine more searches may follow"""
        self.progress.config(mode="indeterminate", value=0)
        self.progress.start(12)
        self.progress_label.config(text="")
        if not self.routine_running:
            self.busy(False)
            self.__replacingtext("Puoi avviare una nuova ricerca")

    def messageshowing(self, message):
        self.__replacingtext(message)


if __name__ == "__main__":
    app = Frontend()
    app.root.protocol("WM_DELETE_WINDOW", app.closingbrowser)
    app.root.mainloop()
