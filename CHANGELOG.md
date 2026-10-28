# Changelog

## 3.1.0

### Correzioni

- Compatibilità Windows: import condizionati di `termios`/`tty`, input tramite `msvcrt`.
- Pausa reale tramite MPV (`pause`), non più solo mute.
- Navigazione, ricerca locale, paginazione e selezione ora rispettano i filtri attivi.
- I messaggi temporanei non restano più a schermo dopo la scadenza.
- Rimosso il markup Rich letterale dalla barra del volume.
- Salvataggio M3U con round-trip completo degli attributi (`tvg-id`, `tvg-logo`, `group-title`, durata, ecc.).
- Parsing M3U robusto con virgole in attributi e titoli.
- Eliminazione con doppia conferma e possibilità di annullare (`u`).
- Scrittura atomica della configurazione e debounce sul volume.
- Exit code corretti e messaggi di errore visibili anche dopo la chiusura della UI.
- `notify-send` non blocca più il thread dei metadata.
- `preexec_fn` sostituito da `start_new_session`.

### Prestazioni

- IPC MPV persistente su Unix.
- Metadata letti da MPV; monitor ICY solo come fallback.
- Rendering event-driven (~2,5 fps per l'equalizer) invece di 8 fps fissi.
- Cache della lista filtrata e mappa indice globale/posizione visibile.
- Thread dedicati per i loop, con generation-id.
- Tray aggiornato al massimo ogni 200 ms.
- RadioBrowser: HTTPS, timeout ridotto, cache delle query.

### UX

- Layout adattivo (full/compact/mini) in base al terminale.
- Selettore gruppi (`g`), vista solo preferiti (`f`).
- Tasti `x` stop, `n`/`N` stazione precedente/successiva, PageUp/PageDown, Home/End.
- Picker gruppi, ricerca RadioBrowser con “altri 20” (`Tab`), stato di errore di rete.
- Ripresa dell'ultima stazione selezionata; con `--last` anche dell'ultima playlist.
- Cronologia persistente.
- `--help`, `--version`, `--list`, `--choose`, `--no-tray`, `--no-color`, `--volume`, `--ao`, `--debug`.
- README aggiornato.

### Registrazione

- ffmpeg resta il metodo principale.
- Se ffmpeg manca o fallisce subito, fallback automatico a `stream-record` di MPV.

## 3.0.0

- Versione iniziale documentata.
