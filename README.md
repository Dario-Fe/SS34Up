<p align="center">
  <img src="icon.svg" width="76" height="76" alt="Icona di SS34Up" />
</p>

<h1 align="center">SS34Up</h1>

<p align="center">
  <strong>La Statale 34, senza sorprese.</strong><br />
  Chiusure notturne della SS34 a Cannobio, servizi sostitutivi via lago, avvisi e orari ufficiali in una pagina sola.
</p>

<p align="center">
  <a href="LICENSE"><img alt="Licenza MIT" src="https://img.shields.io/badge/licenza-MIT-3f7af5?style=flat-square" /></a>
  <a href="scraper/requirements.txt"><img alt="Python 3.11 o successivo" src="https://img.shields.io/badge/python-3.11%2B-3776AB?style=flat-square" /></a>
  <a href=".github/workflows/aggiorna.yml"><img alt="Aggiornamento automatico alle 10:00 e alle 18:00" src="https://img.shields.io/badge/aggiornamento-10%3A00%20%C2%B7%2018%3A00-07111f?style=flat-square" /></a>
  <a href="https://github.com/Dario-Fe/SS34Up"><img alt="Codice su GitHub" src="https://img.shields.io/badge/codice-GitHub-181717?style=flat-square" /></a>
</p>

<p align="center">
  <a href="https://github.com/Dario-Fe/SS34Up">Repository</a> ·
  <a href="LICENSE">Licenza MIT</a> ·
  <a href="mailto:info@verbanianotizie.it">info@verbanianotizie.it</a>
</p>

