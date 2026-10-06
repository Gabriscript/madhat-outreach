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

## Routine di oggi

Il pulsante **Prepara le bozze di oggi** fa tutto da solo:

1. crea fino a 40 bozze prendendo i contatti dall'archivio;
2. se restano meno di 10 giorni di contatti, fa nuove ricerche dalla coda: al massimo 4 al giorno,
   con pause casuali, e si ferma fino al giorno dopo se Google mostra un captcha;
3. aggiorna `output/contatti.xlsx` con tutte le attività trovate e la loro storia.

Regole delle campagne:

- le categorie in `liste/promemoria.txt` ricevono prima il Promemoria, quelle in `liste/sito.txt` il Sito web;
  chi ha già una prenotazione online (MioDottore, Treatwell, Fresha...) riceve subito il Sito web;
- la seconda proposta arriva solo dopo 120 giorni e mai a chi ha risposto;
- una sola attività per dominio; mai a chi ha già ricevuto da te altre email; niente indirizzi PEC;
- il Sito web va prima ai siti più datati (senza https, senza versione mobile, copyright vecchio).

Le città e le categorie si cambiano nei file di `liste/` (una per riga). Limiti e tempi sono in `app/settings.py`.

## Gmail

- `client_secret.json` va nella cartella del progetto: è il client OAuth "App desktop" creato in
  Google Cloud Console, con la Gmail API attiva.
- Al primo utilizzo si apre il browser per il login: concedi entrambi i permessi (creare bozze e
  leggere destinatari e oggetti delle email). Il login resta salvato in `token.json`.
- `client_secret.json` e `token.json` sono privati: git li ignora, non condividerli.
- `output/outreach.db` è l'archivio: ricerche fatte, attività trovate e ogni email preparata o inviata.
  Al primo utilizzo viene riempito con le bozze e la posta inviata già presenti in Gmail: chi ha già
  ricevuto qualsiasi email da te non riceve proposte automatiche. Le risposte vengono riconosciute da sole.

## Dove cambiare le cose

- Testi e oggetti delle email: `TEMPLATES` in `app/scraper/drafts.py`
- Percorsi e impostazioni: `app/settings.py`
- I risultati delle ricerche vengono salvati in `output/`

## Test

```
venv\Scripts\python app\test_app.py
```

Se i risultati sembrano strani (Google cambia la pagina di Maps ogni tanto), questo fa una ricerca vera di prova:

```
venv\Scripts\python app\e2e_check.py
```
