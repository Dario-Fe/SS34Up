# SS34Up

SS34Up è un aggregatore statico e indipendente per consultare le **chiusure notturne della SS34 a Cannobio**, i **servizi sostitutivi via lago**, gli avvisi e gli orari ufficiali del Lago Maggiore.

La pagina non interroga le fonti dal browser: uno scraper Python produce `data.json`, che viene pubblicato insieme al sito. Ogni informazione mantiene il link alla propria fonte.

## Cosa mostra

- Stato della notte corrente e delle prossime tre notti.
- Calendario operativo del Comune di Verbania, con stato di ogni giorno.
- Battelli Cannero Riviera–Cannobio e traghetti Intra–Laveno.
- Avvisi pertinenti, con ricerca, filtri e scheda di dettaglio.
- PDF degli orari di Navigazione Laghi.
- Fonti, licenze e limiti nella pagina `infoutili.html`.
- Guida per installare SS34Up come app su Android, iPhone/iPad e desktop.

Regole principali:

- La chiusura notturna è **21:00–05:00**.
- È esclusa la notte tra sabato e domenica.
- La notte indicata è quella tra il giorno e il successivo; dopo mezzanotte fa fede il giorno precedente.
- Quando la SS34 resta aperta, alcune corse via lago possono essere sospese: l’avviso di Navigazione Laghi viene mostrato sopra i servizi.
- Il calendario operativo del Comune prevale per la notte corrente.
- L’ordinanza ANAS indica l’avvio dal **12 ottobre 2026**, il calendario operativo dal **21 ottobre 2026**: la discrepanza viene mostrata, non nascosta.
- In caso di maltempo o modifiche dell’ultimo minuto fanno fede le fonti ufficiali.

## Stack

- HTML, CSS e JavaScript senza framework e senza dipendenze runtime.
- Python 3 con `requests` e `beautifulsoup4`.
- `data.json` come unico contratto dati tra scraper e frontend.
- Service worker per cache e consultazione offline di base.
- GitHub Actions per l’aggiornamento automatico.
- Netlify per il deploy statico.

## Struttura

```text
.
├── index.html
├── infoutili.html
├── manifest.json
├── icon.svg
├── icon-180.png
├── icon-192.png
├── icon-512.png
├── icon-maskable-512.png
├── sw.js
├── netlify.toml
├── robots.txt
├── data.json
├── assets/
│   ├── app.js
│   └── style.css
├── scraper/
│   ├── __init__.py
│   ├── parsers.py
│   ├── scraper_ss34up.py
│   └── requirements.txt
├── tests/
│   ├── fixtures/
│   └── test_parsers.py
├── requirements-dev.txt
├── pytest.ini
└── .github/workflows/aggiorna.yml
```

## Sviluppo locale

Requisiti: Python 3.11 o successivo, con `tzdata` su Windows.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Aggiornare i dati:

```powershell
.\.venv\Scripts\python.exe scraper\scraper_ss34up.py
```

Eseguire i test:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Avviare il sito:

```powershell
.\.venv\Scripts\python.exe -m http.server 8000
```

Aprire `http://localhost:8000`. Non usare `file://`: il browser blocca il caricamento di `data.json`.

Su macOS/Linux i comandi equivalenti usano `.venv/bin/python`.

## Aggiornamento

Lo scraper:

1. legge le pagine pubbliche del Comune di Verbania e l’API avvisi di Navigazione Laghi;
2. filtra i contenuti non pertinenti e limita gli avvisi agli ultimi 120 giorni;
3. estrae calendario, servizi, validità, orari e PDF;
4. valida che tutti gli URL appartengano ai domini ufficiali;
5. confronta l’hash del contenuto con `data.json` e conserva `generated_at` se nulla è cambiato;
6. scrive il file in modo deterministico.

Il workflow `.github/workflows/aggiorna.yml` viene eseguito ogni giorno alle **08:00, 09:00, 16:00 e 17:00 UTC**. Un controllo in `Europe/Rome` prosegue solo alle 10:00 o alle 18:00 italiane, gestendo automaticamente ora legale e ora solare. Il workflow:

- esegue lo scraper;
- esegue i test;
- crea un commit solo se `data.json` è cambiato;
- non crea commit quando il contenuto è identico.

Per forzare un aggiornamento usare **Actions → Aggiorna dati SS34Up → Run workflow**. Il job richiede `contents: write`, già dichiarato nel workflow.

## Deploy su Netlify

1. Pubblicare il repository su GitHub.
2. Creare un nuovo sito Netlify collegato al repository.
3. Non impostare un build command.
4. Impostare la directory di pubblicazione su `.` (la root del repository).
5. Netlify legge `netlify.toml` per header, cache e Content Security Policy.

Il sito è interamente statico. Dopo un aggiornamento di `data.json`, Netlify ridistribuisce automaticamente il sito.

## Contratto dati

`data.json` usa chiavi in `snake_case`.

```text
meta
  app, version, generated_at, timezone, update_schedule, schedule_note,
  content_hash, sources
calendar
  source_url, published_at, updated_at, updated_label, counts,
  closure_window, months, days, content_hash
notices[]
  id, source, source_id, source_url, source_api, category, tags, title,
  summary, body_text, published_at, updated_at, valid_from, valid_until,
  closure_window, services, is_calendar, calendar_updated_label,
  content_hash, first_seen_at
services[]
  id, kind, from, to, route, times, notes, source_urls
timetables[]
  id, kind, route, title, pdf_url, source_page, valid_from, valid_until
```

Status del calendario: `APERTA`, `CHIUSA`, `CHIUSURA_NOTTURNA`, `NON_DEFINITA`.

## Fonti e licenze

Fonti principali:

- [Comune di Verbania — Novità](https://www.comune.verbania.it/Novita)
- [Calendario SS34 del Comune di Verbania](https://www.comune.verbania.it/Novita/Comunicati/S.S.-34-a-Cannobio-il-calendario-delle-aperture-e-delle-chiusure-notturne)
- [Navigazione Laghi](https://www.navigazionelaghi.it/)
- [Orari Lago Maggiore](https://www.navigazionelaghi.it/biglietti-e-orari-lago-maggiore/)

I contenuti del Comune di Verbania sono pubblicati con licenza **CC BY 4.0**, salvo diversa indicazione per contenuti di terzi. I contenuti di Navigazione Laghi sono consultati dalla fonte ufficiale, che non dichiara una licenza aperta esplicita: SS34Up riporta estratti e fatti con attribuzione e link, senza ridistribuire i PDF.

Il codice del progetto è distribuito con licenza MIT. I dati e i contenuti restano dei rispettivi titolari. L’uso dei nomi delle fonti non implica approvazione o affiliazione.

## Privacy

Nessun analytics, cookie di profilazione, font remoto o widget di terze parti. La cache del service worker resta sul dispositivo dell’utente. L’hosting può registrare log tecnici secondo le proprie condizioni.

## Avvertenza

SS34Up non è un servizio ufficiale e non sostituisce Comune di Verbania, Anas, Navigazione Laghi o forze dell’ordine. Non usare il sito per emergenze. Verificare sempre la fonte prima di partire.
