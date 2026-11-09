# Changelog

## Non rilasciato

### Correzioni

- System tray: se `pystray` o il backend grafico mancano, all'avvio viene
  mostrato un avviso esplicito (con il comando di installazione) invece di
  disabilitare l'icona in silenzio.
- System tray: avvio più robusto, con log del backend usato e protezione degli
  aggiornamenti grafici da errori che non devono fermare il player.
- RadioBrowser: se la verifica del certificato TLS fallisce (CA locale mancante
  o certificato non valido) la ricerca riprova automaticamente senza verifica,
  invece di restare bloccata da un errore di rete.

### UX

- Menu del tray: stazione e titolo della traccia audio su righe separate.
- Menu del tray: volume con preset (0/25/50/75/100%), incrementi ±5% e muto
  con spunta; volume visibile anche nel tooltip.
- `python-xlib` aggiunto alle dipendenze Linux per il backend Xorg di pystray.

### Prestazioni

- UI Rich: refresh di orologio, uptime ed equalizer ogni 5 secondi (invece di
  ogni secondo); i messaggi temporanei non forzano più ridisegni a 10 fps.
  Consumo CPU ulteriormente ridotto.

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
