# 🎵 Radio Player M3U

![Python](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-GPL%20v3-green)
![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey)
![MPV](https://img.shields.io/badge/Requires-mpv-orange)
![Rich](https://img.shields.io/badge/TUI-Rich-purple)

Lettore di stazioni radio da terminale, **cross-platform** (Linux · macOS · Windows), con interfaccia TUI colorata basata su [Rich](https://github.com/Textualize/rich), metadati in tempo reale, registrazione stream e ricerca integrata su [RadioBrowser.info](https://www.radio-browser.info).

---

## 📸 Anteprima

### Schermata principale

```
╭──────────────────────────────────────────────────────────────────────────╮
│ 🎵 RADIO PLAYER M3U    ⏰ 14:32:18    00:47    🔊 Volume: 80%  📝 ✗  🔔  │
╰──────────────────────────────────────────────────────────────────────────╯
╭─ Status ─────────────────────────────────────────────────────────────────╮
│ ▶  IN RIPRODUZIONE  │  📡 Radio Deejay                                   │
│ 🎤 The Weeknd  🎼 Blinding Lights  [01:23]                               │
│ 🔊 128 kbps • AAC • 📦 OK                                                │
╰──────────────────────────────────────────────────────────────────────────╯
╭─ 📻 Stazioni (9 totali) ─────────────────────────────────────────────────╮
│       1  IT::Venice Radio                                                │
│       2  IT::Radio24                                                     │
│  👉▶️  3  IT::Radio Deejay                                               │
│       4  IT::RDS                                                         │
│       5  IT::Radio Rai1                                                  │
│       6  IT::Radio Rai2                                                  │
│       7  IT::Radio Rai3                                                  │
│       8  IT::Radio Rai5 Classica                                         │
│       9  IT::Radio Classica CH                                           │
╰──────────────────────────────────────────────────────────────────────────╯
╭─ 🎮 Controlli ───────────────────────────────────────────────────────────╮
│ ↑/↓ Seleziona  p/Space Play/Pausa  +/= Vol+  -/_ Vol-  m Muto  b Sfoglia │
│ r Rec  l Log  t Notifiche  h Cronologia  s Salva  1-9+↵ Vai a #  q Esci  │
╰──────────────────────────────────────────────────────────────────────────╯
```

### Ricerca RadioBrowser.info (tasto `b`)

```
╭──────────────────────────────────────────────────────────────────────────╮
│ 🎵 RADIO PLAYER M3U    ⏰ 14:33:05    01:34    🔊 Volume: 80%  📝 ✗  🔔  │
╰──────────────────────────────────────────────────────────────────────────╯
╭─ 🔍 RadioBrowser.info  ✅ 20 stazioni trovate ───────────────────────────╮
│ radio italia_                                                            │
╰──────────────────────────────────────────────────────────────────────────╯
╭─ Risultati (20) ─────────────────────────────────────────────────────────╮
│    Nome                           Paese   kbps  Codec  ★ Voti            │
│ 👉 Virgin Radio Italia            Italy    128  MP3    16116             │
│    Radio Italia Solo Musica       Italy      0  MP3     9276             │
│    CLASSIC HITS RADIO Italia      Italy    192  AAC     5844             │
│    NEW HITS RADIO Italia          Italy    320  MP3     3849             │
│    Radio Italia Anni 60           Italy     64  MP3     2998             │
╰──────────────────────────────────────────────────────────────────────────╯
╭─ 🎮 Comandi ricerca ─────────────────────────────────────────────────────╮
│ ↑/↓ Naviga  ↵ Aggiungi a M3U  p Ascolta anteprima  ⌫ Cancella  Esc Torna │
╰──────────────────────────────────────────────────────────────────────────╯
```

---

## ✨ Caratteristiche

| | Funzionalità |
|---|---|
| 📻 | Riproduzione di qualsiasi stream radio supportato da MPV (MP3, AAC, OGG, HLS…) |
| 🖥️ | Interfaccia TUI con 10 stazioni sempre visibili, nessuno scroll necessario |
| 🎵 | Metadati automatici via ICY: artista, titolo del brano e timer in tempo reale |
| 📊 | Statistiche live: bitrate, codec e stato del buffer |
| 🔊 | Controllo volume istantaneo senza interrompere la riproduzione |
| 🔍 | Ricerca su RadioBrowser.info — 40.000+ stazioni, ordinabili per popolarità |
| ➕ | Aggiunta stazioni al M3U da RadioBrowser con controllo duplicati automatico |
| 👂 | Anteprima di una stazione trovata prima di salvarla |
| 🔴 | Registrazione dello stream in MP3 tramite ffmpeg |
| 📜 | Cronologia brani (ultimi 100), esportabile in JSON |
| 🔔 | Notifiche desktop native al cambio brano (`notify-send` su Linux, Toast su Windows) |
| 📝 | Logging su file rotante, attivabile/disattivabile a runtime senza riavvio |
| ⏱️ | Uptime di sessione persistente (non si resetta al cambio stazione) |
| 🖥️ | Cross-platform: Linux, macOS, Windows |

---

## 🚀 Avvio rapido

```bash
# 1. Clona il repository
git clone https://github.com/buzzqw/radio-player-m3u.git
cd radio-player-m3u

# 2. Installa le dipendenze Python
pip3 install -r requirements.txt

# 3. Installa mpv (vedi sotto per il tuo sistema)

# 4. Avvia con il file M3U di esempio incluso
python3 radio_player.py radio.m3u
```

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
2. Installa **MPV** da [mpv.io](https://mpv.io/installation/) e aggiungi la cartella al PATH di sistema
3. *(Opzionale)* Installa **ffmpeg** da [ffmpeg.org](https://ffmpeg.org/download.html) per la registrazione
4. Installa le dipendenze:

```cmd
pip install -r requirements.txt
pip install pywin32 win10toast
```

---

## ▶️ Utilizzo

```bash
# Avvia con un file M3U specifico
python3 radio_player.py mie_radio.m3u

# Auto-rileva il primo file .m3u nella cartella corrente
python3 radio_player.py
```

All'avvio viene selezionata automaticamente la prima stazione. Premi `p` o `Spazio` per iniziare ad ascoltare.

---

## 📋 Formato file M3U

Il player supporta il formato **M3U esteso** (`#EXTM3U`) con attributi opzionali:

```m3u
#EXTM3U

#EXTINF:-1 group-title="Italiana" tvg-logo="https://example.com/logo.png",Radio Deejay
http://deejay.example.com/stream.mp3

#EXTINF:-1 group-title="Classica",Radio Classica
http://classica.example.com/stream

#EXTINF:-1,IT::Radio Rai1
http://icestreaming.rai.it/1.mp3
```

> **Suggerimento:** Premi `b` per cercare stazioni su RadioBrowser.info e aggiungerle automaticamente al tuo file M3U con un solo tasto.

---

## 🎮 Comandi da tastiera

### Riproduzione normale

| Tasto | Azione |
|-------|--------|
| `↑` `↓` | Seleziona stazione (senza avviarla) |
| `p` · `Spazio` · `Invio` | Play / Pausa |
| `+` `=` | Volume +5% |
| `-` `_` | Volume -5% |
| `m` | Muto / Riattiva audio |
| `1`–`9` poi `Invio` | Salta direttamente alla stazione numero N |
| `b` | Apre la ricerca RadioBrowser.info |
| `r` | Avvia / ferma registrazione stream *(richiede ffmpeg)* |
| `t` | Attiva / disattiva notifiche cambio brano |
| `l` | Attiva / disattiva log su file |
| `h` | Mostra gli ultimi brani ascoltati |
| `s` | Esporta la cronologia brani in JSON |
| `q` | Esci |

### Modalità ricerca RadioBrowser (`b`)

| Tasto | Azione |
|-------|--------|
| *(digita)* | Cerca stazioni per nome — ricerca automatica dopo 0,3 s |
| `↑` `↓` | Naviga tra i risultati |
| `Invio` | Aggiunge la stazione selezionata al file M3U |
| `p` | Ascolta anteprima senza salvare nel M3U |
| `Spazio` | Ferma l'anteprima in corso |
| `⌫` | Cancella l'ultimo carattere digitato |
| `Esc` | Torna alla lista stazioni |

---

## 🔍 Ricerca RadioBrowser.info

Il player integra la API pubblica di [RadioBrowser.info](https://www.radio-browser.info), un database aperto con oltre **40.000 stazioni** da tutto il mondo.

**Come funziona:**

1. Premi `b` per aprire la modalità sfoglia
2. Digita il nome (anche parziale) — la ricerca parte automaticamente dopo 0,3 secondi
3. I risultati sono ordinati per **popolarità** (★ voti della community)
4. Per ogni stazione vengono mostrati: nome, paese, bitrate, codec e voti
5. Le stazioni **già presenti** nel tuo M3U sono segnalate con `✓`
6. `Invio` aggiunge la stazione al file M3U (controlla automaticamente i duplicati per URL e nome)
7. `p` avvia un'anteprima istantanea — `Spazio` per fermarla
8. `Esc` per tornare alla lista

**Feedback visivo dello stato:**

| Stato | Colore bordo | Indicatore |
|-------|-------------|------------|
| Ricerca in corso | 🟡 Giallo | Spinner animato + query cercata |
| Risultati trovati | 🟢 Verde | Numero stazioni trovate |
| Nessun risultato | 🔴 Rosso | Query esatta che non ha prodotto risultati |

---

## 🔧 Dipendenze

### Python (`pip`)

| Pacchetto | Versione | Uso |
|-----------|----------|-----|
| [`rich`](https://github.com/Textualize/rich) | ≥ 13.7 | Interfaccia TUI — obbligatoria |
| [`requests`](https://requests.readthedocs.io) | ≥ 2.31 | Metadati ICY e API RadioBrowser |

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

La ricerca usa l'API pubblica di radio-browser.info su HTTPS (con fallback HTTP). Se la rete blocca il traffico esterno, la ricerca non sarà disponibile ma il player funzionerà normalmente.

### Frecce di navigazione non funzionano

Assicurati di eseguire il player in un terminale che supporta le sequenze ANSI (qualsiasi terminale moderno). Evita di lanciarlo da IDE o editor senza terminale integrato.

---

## 📜 Licenza

Distribuito sotto la **GNU General Public License v3.0**.

```
Copyright (C) 2025 Andres Zanzani <azanzani@gmail.com>

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

I contributi sono benvenuti!

1. Fai un fork del repository
2. Crea un branch per la tua modifica (`git checkout -b feature/nuova-funzione`)
3. Fai commit delle modifiche (`git commit -m 'Aggiunge nuova funzione'`)
4. Fai push del branch (`git push origin feature/nuova-funzione`)
5. Apri una **Pull Request**

Per bug e richieste di funzionalità usa la sezione [Issues](https://github.com/buzzqw/radio-player-m3u/issues).

---

<div align="center">

🎵 **Buon ascolto!** 🎵

*Fatto con ❤️ e Python*

</div>