SS34Up è un aggregatore statico e indipendente per consultare le **chiusure notturne della SS34 a Cannobio**, i **servizi sostitutivi via lago**, gli avvisi e gli orari ufficiali del Lago Maggiore. Fa parte della suite di servizi e app gratuite di Verbania Notizie, insieme a [BenzUp](https://benzup.netlify.app/), [JobUp](https://job-up.netlify.app/) e [AlboUp](https://alboup.netlify.app/).

La pagina non interroga le fonti dal browser: uno scraper Python produce `data.json`, che viene pubblicato insieme al sito. Ogni informazione mantiene il link alla propria fonte, e il codice è pubblico su GitHub con licenza MIT.

## Indice

- [Cosa mostra](#cosa-mostra)
- [Stack](#stack)
- [Struttura](#struttura)
- [Sviluppo locale](#sviluppo-locale)
- [Aggiornamento automatico](#aggiornamento-automatico)
- [Deploy su Netlify](#deploy-su-netlify)
- [Contratto dati](#contratto-dati)
- [Fonti e licenze](#fonti-e-licenze)
- [Licenza](#licenza)
- [Privacy](#privacy)
- [Avvertenza](#avvertenza)

## Cosa mostra

- Stato della notte corrente e delle prossime tre notti.
- Calendario operativo del Comune di Verbania, con stato di ogni giorno.
- Battelli Cannero Riviera–Cannobio e traghetti Intra–Laveno.
- Avvisi pertinenti, con ricerca, filtri e scheda di dettaglio.
- PDF degli orari di Navigazione Laghi.
- Fonti, licenze e limiti nella pagina `infoutili.html`.
- Contatti con l’email della redazione e riferimenti alla suite Verbania Notizie.
- Guida per installare SS34Up come app su Android, iPhone/iPad e desktop.

### Regole principali

- La chiusura notturna è **21:00–05:00**.
- È esclusa la notte tra sabato e domenica.
- La notte indicata è quella tra il giorno e il successivo; dopo mezzanotte fa fede il giorno precedente.
- Quando la SS34 resta aperta, alcune corse via lago possono essere sospese: l’avviso di Navigazione Laghi viene mostrato sopra i servizi.
- Il calendario operativo del Comune prevale per la notte corrente.
- L’ordinanza ANAS indica l’avvio dal **12 ottobre 2026**, il calendario operativo dal **21 ottobre 2026**: la discrepanza viene mostrata, non nascosta.
- In caso di maltempo o modifiche dell’ultimo minuto fanno fede le fonti ufficiali.

## Stack

| Livello | Scelta |
| --- | --- |
| Frontend | HTML, CSS e JavaScript senza framework e senza dipendenze runtime |
| Dati | `data.json`, unico contratto tra scraper e frontend |
| Scraper | Python 3 con `requests` e `beautifulsoup4` |
| Offline | Service worker per cache e consultazione offline di base |
| Automazione | GitHub Actions, due aggiornamenti al giorno |
| Hosting | Netlify, sito statico |

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
├── LICENSE
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
│   ├── test_build_data.py
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

## Aggiornamento automatico

Lo scraper:

1. legge le pagine pubbliche del Comune di Verbania, il preview pubblico del canale Telegram ufficiale “Verbania M’Informa” e l’API avvisi di Navigazione Laghi;
2. filtra i contenuti non pertinenti e limita gli avvisi agli ultimi 120 giorni;
3. usa Telegram come fonte supplementare, scartando i post già presenti sul sito o già pubblicati dal canale;
4. estrae calendario, servizi, validità, orari e PDF;
5. valida che tutti gli URL appartengano ai domini ufficiali o al canale Telegram del Comune;
6. confronta l’hash del contenuto con `data.json` e aggiorna sempre `generated_at` con l’ora del controllo appena eseguito, anche quando i contenuti non cambiano;
7. scrive il file in modo deterministico.

Se il sito del Comune non risponde, lo scraper conserva l’ultimo calendario e gli avvisi Comune già salvati, poi aggiorna comunque Telegram e Navigazione Laghi. Un post Telegram viene accettato solo se è pertinente alla SS34 e non ripete per URL o contenuto un avviso già presente; la deduplica testuale considera gli avvisi dello stesso periodo.

Il workflow `.github/workflows/aggiorna.yml` gestisce le esecuzioni:

| Fase | Comportamento |
| --- | --- |
| Cron GitHub | 08:15, 09:15, 16:15 e 17:15 UTC, lontano dal minuto `0` che è il più congestionato dello scheduler |
| Guardia sull’età dei dati | prosegue se `meta.generated_at` ha almeno 6 ore: un ritardo di GitHub non spreca più la run e una run persa viene recuperata dalla successiva |
| Contenuti nuovi | `data.json` cambia, nasce un commit e Netlify ridistribuisce il sito |
| Nessuna novità | `generated_at` avanza comunque: il commit contiene solo l’orario, così l’app mostra sempre l’ultimo controllo |

Il `content_hash` resta invariato quando i contenuti sono identici: serve a distinguere una novità reale da un semplice controllo.

Per forzare un aggiornamento usare **Actions → Aggiorna dati SS34Up → Run workflow**. Il job richiede `contents: write`, già dichiarato nel workflow.

## Deploy su Netlify

1. Il repository pubblico è [Dario-Fe/SS34Up](https://github.com/Dario-Fe/SS34Up).
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
  id, source, source_id, source_url, source_api, telegram_url (solo Telegram),
  category, tags, title, summary, body_text, published_at, updated_at,
  valid_from, valid_until, closure_window, services, is_calendar,
  calendar_updated_label, content_hash, first_seen_at
services[]
  id, kind, from, to, route, times, notes, source_urls
timetables[]
  id, kind, route, title, pdf_url, source_page, valid_from, valid_until
```

Status del calendario: `APERTA`, `CHIUSA`, `CHIUSURA_NOTTURNA`, `NON_DEFINITA`.

## Fonti e licenze

| Fonte | Cosa fornisce | Licenza dichiarata |
| --- | --- | --- |
| [Comune di Verbania — Novità](https://www.comune.verbania.it/Novita) | avvisi e comunicati | CC BY 4.0, salvo contenuti di terzi |
| [Calendario SS34 del Comune](https://www.comune.verbania.it/Novita/Comunicati/S.S.-34-a-Cannobio-il-calendario-delle-aperture-e-delle-chiusure-notturne) | aperture e chiusure notturne | CC BY 4.0 |
| [Canale Telegram “Verbania M’Informa”](https://t.me/s/VerbaniaMinforma) | avvisi supplementari | non dichiarata |
| [Navigazione Laghi](https://www.navigazionelaghi.it/) | avvisi, orari e PDF | non dichiarata |

I contenuti del canale Telegram e di Navigazione Laghi sono consultati dalla fonte ufficiale, che non dichiara una licenza aperta esplicita: SS34Up riporta estratti e fatti con attribuzione e link, senza ridistribuire i PDF. L’uso dei nomi delle fonti non implica approvazione o affiliazione.

## Licenza

Il codice è distribuito con **licenza MIT**: il testo completo è in [`LICENSE`](LICENSE), il repository pubblico è [github.com/Dario-Fe/SS34Up](https://github.com/Dario-Fe/SS34Up). La licenza riguarda solo il codice: dati, avvisi, orari, immagini e contenuti di Comune di Verbania, Anas e Navigazione Laghi restano dei rispettivi titolari.

## Privacy

Nessun cookie di profilazione, nessun font remoto, nessun widget pubblicitario o social. Le uniche richieste esterne sono il beacon di **Cloudflare Web Analytics** — senza cookie e senza identificatori persistenti, solo statistiche aggregate — e i link alle fonti ufficiali. La cache del service worker resta sul dispositivo dell’utente. L’hosting può registrare log tecnici secondo le proprie condizioni.

## Avvertenza

> **SS34Up non è un servizio ufficiale** e non sostituisce Comune di Verbania, Anas, Navigazione Laghi o forze dell’ordine. Non usare il sito per emergenze. Verificare sempre la fonte prima di partire.

Per segnalazioni sui dati: [info@verbanianotizie.it](mailto:info@verbanianotizie.it). Per problemi tecnici: [issue su GitHub](https://github.com/Dario-Fe/SS34Up/issues).
