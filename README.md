# 🎵 Radio Player M3U

Un lettore di stazioni radio da terminale cross-platform (Linux/Windows) che supporta file M3U con controlli intuitivi e notifiche native.

## ✨ Caratteristiche

- 📻 **Riproduzione stream radio** - Supporta tutti i formati supportati da MPV
- 🎮 **Controlli da tastiera** - Navigazione veloce con frecce e tasti rapidi
- 🔔 **Notifiche native** - Toast notifications su Windows, notify-send su Linux
- 📊 **Informazioni real-time** - Bitrate, codec, buffer status, tempo brano
- 🎵 **Metadati automatici** - Artista, titolo e cambio brano automatico
- 🔊 **Controllo volume** - Regolazione istantanea senza interruzioni
- 🎯 **Navigazione avanzata** - Selezione per numero o navigazione con frecce
- ⏱️ **Timer brano** - Tempo di riproduzione del brano corrente
- 🖥️ **Cross-platform** - Funziona su Linux e Windows

## 📸 Anteprima

```
===========================================================================
🎵 RADIO PLAYER M3U - Versione Terminale
⏰ 14:30:25  Uptime: 02:45                🔔 ON  🔊 75%
===========================================================================

📡 STATO: ▶️ IN RIPRODUZIONE • Radio Italia
🎤 Artista: Coldplay                     📊 128 kbps MP3 📦 OK
🎼 Titolo: Yellow                                     ⏱️ 02:34

📻 STAZIONI DISPONIBILI:
--------------------------------------------------
👆▶️  1. Radio Italia
     2. RTL 102.5
     3. Radio Deejay
     4. Virgin Radio Italy
     5. Radio 105

🎮 CONTROLLI:
🔼 ↑/↓            : Seleziona stazione   🔊 +/=            : Alza volume
▶️  p/Spazio/Invio : Play/Pausa          🔉 -/_            : Abbassa volume
🔇 m              : Muto/Riattiva        🔢 1-9+Invio      : Vai a numero
🔔 t              : Toggle notifiche     ❌ q              : Esci
===========================================================================
© 2025 Andres Zanzani <azanzani@gmail.com> - GPL 3 License
```

## 🚀 Installazione

### Linux (Ubuntu/Debian)

```bash
# Installa le dipendenze
sudo apt update
sudo apt install mpv python3 python3-pip libnotify-bin

# Installa le librerie Python
pip3 install requests

# Scarica il programma
wget https://raw.githubusercontent.com/azanzani/radio-player-m3u/main/radio_player.py
chmod +x radio_player.py
```

### Linux (Fedora/RHEL)

```bash
# Installa le dipendenze
sudo dnf install mpv python3 python3-pip libnotify

# Installa le librerie Python
pip3 install requests

# Scarica il programma
wget https://raw.githubusercontent.com/azanzani/radio-player-m3u/main/radio_player.py
chmod +x radio_player.py
```

### Windows

