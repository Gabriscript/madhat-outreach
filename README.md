# MadHat Outreach

Trova attività su Google Maps, estrae le email dai loro siti web e prepara le bozze Gmail per l'outreach.
Nulla viene inviato in automatico: le bozze le controlli e le invii tu da Gmail.

Basato su [Zubdata/Google-Maps-Scraper](https://github.com/Zubdata/Google-Maps-Scraper), licenza GPL v3 (vedi `LICENSE`).

## Installazione (Windows, una volta sola)

Serve Google Chrome installato. Dalla cartella del progetto:

```
python -m venv venv
venv\Scripts\pip install -r requirements.txt
```

## Avvio

Dalla cartella del progetto:

```
venv\Scripts\python app\run.py
```

Se Chrome non parte perché il driver non si scarica, scaricalo dalla
[pagina ufficiale](https://googlechromelabs.github.io/chrome-for-testing/#stable) e indica il percorso
in `DRIVER_EXECUTABLE_PATH` dentro `app/settings.py`.

## Gmail

- `client_secret.json` va nella cartella del progetto: è il client OAuth "App desktop" creato in
  Google Cloud Console, con la Gmail API attiva.
- Al primo utilizzo si apre il browser per il login: concedi entrambi i permessi (creare bozze e
  leggere destinatari e oggetti delle email). Il login resta salvato in `token.json`.
- `client_secret.json` e `token.json` sono privati: git li ignora, non condividerli.
- `output/bozze_create.csv` registra ogni bozza creata, così la stessa attività non riceve mai due volte
  la stessa proposta. Al primo utilizzo viene riempito con le bozze e la posta inviata già presenti in Gmail.

## Dove cambiare le cose

- Testi e oggetti delle email: `TEMPLATES` in `app/scraper/drafts.py`
- Percorsi e impostazioni: `app/settings.py`
- I risultati delle ricerche vengono salvati in `output/`

## Test

```
venv\Scripts\python app\test_app.py
```
