# Monitoraggio Argo

[Read this documentation in English](README_EN.md)

Un piccolo monitor basato sulle API di Argo Famiglia, pensato per sostituire le fragili
procedure di scraping del sito.

Il programma salva in un unico database SQLite i compiti, i promemoria, gli avvisi della
Bacheca, i metadati degli allegati e lo stato delle notifiche. Invia un'email giornaliera con
gli impegni scolastici e un'email quando compaiono nuovi avvisi in Bacheca, con un riepilogo
settimanale facoltativo. Gli allegati della Bacheca possono essere caricati su Google Drive;
per impostazione predefinita non vengono conservati in locale dopo il caricamento.

Il programma non richiama mai le funzioni «presa visione» o «adesione» di Argo.

## Installazione

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-browser.txt
.venv/bin/python -m playwright install chromium
cp config.example.yaml config.yaml
cp data/schedule.example.csv data/schedule.csv
cp data/manual_events.example.csv data/manual_events.csv
```

Inserisci i tuoi dati in `config.yaml`. Questo file è privato ed escluso da Git. Non inserire
mai credenziali reali in `config.example.yaml`.

Per importare soltanto le impostazioni utili dal progetto del 2024:

```sh
.venv/bin/python migrate_2024_config.py \
  /percorso/del/progetto/Argo_Monitoring_2024/config/config.json
```

## Utilizzo

Puoi iniziare con una prova offline, senza email né caricamenti, usando un'esportazione già
presente:

```sh
python3 argo_monitor.py --dry-run --saved-export output/20260908-184413
```

Per una normale esecuzione con accesso assistito dal browser:

```sh
python3 argo_monitor.py
```

Il profilo browser dedicato può conservare la sessione Argo. Quando compare il nuovo modulo
SSO, il programma inserisce codice scuola, nome utente e password dal file privato
`config.yaml` e seleziona «Ricordami». Potrebbe essere comunque necessario intervenire se
Argo introducesse un ulteriore passaggio di autenticazione.

Per usare soltanto le API, imposta `argo.mode: api` e indica un file HAR recente oppure un file
privato contenente il token. Il token rilevato dura normalmente circa un'ora e, da solo, non è
adatto a un'esecuzione giornaliera non presidiata.

L'opzione `--dry-run` aggiorna SQLite e le anteprime HTML, ma non invia email e non carica file.
Le anteprime vengono salvate in `data/previews/` e sono escluse da Git.

## Cosa è stato volutamente escluso

Il progetto non comprende lo scraping con Selenium/Helium, i CSV intermedi generati da
pandas, le acquisizioni di debug, gli script duplicati, le dipendenze per IA/OCR, lo storico
dei PDF o il vecchio ambiente virtuale. Le email usano il testo e i metadati forniti dalle API
di Argo, rendendo l'esecuzione deterministica ed economica.

## Sicurezza del repository pubblico

Le regole di esclusione proteggono `config.yaml`, l'orario e gli eventi reali, i file HAR e
OAuth, il database SQLite, i documenti scaricati, la sessione del browser, i log, le anteprime
e gli ambienti virtuali. Nel repository pubblico compaiono soltanto configurazioni e CSV di
esempio.

## Licenza

Distribuito con licenza MIT. Questo progetto è indipendente e non è affiliato ad Argo Software.