1. **Installa Python 3.8+** da [python.org](https://python.org)

2. **Installa MPV:**
   - Scarica MPV da [mpv.io](https://mpv.io/installation/)
   - Estrai `mpv.exe` nella stessa cartella del programma o aggiungi al PATH

3. **Installa dipendenze Python:**
   ```cmd
   pip install requests pywin32 win10toast
   ```

4. **Scarica il programma:**
   ```cmd
   curl -O https://raw.githubusercontent.com/azanzani/radio-player-m3u/main/radio_player.py
   ```

## 📝 Uso

### Avvio Base

```bash
# Linux
python3 radio_player.py [file.m3u]

# Windows
python radio_player.py [file.m3u]
```

### Esempi

```bash
# Carica un file M3U specifico
python3 radio_player.py my_stations.m3u

# Auto-rileva file M3U nella cartella corrente
python3 radio_player.py
```

### File M3U di Esempio

Crea un file `radio.m3u`:

```m3u
#EXTM3U
#EXTINF:-1,Radio Italia
http://radioitalia.streamingmedia.it:8100/stream
#EXTINF:-1,RTL 102.5
http://icecast.unitedradio.it/RTL_102_5.mp3
#EXTINF:-1,Radio Deejay
http://deejay-icecast-radioitalia.icecast.teraswitch.com/deejay.mp3
#EXTINF:-1,Virgin Radio Italy
http://icecast.unitedradio.it/Virgin.mp3
#EXTINF:-1,IT::Venice Radio
http://5.135.173.165/stream1
#EXTINF:-1,IT::Radio24
http://shoutcast2.radio24.it:8000
#EXTINF:-1,IT::RDS
http://stream1.rds.it:8000/rds64k
#EXTINF:-1,IT::Radio Rai1
http://icestreaming.rai.it/1.mp3
#EXTINF:-1,IT::Radio Rai2
http://icestreaming.rai.it/2.mp3
#EXTINF:-1,IT::Radio Rai3
http://icestreaming.rai.it/3.mp3
#EXTINF:-1,IT::Radio Rai5 Classica
http://icestreaming.rai.it/5.mp3
#EXTINF:-1,IT::Radio Classica CH
http://relay.publicdomainproject.org/classical.mp3
#EXTINF:-1,IT::Classical Essential
http://strm112.1.fm/polskafm_mobile_mp3
```

## 🎮 Controlli

| Tasto | Azione |
|-------|--------|
| `↑` `↓` | Seleziona stazione (senza avviarla) |
| `p` `Spazio` `Invio` | Play/Pausa stazione selezionata |
| `+` `=` | Alza volume (+5%) |
| `-` `_` | Abbassa volume (-5%) |
| `m` | Muto/Riattiva |
| `1-9` + `Invio` | Vai direttamente alla stazione numero N |
| `t` | Attiva/disattiva notifiche cambio brano |
| `q` | Esci dal programma |

## 📊 Informazioni Mostrate

- **⏰ Orario corrente** - Sempre aggiornato
- **⏱️ Uptime** - Tempo totale di utilizzo
- **🔊 Volume** - Livello audio attuale
- **🔔 Notifiche** - Stato ON/OFF
- **📡 Stato riproduzione** - Stazione corrente
- **🎤 Metadati** - Artista e titolo del brano
- **📊 Statistiche audio** - Bitrate, codec, buffer
- **⏱️ Timer brano** - Tempo di riproduzione corrente

## 🔔 Notifiche

### Linux
Il programma prova automaticamente diversi sistemi di notifica:
- `notify-send` (standard)
- `gdbus` (GNOME/systemd) 
- `zenity` (fallback grafico)
- Output terminale (ultimo fallback)

### Windows
- **Windows 10/11**: Toast notifications native
- **Fallback**: MessageBox o output terminale

## 🛠️ Risoluzione Problemi

### Audio non funziona
```bash
# Verifica che MPV sia installato
mpv --version

# Test manuale stream
mpv --no-video "http://example-radio-stream.com"
```

### Notifiche non appaiono (Linux)
```bash
# Test notifiche
notify-send "Test" "Funziona!"

# Installa se mancante
sudo apt install libnotify-bin  # Ubuntu/Debian
sudo dnf install libnotify      # Fedora
```

### Volume non cambia
- Il volume si applica alle nuove connessioni
- Per applicare immediatamente, riavvia la stazione corrente

## 🔧 Dipendenze

### Python
- `requests` - HTTP requests per metadati
- `socket` - Comunicazione IPC con MPV
- `json` - Parsing comandi MPV
- `platform` - Rilevamento OS

### Sistema Linux
- `mpv` - Player audio/video
- `libnotify-bin` - Notifiche desktop (opzionale)

### Sistema Windows  
- `mpv.exe` - Player audio/video
- `pywin32` - API Windows (opzionale)
- `win10toast` - Toast notifications (opzionale)

## 📜 Licenza

Questo programma è rilasciato sotto la **GNU General Public License v3.0**.

```
Copyright (C) 2025 Andres Zanzani <azanzani@gmail.com>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
```

Vedi il file [LICENSE](LICENSE) per i dettagli completi.

## 👨‍💻 Autore

**Andres Zanzani**
- 📧 Email: azanzani@gmail.com
- 🐙 GitHub: [@azanzani](https://github.com/buzzqw)

## 🤝 Contribuire

I contributi sono benvenuti! Per favore:

1. 🍴 Fai un fork del repository
2. 🌿 Crea un branch per la tua feature (`git checkout -b feature/AmazingFeature`)
3. 💾 Commit le tue modifiche (`git commit -m 'Add some AmazingFeature'`)
4. 📤 Push al branch (`git push origin feature/AmazingFeature`)
5. 🔀 Apri una Pull Request

## 🐛 Segnalare Bug

Usa la sezione [Issues](https://github.com/azanzani/radio-player-m3u/issues) per:
- 🐛 Segnalare bug
- 💡 Proporre nuove funzionalità  
- ❓ Fare domande

## ⭐ Supporta il Progetto

Se questo progetto ti è utile:
- ⭐ Metti una stella su GitHub
- 🐛 Segnala bug o problemi
- 🔀 Contribuisci con miglioramenti
- 📢 Condividi con altri

## 📋 TODO

- [ ] Playlist management (aggiunta/rimozione stazioni)
- [ ] Equalizzatore integrato
- [ ] Registrazione stream
- [ ] Supporto podcast
- [ ] Interfaccia grafica opzionale
- [ ] Docker container
- [ ] Snap package
- [ ] Homebrew formula (macOS)

---

🎵 **Buon ascolto!** 🎵