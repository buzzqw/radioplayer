# 🎵 Radio Player M3U

![Python](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-GPL%20v3-green)
![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey)
![Version](https://img.shields.io/badge/Version-3.0-orange)

Lettore di stazioni radio da terminale, **cross-platform** (Linux · macOS · Windows), con interfaccia TUI colorata basata su [Rich](https://github.com/Textualize/rich), metadati in tempo reale, registrazione stream e ricerca integrata su [RadioBrowser.info](https://www.radio-browser.info).

---

## 📸 Anteprima

### Schermata principale (in riproduzione)

```
╭──────────────────────────────────────────────────────────────────────────────╮
│ 🎵 RADIO PLAYER M3U  ⏰ 21:45:03  Uptime: 01:23  🔊 ████████░░ 80%  📝 ✗  🔔 │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Status ─────────────────────────────────────────────────────────────────────╮
│ ▶  IN RIPRODUZIONE  │  📡 Radio Deejay                                       │
│ 🎤 The Weeknd  🎼 Blinding Lights  [01:23]  ▁▁▅▁▁▇▁▃                         │
│ 🔊 128 kbps  •  AAC  •  📦 OK                                                │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ 📻 Stazioni (9 totali) ─────────────────────────────────────────────────────╮
│   ── Italia ──                                                               │
│  👉   ★ 1  Radio Deejay                                                     │
│       2  Radio 105                                                            │
│   ▶️   3  RDS                                                                │
│   ── UK ──                                                                   │
│       4  BBC Radio 1                                                          │
│       5  BBC Radio 2                                                          │
│   ── Jazz ──                                                                 │
│       6  Smooth Jazz                                                          │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ 🎮 Controlli ───────────────────────────────────────────────────────────────╮
│ ↑/↓ Seleziona stazione    +/= Alza volume   p/Spazio Play/Pausa  -/_ Vol-    │
│ m Muto  1-9+↵ Vai a #  r Rec  l Log  t Notifiche  h Cronologia  s Salva     │
│ b RadioBrowser  g Gruppi  * Preferiti  d Rimuovi  / Cerca  e EQ  ? Aiuto     │
│ a-z Salta lettera  q Esci                                                    │
╰──────────────────────────────────────────────────────────────────────────────╯
```

### Ricerca nel M3U locale (`/`)

Digita `/` per filtrare la lista — la parte che combacia viene evidenziata:

```
╭─ 📻 Stazioni  /radio  (2 di 9 totali) ───────────────────────────────────────╮
│   ── Italia ──                                                               │
│  👉    3  IT::Radio Deejay                                                  │
│   ── UK ──                                                                   │
│       4  BBC Radio 1                                                          │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ 🎮 Controlli ───────────────────────────────────────────────────────────────╮
│ /radio_    Cerca stazione locale...                                          │
│ ↑/↓ Seleziona  p/Spazio Play/Pausa  +/= Vol+  -/_ Vol-  m Muto  g Gruppi    │
╰──────────────────────────────────────────────────────────────────────────────╯
```

> Il testo `radio` in `IT::Radio Deejay` e `BBC Radio 1` appare in **giallo bold** per indicare dove combacia.

### Filtrato per gruppo (`g`)

Ciclando con `g`, il pannello mostra solo il gruppo corrente:

```
╭─ 📻 Stazioni Italia (4 di 9 totali) ─────────────────────────────────────────╮
│  ★ 👉▶️ 1  Radio Deejay                                                     │
│       2  Radio 105                                                            │
│       3  RDS                                                                 │
│       4  RTL 102.5                                                            │
╰──────────────────────────────────────────────────────────────────────────────╯
```

### Schermata di aiuto (`?`)

Premi `?` per vedere tutti i comandi in una tabella:

```
╭─ 💡 Aiuto  (premi ? per chiudere) ───────────────────────────────────────────╮
│ Tasto        Azione                    Tasto        Azione                    │
│ ↑/↓          Seleziona stazione        p / Spazio   Play/Pausa               │
│ 1-9 + ↵      Vai a stazione numero     g            Filtro per gruppo        │
│ *            Aggiungi/rimuovi pref     d            Rimuovi stazione          │
│ /            Cerca nel M3U             e            Preset EQ                 │
│ + / = / -/_  Volume ± 5%               m            Muto/Riattiva            │
│ r            Registra stream           t            Notifiche ON/OFF          │
│ l            Logging ON/OFF            b            Sfoglia RadioBrowser      │
│ s            Salva cronologia          h            Cronologia brani          │
│ ?            Questo aiuto              q            Esci                      │
╰──────────────────────────────────────────────────────────────────────────────╯
```

### Cronologia brani (`h`)

```
╭─ 📜 Cronologia brani  (premi H per chiudere) ────────────────────────────────╮
│  #   Artista          Brano                 Stazione          Orario          │
│  1   The Weeknd       Blinding Lights       Radio Deejay      21:45           │
│  2   Dua Lipa         Levitating            Radio Deejay      21:42           │
│  3   Coldplay         A Sky Full of Stars   Radio Deejay      21:38           │
│  4   Lady Gaga        Poker Face            Radio 105         21:34           │
╰──────────────────────────────────────────────────────────────────────────────╯
```

### Ricerca RadioBrowser.info (`b`)

Apri una ricerca globale su 40.000+ stazioni direttamente dal terminale:

```
╭─ 🔍 RadioBrowser.info  ✅ 20 stazioni trovate ───────────────────────────────╮
│ radio italia_                                                                │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Risultati (20) ─────────────────────────────────────────────────────────────╮
│      Nome                            Paese  kbps  Codec    ★ Voti            │
│  👉  Virgin Radio Italia             Italy   128  MP3       16116            │
│     Radio Italia Solo Musica ✓      Italy     0  MP3        9276            │
│     CLASSIC HITS RADIO Italia        Italy   192  AAC        5844            │
│     NEW HITS RADIO Italia            Italy   320  MP3        3849            │
│     Radio Italia Anni 60             Italy    64  MP3        2998            │
╰──────────────────────────────────────────────────────────────────────────────╯
│ ↑/↓ Naviga  ↵ Aggiungi a M3U  p Anteprima/Ferma  ⌫ Cancella  Esc Torna        │
╰──────────────────────────────────────────────────────────────────────────────╯
```

> Le stazioni con `✓` sono **già presenti** nel tuo file M3U e non verranno duplicate.

---

## ✨ Caratteristiche

| | Funzionalità |
|---|---|
| 📻 | Riproduzione di qualsiasi stream supportato da MPV (MP3, AAC, OGG, HLS…) |
| 🎵 | Metadati automatici via ICY: artista, titolo, timer e **equalizer animato** |
| 📊 | Statistiche live: bitrate, codec, stato del buffer (colorato in base al livello) |
| 🔊 | Volume con **barra visuale** (es. `████████░░`) e controllo istantaneo |
| 📁 | **Filtro per gruppo** M3U (`g`) e separatori di gruppo nel pannello stazioni |
| ⭐ | **Preferiti** (`*`): stazioni marcate con ★, salvati nella configurazione |
| 🔍 | Ricerca nel M3U locale (`/`) con evidenziazione del testo che combacia |
| 🔤 | **Jump per lettera** (`a`–`z`): salta alla stazione che inizia con quella lettera |
| 🎚️ | **Preset equalizzatore** (`e`): Flat, Bass Boost, Voice, Classical, Rock |
| 💡 | **Schermata aiuto** (`?`) con tutti i comandi |
| 🌐 | Ricerca su RadioBrowser.info — 40.000+ stazioni per popolarità |
| ➕ | Aggiunta al M3U da RadioBrowser con controllo duplicati automatico |
| 👂 | Anteprima di una stazione prima di salvarla |
| 🔴 | Registrazione dello stream in MP3 tramite ffmpeg |
| 📜 | Cronologia brani (ultimi 100), esportabile in JSON |
| 🔔 | Notifiche desktop native al cambio brano (`notify-send` / Toast) |
| 📝 | Logging su file rotante, attivabile a runtime senza riavvio |
| ⚙️ | **Configurazione persistente** (`~/.config/radioplayer/config.json`) |
| 🖼️ | Icona nel system tray: play/pausa, stop, muto, volume, **stazione prec./succ.** |
| 🛡️ | Pulizia corretta di MPV all'uscita, anche su chiusura forzata (SIGHUP/SIGTERM) |

---

## 🚀 Avvio rapido

```bash
# 1. Clona il repository
git clone https://github.com/buzzqw/radioplayer.git
cd radioplayer

# 2. Installa le dipendenze Python
pip3 install -r requirements.txt

# 3. Installa mpv (vedi sotto per il tuo sistema)

# 4. Avvia con il file M3U di esempio incluso
python3 radioplayer.py stations.m3u
```

`python3 radioplayer.py` lancia direttamente la radio: se non specifichi un file, cerca automaticamente i `.m3u` nella cartella corrente (e in quella dello script) e ti fa scegliere se ce ne sono più di uno.

---

## 📦 Installazione

### Linux — Ubuntu / Debian

```bash
sudo apt update
sudo apt install mpv python3 python3-pip libnotify-bin ffmpeg
pip3 install -r requirements.txt
```

### Linux — Fedora / RHEL

```bash
sudo dnf install mpv python3 python3-pip libnotify ffmpeg
pip3 install -r requirements.txt
```

### macOS

```bash
brew install mpv python ffmpeg
pip3 install -r requirements.txt
```

### Windows

1. Installa **Python 3.8+** da [python.org](https://www.python.org/downloads/) *(spunta "Add to PATH")*
2. Installa **MPV** da [mpv.io](https://mpv.io/installation/) e aggiungi la cartella al PATH
3. *(Opzionale)* Installa **ffmpeg** da [ffmpeg.org](https://ffmpeg.org/download.html) per la registrazione
4. Installa le dipendenze:

```cmd
pip install -r requirements.txt
pip install pywin32 win10toast
```

### Installazione come pacchetto (opzionale)

```bash
pip install .
radioplayer            # comando installato nel PATH
```

---

## ▶️ Utilizzo

```bash
# Avvia con un file M3U specifico
python3 radioplayer.py mie_radio.m3u

# Auto-rileva i file .m3u nella cartella corrente
python3 radioplayer.py
```

All'avvio viene selezionata automaticamente la prima stazione. Premi `p` o `Spazio` per iniziare ad ascoltare.

---

## 📋 Formato file M3U

Il player supporta il formato **M3U esteso** (`#EXTM3U`) con attributi opzionali, inclusi i gruppi (`group-title` / `#EXTGRP`):

```m3u
#EXTM3U

#EXTINF:-1 group-title="Italiana" tvg-logo="https://example.com/logo.png",Radio Deejay
http://deejay.example.com/stream.mp3

#EXTINF:-1 group-title="Classica",Radio Classica
http://classica.example.com/stream

#EXTINF:-1,IT::Radio Rai1
http://icestreaming.rai.it/1.mp3
```

> I gruppi servono anche per il filtro (`g`) e come separatori nel pannello stazioni.

---

## 🎮 Comandi da tastiera

### Riproduzione normale

| Tasto | Azione |
|-------|--------|
| `↑` `↓` | Seleziona stazione |
| `p` · `Spazio` · `Invio` | Play / Pausa |
| `+` `=` · `-` `_` | Volume +5% / −5% |
| `m` | Muto / Riattiva audio |
| `1`–`9` poi `Invio` | Salta alla stazione numero N |
| `a`–`z` | Salta alla prima stazione che inizia con quella lettera |
| `g` | Cicla il filtro per gruppo |
| `*` | Aggiungi / rimuovi preferito |
| `d` | Rimuovi stazione dalla lista e dal file M3U |
| `/` | Ricerca nel M3U locale |
| `e` | Cicla i preset equalizzatore |
| `?` | Schermata aiuto |
| `b` | Apre la ricerca RadioBrowser.info |
| `r` | Avvia / ferma registrazione *(richiede ffmpeg)* |
| `t` | Notifiche cambio brano ON/OFF |
| `l` | Log su file ON/OFF |
| `h` | Cronologia brani |
| `s` | Esporta la cronologia in JSON |
| `q` | Esci |

### Ricerca locale (`/`)

| Tasto | Azione |
|-------|--------|
| *(digita)* | Filtra le stazioni, evidenziando il testo che combacia |
| `↑` `↓` | Naviga tra le stazioni |
| `⌫` | Cancella l'ultimo carattere |
| `Invio` · `Esc` | Esci dalla ricerca |

### Ricerca RadioBrowser (`b`)

| Tasto | Azione |
|-------|--------|
| *(digita)* | Cerca — automatica dopo 0,3 s |
| `↑` `↓` | Naviga tra i risultati |
| `Invio` | Aggiunge la stazione al M3U |
| `p` | Anteprima / ferma (toggle sulla stessa stazione) |
| *(digita)* | Spazio incluso — scrivi query multi-parola |
| `⌫` | Cancella l'ultimo carattere |
| `Esc` | Torna alla lista |

---

## 🔍 Ricerca RadioBrowser.info

Integra l'API pubblica di [RadioBrowser.info](https://www.radio-browser.info), un database aperto con oltre **40.000 stazioni**.

1. Premi `b` per aprire la modalità sfoglia
2. Digita il nome (anche parziale) — ricerca automatica dopo 0,3 s
3. Risultati ordinati per **popolarità** (★ voti)
4. Per ogni stazione: nome, paese, bitrate, codec e voti
5. Le stazioni **già presenti** nel M3U sono segnalate con `✓`
6. `Invio` aggiunge (controllo automatico duplicati per URL e nome)
7. `p` ascolta anteprima — premi di nuovo `p` sulla stessa stazione per fermarla

**Feedback visivo:** bordo 🟡 giallo durante la ricerca (spinner), 🟢 verde con risultati, 🔴 rosso se nessun risultato.

---

## ⚙️ Configurazione persistente

Le preferenze vengono salvate in `~/.config/radioplayer/config.json` (Linux/macOS) o nella cartella di configurazione dell'utente (Windows) e ripristinate al riavvio:

| Chiave | Descrizione |
|--------|-------------|
| `volume` | Ultimo livello volume |
| `show_song_popups` | Notifiche cambio brano attive |
| `logging_enabled` | Log su file attivo |
| `favorites` | Lista stazioni preferite |
| `group_filter` | Ultimo filtro gruppo attivo |
| `eq_preset_idx` | Ultimo preset equalizzatore |
| `last_m3u` | Ultimo file M3U usato |

Il log rotante viene scritto in `~/.config/radioplayer/radioplayer.log` quando attivato con `l`.

---

## 🔧 Dipendenze

### Python (`pip`)

| Pacchetto | Versione | Uso |
|-----------|----------|-----|
| [`rich`](https://github.com/Textualize/rich) | ≥ 13.7 | Interfaccia TUI |
| [`requests`](https://requests.readthedocs.io) | ≥ 2.31 | Metadati ICY e API RadioBrowser |
| [`pystray`](https://github.com/moses-palmer/pystray) | ≥ 0.19.5 | Icona system tray |
| [`Pillow`](https://python-pillow.org) | ≥ 10.0 | Immagine icona tray |

```bash
pip3 install -r requirements.txt
```

### Sistema

| Strumento | Necessario | Uso |
|-----------|-----------|-----|
| `mpv` | ✅ Obbligatorio | Engine di riproduzione audio |
| `ffmpeg` | ⬜ Opzionale | Registrazione stream (`r`) |
| `libnotify` | ⬜ Opzionale | Notifiche desktop su Linux |
| `pywin32` + `win10toast` | ⬜ Opzionale | Notifiche Toast su Windows |

---

## 🛠️ Risoluzione problemi

### MPV non trovato all'avvio

```bash
mpv --version        # verifica che mpv sia installato e nel PATH
which mpv            # percorso binario (Linux/macOS)
```

### La musica continua dopo aver chiuso l'app

Se chiudi l'app con `q` il processo MPV viene terminato automaticamente. In caso di chiusura forzata del terminale l'app intercetta `SIGHUP`/`SIGTERM` e pulisce MPV; se proprio resta orfano:

```bash
pkill -x mpv
```

### Nessun metadato (artista/titolo) visualizzato

Alcuni stream non espongono metadati ICY standard. Il player prova due metodi:
1. Lettura diretta dell'header ICY (`icy-metaint`)
2. Interrogazione tramite IPC MPV (`metadata`)

Se entrambi falliscono, lo stream non trasmette metadati — è normale per alcune stazioni.

### Registrazione non disponibile

```bash
ffmpeg -version      # deve rispondere con la versione
# Ubuntu/Debian: sudo apt install ffmpeg
# macOS:         brew install ffmpeg
# Windows:       scarica da https://ffmpeg.org/download.html
```

### Notifiche non appaiono (Linux)

```bash
notify-send "Test" "Funziona?"
# Se il comando fallisce:
sudo apt install libnotify-bin   # Ubuntu/Debian
sudo dnf install libnotify       # Fedora
```

### Ricerca RadioBrowser non risponde

La ricerca usa l'API pubblica su HTTPS (con fallback HTTP). Se la rete blocca il traffico esterno, la ricerca non sarà disponibile ma il player funzionerà normalmente.

### Frecce di navigazione non funzionano

Usa un terminale che supporta le sequenze ANSI (qualsiasi terminale moderno). Evita IDE senza terminale integrato.

---

## 🧪 Sviluppo e test

```bash
pip install -e ".[dev]"     # o: pip install -r requirements.txt + pytest
pytest                      # 32 test (parser M3U, modelli, config, logging, cronologia)
```

---

## 📜 Licenza

Distribuito sotto la **GNU General Public License v3.0**.

```
Copyright (C) 2025–2026 Andres Zanzani <azanzani@gmail.com>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
```

---

## 👨‍💻 Autore

**Andres Zanzani**

- 📧 [azanzani@gmail.com](mailto:azanzani@gmail.com)
- 🐙 GitHub: [@buzzqw](https://github.com/buzzqw)

---

## 🤝 Contribuire

1. Fai un fork del repository
2. Crea un branch (`git checkout -b feature/nuova-funzione`)
3. Fai commit delle modifiche
4. Fai push del branch
5. Apri una **Pull Request**

Per bug e richieste di funzionalità usa la sezione [Issues](https://github.com/buzzqw/radioplayer/issues).

---

<div align="center">

🎵 **Buon ascolto!** 🎵

*Fatto con ❤️ e Python*

</div>
