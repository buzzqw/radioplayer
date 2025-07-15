#!/usr/bin/env python3
"""
Radio Player M3U - Lettore di stazioni radio da file M3U (Cross-Platform)

Copyright (C) 2025 Andres Zanzani <azanzani@gmail.com>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.

Compatibile con Linux e Windows.

Controlli:
- Frecce Su/Giù: seleziona stazione (senza cambiarla)
- p/Spazio/Invio: play/pausa stazione selezionata
- m: muto/riattiva
- +: alza volume
- -: abbassa volume
- t: toggle notifiche cambio brani
- 1-9+Invio: vai a numero stazione
- q: esci

Requisiti:
- Linux: mpv, libnotify-bin (opzionale per notifiche)
- Windows: mpv.exe, pywin32 (opzionale), win10toast (opzionale)
"""

import subprocess
import threading
import time
import re
import sys
import os
import select
import termios
import tty
import signal
import requests
import socket
import json
import platform
from urllib.parse import urlparse
from datetime import datetime

# Importazioni condizionali per Windows
if platform.system() == "Windows":
    import msvcrt
    try:
        import win32gui
        import win32con
        WIN32_AVAILABLE = True
    except ImportError:
        WIN32_AVAILABLE = False
else:
    WIN32_AVAILABLE = False

class RadioStation:
    def __init__(self, name, url):
        self.name = name
        self.url = url
    
    def __str__(self):
        return self.name

class TerminalRadioPlayer:
    def __init__(self):
        # Variabili di stato
        self.stations = []
        self.selected_station_index = 0
        self.playing_station_index = -1
        self.is_playing = False
        self.is_paused = False
        self.is_muted = False
        self.volume = 50
        self.running = True
        self.mpv_process = None
        self.current_song = ""
        self.current_artist = ""
        self.stream_title = ""
        self.bitrate = ""
        self.start_time = None
        
        # Socket/Named pipe per controllare MPV
        if platform.system() == "Windows":
            self.mpv_socket = r"\\.\pipe\radio_player_mpv"
        else:
            self.mpv_socket = "/tmp/radio_player_mpv.sock"
        
        # Navigazione numerica
        self.number_input_mode = False
        self.number_buffer = ""
        
        # Flag per forzare aggiornamento interfaccia
        self.force_update = False
        
        # Popup cambio canzone
        self.show_song_popups = True
        self.last_song_info = ""
        
        # Informazioni tecniche stream
        self.audio_bitrate = ""
        self.buffer_status = ""
        self.audio_codec = ""
        self.cache_duration = ""
        
        # Tempo brano corrente
        self.current_song_start_time = None
        self.pause_start_time = None
        self.total_pause_time = 0
        
        # Configurazione terminale
        self.old_settings = None
        
        # Verifica MPV
        if not self.check_mpv():
            print("❌ MPV non è installato. Installa con:")
            print("   Ubuntu/Debian: sudo apt install mpv")
            print("   Fedora: sudo dnf install mpv")
            print("   macOS: brew install mpv")
            sys.exit(1)
    
    def check_mpv(self):
        """Verifica se mpv è installato"""
        try:
            subprocess.run(['mpv', '--version'], 
                         stdout=subprocess.DEVNULL, 
                         stderr=subprocess.DEVNULL, 
                         check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
    
    def setup_terminal(self):
        """Configura il terminale per input non bloccante"""
        if platform.system() == "Windows":
            # Windows non ha bisogno di configurazione speciale
            pass
        else:
            self.old_settings = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
        
    def restore_terminal(self):
        """Ripristina le impostazioni del terminale"""
        if platform.system() == "Windows":
            pass
        else:
            if self.old_settings:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)
    
    def get_char(self):
        """Legge un carattere da stdin - cross-platform"""
        if platform.system() == "Windows":
            if msvcrt.kbhit():
                char = msvcrt.getch().decode('utf-8', errors='ignore')
                
                # Gestione tasti speciali su Windows
                if char == '\xe0':  # Tasti speciali
                    char = msvcrt.getch().decode('utf-8', errors='ignore')
                    if char == 'H':  # Freccia su
                        return 'UP'
                    elif char == 'P':  # Freccia giù
                        return 'DOWN'
                    elif char == 'M':  # Freccia destra
                        return 'RIGHT'
                    elif char == 'K':  # Freccia sinistra
                        return 'LEFT'
                elif char == '\x1b':  # ESC
                    return 'ESC'
                
                return char
            return None
        else:
            # Linux/Unix
            if select.select([sys.stdin], [], [], 0.1) == ([sys.stdin], [], []):
                char = sys.stdin.read(1)
                
                if char == '\x1b':  # Sequenza ESC
                    try:
                        next_chars = sys.stdin.read(2)
                        if next_chars == '[A':
                            return 'UP'
                        elif next_chars == '[B':
                            return 'DOWN'
                        elif next_chars == '[C':
                            return 'RIGHT'
                        elif next_chars == '[D':
                            return 'LEFT'
                        else:
                            return 'ESC'
                    except:
                        return 'ESC'
                
                return char
            return None
    
    def clear_screen(self):
        """Pulisce lo schermo"""
        os.system('clear' if os.name == 'posix' else 'cls')
    
    def load_m3u_file(self, file_path):
        """Carica e analizza un file M3U"""
        try:
            self.stations = self.parse_m3u(file_path)
            return True
        except Exception as e:
            print(f"Errore nel caricamento del file M3U: {e}")
            return False
    
    def parse_m3u(self, file_path):
        """Analizza un file M3U e restituisce una lista di stazioni radio"""
        stations = []
        current_name = ""
        
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                lines = file.readlines()
        except UnicodeDecodeError:
            with open(file_path, 'r', encoding='latin-1') as file:
                lines = file.readlines()
        
        for line in lines:
            line = line.strip()
            
            if line.startswith('#EXTINF:'):
                match = re.search(r'#EXTINF:[^,]*,(.+)', line)
                if match:
                    current_name = match.group(1).strip()
                else:
                    current_name = "Stazione Sconosciuta"
                    
            elif line and not line.startswith('#'):
                if self.is_valid_url(line):
                    if not current_name:
                        current_name = f"Stazione {len(stations) + 1}"
                    stations.append(RadioStation(current_name, line))
                    current_name = ""
        
        return stations
    
    def is_valid_url(self, url):
        """Verifica se l'URL è valido"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except:
            return False
    
    def get_current_song_time(self):
        """Restituisce il tempo di riproduzione del brano corrente"""
        if self.current_song_start_time and self.is_playing:
            if self.is_paused and self.pause_start_time:
                # Se in pausa, calcola fino al momento della pausa
                elapsed = self.pause_start_time - self.current_song_start_time - self.total_pause_time
            else:
                # Se in riproduzione, calcola tempo totale meno pause
                elapsed = time.time() - self.current_song_start_time - self.total_pause_time
            
            # Non mostrare tempi negativi
            elapsed = max(0, elapsed)
            minutes = int(elapsed // 60)
            seconds = int(elapsed % 60)
            return f"{minutes:02d}:{seconds:02d}"
        return "00:00"
    
    def get_uptime(self):
        """Restituisce il tempo di riproduzione"""
        if self.start_time and self.is_playing and not self.is_paused:
            elapsed = time.time() - self.start_time
            hours = int(elapsed // 3600)
            minutes = int((elapsed % 3600) // 60)
            seconds = int(elapsed % 60)
            if hours > 0:
                return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                return f"{minutes:02d}:{seconds:02d}"
        return "00:00"
    
    def get_right_info(self):
        """Restituisce le informazioni tecniche di destra (bitrate, codec, buffer)"""
        right_info = ""
        
        # Bitrate (preferisce quello da MPV se disponibile)
        if self.audio_bitrate:
            right_info += f"📊 {self.audio_bitrate}"
        elif self.bitrate:
            if ',' in self.bitrate:
                parts = self.bitrate.split(',')
                numbers = []
                for part in parts:
                    match = re.search(r'(\d+)', part.strip())
                    if match:
                        numbers.append(int(match.group(1)))
                if numbers:
                    min_bitrate = min(numbers)
                    right_info += f"📊 {min_bitrate} kbps"
            else:
                right_info += f"📊 {self.bitrate}"
        
        # Codec
        if self.audio_codec:
            right_info += f" {self.audio_codec}"
        
        # Buffer status
        if self.buffer_status:
            if self.buffer_status == "BUFFERING":
                right_info += f" 🔄 {self.buffer_status}"
            else:
                right_info += f" 📦 {self.buffer_status}"
        
        # Cache duration
        if self.cache_duration:
            right_info += f" ⏱️ {self.cache_duration}"
                
        return right_info
    
    def display_interface(self):
        """Mostra l'interfaccia del terminale"""
        self.clear_screen()
        current_time = datetime.now().strftime("%H:%M:%S")
        
        print("=" * 75)
        print("🎵 RADIO PLAYER M3U - Versione Terminale")
        
        # Linea con orario, uptime, volume e stato popup
        time_line = f"⏰ {current_time}"
        uptime_text = f"Uptime: {self.get_uptime()}"
        
        if self.is_muted:
            volume_text = "🔇 MUTO"
        else:
            volume_text = f"🔊 {self.volume}%"
            
        popup_status = "🔔 ON" if self.show_song_popups else "🔔 OFF"
        
        # Calcola spazi per allineamento
        total_width = 75
        left_part = f"{time_line}  {uptime_text}"
        right_part = f"{popup_status}  {volume_text}"
        spaces_needed = total_width - len(left_part) - len(right_part) - 2
        
        if spaces_needed > 0:
            print(f"{left_part}{' ' * spaces_needed}{right_part}")
        else:
            print(f"{left_part}  {right_part}")
            
        print("=" * 75)
        print()
        
        if not self.stations:
            print("❌ Nessuna stazione caricata")
            print("Uso: python3 radio_player.py [file.m3u]")
            return
        
        # Stato corrente
        current_station = self.stations[self.selected_station_index]
        playing_station = self.stations[self.playing_station_index] if self.playing_station_index >= 0 else None
        
        # Stato su una linea - senza ripetizione
        if self.is_playing and not self.is_paused:
            status = "▶️ IN RIPRODUZIONE"
        elif self.is_paused:
            status = "⏸️ IN PAUSA"
        else:
            status = "⏹️ FERMATO"
        
        if playing_station:
            print(f"📡 STATO: {status} • {playing_station.name}")
        else:
            print(f"📡 STATO: {status}")
        
        # Informazioni brano corrente - senza riga vuota sopra
        if self.is_playing:
            
            if self.current_artist and self.current_song:
                # Artista e titolo separati
                artist_line = f"🎤 Artista: {self.current_artist}"
                right_info = self.get_right_info()
                
                if right_info:
                    spaces_needed = 73 - len(artist_line) - len(right_info)
                    if spaces_needed > 0:
                        artist_line += " " * spaces_needed + right_info
                    else:
                        artist_line += f"  {right_info}"
                print(artist_line)
                
                # Titolo con tempo brano
                song_time = self.get_current_song_time()
                title_line = f"🎼 Titolo: {self.current_song}"
                if song_time != "00:00":
                    time_info = f"⏱️ {song_time}"
                    spaces_needed = 73 - len(title_line) - len(time_info)
                    if spaces_needed > 0:
                        title_line += " " * spaces_needed + time_info
                    else:
                        title_line += f"  {time_info}"
                print(title_line)
                
            elif self.current_song:
                # Solo titolo (senza artista)
                song_line = f"🎼 {self.current_song}"
                song_time = self.get_current_song_time()
                right_parts = []
                
                if self.get_right_info():
                    right_parts.append(self.get_right_info())
                if song_time != "00:00":
                    right_parts.append(f"⏱️ {song_time}")
                
                if right_parts:
                    right_info = "  ".join(right_parts)
                    spaces_needed = 73 - len(song_line) - len(right_info)
                    if spaces_needed > 0:
                        song_line += " " * spaces_needed + right_info
                    else:
                        song_line += f"  {right_info}"
                print(song_line)
                
            elif self.stream_title:
                # Stream title generico
                title_line = f"📺 {self.stream_title}"
                right_info = self.get_right_info()
                
                if right_info:
                    spaces_needed = 73 - len(title_line) - len(right_info)
                    if spaces_needed > 0:
                        title_line += " " * spaces_needed + right_info
                    else:
                        title_line += f"  {right_info}"
                print(title_line)
                
            else:
                # Messaggio di caricamento - senza volume
                loading_line = f"🎤 Caricamento informazioni..."
                right_info = self.get_right_info()
                
                if right_info:
                    spaces_needed = 73 - len(loading_line) - len(right_info)
                    if spaces_needed > 0:
                        loading_line += " " * spaces_needed + right_info
                    else:
                        loading_line += f"  {right_info}"
                print(loading_line)
        
        print()
        print("📻 STAZIONI DISPONIBILI:")
        print("-" * 50)
        
        # Mostra fino a 10 stazioni con scroll
        start_idx = max(0, self.selected_station_index - 5)
        end_idx = min(len(self.stations), start_idx + 10)
        
        if start_idx > 0:
            print("    ⬆️  ... altre stazioni sopra ...")
        
        for i in range(start_idx, end_idx):
            station = self.stations[i]
            markers = ""
            
            if i == self.selected_station_index:
                markers += "👆"
            else:
                markers += "  "
            
            if i == self.playing_station_index and self.is_playing:
                if not self.is_paused:
                    markers += " ▶️"
                else:
                    markers += " ⏸️"
            else:
                markers += "  "
            
            line = f"{markers} {i+1:2d}. {station.name}"
            
            if i == self.selected_station_index:
                print(f"\033[7m{line}\033[0m")
            else:
                print(line)
        
        if end_idx < len(self.stations):
            print("    ⬇️  ... altre stazioni sotto ...")
        
        print()
        print("🎮 CONTROLLI:")
        print("-" * 50)
        controls = [
            ("🔼 ↑/↓            : Seleziona stazione", "🔊 +/=            : Alza volume"),
            ("▶️  p/Spazio/Invio : Play/Pausa", "  🔉 -/_            : Abbassa volume"),
            ("🔇 m              : Muto/Riattiva", "🔢 1-9+Invio      : Vai a numero"),
            ("🔔 t              : Toggle notifiche brani", "❌ q              : Esci")
        ]
        
        for left, right in controls:
            if right:
                print(f"{left:<42}{right}")
            else:
                print(left)
        
        if self.number_input_mode:
            print()
            print(f"🔢 INSERISCI NUMERO: {self.number_buffer}_ (Invio per confermare, Esc per annullare)")
        
        print("=" * 75)
        print("© 2025 Andres Zanzani <azanzani@gmail.com> - GPL 3 License")
    
    def show_song_popup(self, artist, song):
        """Mostra notifica di sistema per cambio canzone - cross-platform"""
        if not self.show_song_popups:
            return
            
        try:
            # Prepara il messaggio per la notifica
            if artist and song:
                message = f"{artist} - {song}"
                title = "🎵 Nuovo Brano"
            elif song:
                message = song
                title = "🎵 In Onda"
            else:
                return
            
            if platform.system() == "Windows":
                # Windows: usa toast notifications o fallback
                try:
                    # Prova con win10toast se disponibile
                    from win10toast import ToastNotifier
                    toaster = ToastNotifier()
                    toaster.show_toast(title, message, icon_path=None, duration=4)
                except ImportError:
                    # Fallback: usa messagebox
                    if WIN32_AVAILABLE:
                        import win32api
                        win32api.MessageBox(0, message, title, win32con.MB_ICONINFORMATION | win32con.MB_SETFOREGROUND)
                    else:
                        # Ultimo fallback: stampa nel terminale
                        print(f"\n🔔 {title}: {message}")
            else:
                # Linux: prova diversi metodi di notifica
                notification_sent = False
                
                # Metodo 1: notify-send standard
                try:
                    result = subprocess.run([
                        'notify-send',
                        title,
                        message,
                        '--icon=audio-x-generic',
                        '--expire-time=4000',
                        '--app-name=RadioPlayer'
                    ], check=True, capture_output=True, text=True, timeout=5)
                    notification_sent = True
                except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                    pass
                
                # Metodo 2: notify-send semplificato
                if not notification_sent:
                    try:
                        result = subprocess.run([
                            'notify-send',
                            f"{title}: {message}"
                        ], check=True, capture_output=True, text=True, timeout=5)
                        notification_sent = True
                    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                        pass
                
                # Metodo 3: gdbus (per GNOME/systemd)
                if not notification_sent:
                    try:
                        subprocess.run([
                            'gdbus', 'call', '--session',
                            '--dest=org.freedesktop.Notifications',
                            '--object-path=/org/freedesktop/Notifications',
                            '--method=org.freedesktop.Notifications.Notify',
                            'RadioPlayer', '0', 'audio-x-generic',
                            title, message, '[]', '{}', '4000'
                        ], check=True, capture_output=True, text=True, timeout=5)
                        notification_sent = True
                    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                        pass
                
                # Metodo 4: zenity
                if not notification_sent:
                    try:
                        subprocess.run([
                            'zenity', '--notification',
                            f'--text={title}: {message}',
                            '--timeout=4'
                        ], check=True, capture_output=True, text=True, timeout=5)
                        notification_sent = True
                    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                        pass
                
                # Se nessun metodo funziona, fallback nel terminale
                if not notification_sent:
                    print(f"\n🔔 {title}: {message}")
            
        except Exception as e:
            # Fallback universale: stampa nel terminale
            if artist and song:
                print(f"\n🔔 Nuovo brano: {artist} - {song}")
            elif song:
                print(f"\n🔔 In onda: {song}")
    
    def play_selected_station(self):
        """Avvia la riproduzione della stazione selezionata"""
        if not self.stations:
            return
        
        station = self.stations[self.selected_station_index]
        self.stop()
        
        self.playing_station_index = self.selected_station_index
        
        try:
            # Rimuovi socket/pipe precedente se esiste
            if platform.system() == "Windows":
                # Su Windows MPV usa named pipes
                pass  # Non serve rimuovere named pipes
            else:
                if os.path.exists(self.mpv_socket):
                    os.remove(self.mpv_socket)
            
            cmd = [
                'mpv',
                '--no-video',
                '--volume=' + str(self.volume),
                '--quiet',
                '--no-terminal',
                '--cache=yes',
                '--demuxer-max-bytes=1M',
                '--audio-buffer=0.1'
            ]
            
            # Aggiungi IPC server in base al sistema operativo
            if platform.system() == "Windows":
                cmd.append('--input-ipc-server=' + self.mpv_socket)
            else:
                cmd.append('--input-ipc-server=' + self.mpv_socket)
            
            cmd.append(station.url)
            
            self.mpv_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid
            )
            
            time.sleep(1)
            
            if self.mpv_process and self.mpv_process.poll() is None:
                self.is_playing = True
                self.is_paused = False
                self.start_time = time.time()
                self.current_song_start_time = time.time()  # Inizia timer brano
                self.pause_start_time = None  # Reset pause timer
                self.total_pause_time = 0     # Reset pause totale
                
                # Avvia thread per metadati e statistiche continue
                metadata_thread = threading.Thread(target=self.monitor_metadata_continuous, daemon=True)
                metadata_thread.start()
                
                # Avvia thread separato per statistiche tecniche (più frequente)
                stats_thread = threading.Thread(target=self.monitor_stream_stats, daemon=True)
                stats_thread.start()
                
        except Exception as e:
            self.is_playing = False
            self.playing_station_index = -1
    
    def monitor_metadata_continuous(self):
        """Monitora i metadati dello stream ogni 5 secondi"""
        while self.is_playing and self.running and self.playing_station_index >= 0:
            station = self.stations[self.playing_station_index]
            
            try:
                headers = {
                    'Icy-MetaData': '1',
                    'User-Agent': 'RadioPlayer/1.0',
                    'Accept': '*/*',
                    'Range': 'bytes=0-'  # Richiedi solo l'inizio dello stream
                }
                
                # Timeout breve per non bloccare
                response = requests.get(station.url, headers=headers, stream=True, timeout=3)
                
                # Estrae bitrate solo la prima volta
                if not self.bitrate:
                    icy_bitrate = response.headers.get('icy-br', '')
                    if icy_bitrate:
                        self.bitrate = f"{icy_bitrate} kbps"
                
                # Estrae metaint per i metadati
                metaint = response.headers.get('icy-metaint')
                if metaint:
                    try:
                        metaint = int(metaint)
                        
                        # Legge dati audio
                        audio_data = response.raw.read(metaint)
                        
                        # Legge lunghezza metadati
                        meta_length_byte = response.raw.read(1)
                        
                        if meta_length_byte:
                            meta_length = ord(meta_length_byte) * 16
                            
                            if meta_length > 0:
                                # Legge metadati
                                metadata = response.raw.read(meta_length).decode('utf-8', errors='ignore')
                                
                                # Estrae StreamTitle
                                title_match = re.search(r"StreamTitle='([^']*)'", metadata)
                                
                                if title_match:
                                    stream_title = title_match.group(1).strip()
                                    
                                                                                # Aggiorna solo se diverso dal precedente
                                    if stream_title and stream_title != self.stream_title:
                                        old_artist = self.current_artist
                                        old_song = self.current_song
                                        
                                        self.stream_title = stream_title
                                        
                                        # Prova a separare artista - titolo
                                        if ' - ' in stream_title:
                                            parts = stream_title.split(' - ', 1)
                                            new_artist = parts[0].strip()
                                            new_song = parts[1].strip()
                                            
                                            # Aggiorna solo se cambiato
                                            if new_artist != self.current_artist or new_song != self.current_song:
                                                self.current_artist = new_artist
                                                self.current_song = new_song
                                                
                                                # Mostra popup se è un vero cambio (non il primo caricamento)
                                                if old_artist or old_song:
                                                    popup_thread = threading.Thread(
                                                        target=self.show_song_popup, 
                                                        args=(new_artist, new_song), 
                                                        daemon=True
                                                    )
                                                    popup_thread.start()
                                        else:
                                            # Se non c'è separatore, metti tutto come titolo
                                            if stream_title != self.current_song:
                                                old_song_for_popup = self.current_song
                                                self.current_artist = ""
                                                self.current_song = stream_title
                                                
                                                # Mostra popup se è un vero cambio (non il primo caricamento)
                                                if old_song_for_popup:
                                                    popup_thread = threading.Thread(
                                                        target=self.show_song_popup, 
                                                        args=("", stream_title), 
                                                        daemon=True
                                                    )
                                                    popup_thread.start()
                    except Exception:
                        pass
                
                response.close()
                
            except Exception:
                # In caso di errore, non fare nulla e continua
                pass
            
            # Aspetta 2 secondi prima del prossimo controllo (più frequente per rilevare cambi)
            time.sleep(2)
    
    def monitor_stream_stats(self):
        """Monitora le statistiche tecniche dello stream ogni 2 secondi"""
        # Aspetta un po' che MPV si stabilizzi
        time.sleep(3)
        
        while self.is_playing and self.running and self.playing_station_index >= 0:
            self.update_stream_stats()
            time.sleep(2)  # Aggiorna ogni 2 secondi
    
    def toggle_play_pause(self):
        """Avvia/pausa la riproduzione"""
        if not self.stations:
            return
        
        if not self.is_playing:
            self.play_selected_station()
        else:
            if self.playing_station_index != self.selected_station_index:
                self.play_selected_station()
            else:
                if self.mpv_process and self.mpv_process.poll() is None:
                    if self.is_paused:
                        self.play_selected_station()
                    else:
                        os.killpg(os.getpgid(self.mpv_process.pid), signal.SIGSTOP)
                        self.is_paused = True
    
    def stop(self):
        """Ferma la riproduzione - cross-platform"""
        if self.mpv_process:
            try:
                if platform.system() == "Windows":
                    # Windows: termina processo direttamente
                    self.mpv_process.terminate()
                    self.mpv_process.wait(timeout=2)
                else:
                    # Linux: usa killpg
                    os.killpg(os.getpgid(self.mpv_process.pid), signal.SIGTERM)
                    self.mpv_process.wait(timeout=2)
            except:
                try:
                    if platform.system() == "Windows":
                        self.mpv_process.kill()
                    else:
                        os.killpg(os.getpgid(self.mpv_process.pid), signal.SIGKILL)
                except:
                    pass
            self.mpv_process = None
        
        # Pulisci socket/pipe
        if platform.system() == "Linux" and os.path.exists(self.mpv_socket):
            try:
                os.remove(self.mpv_socket)
            except:
                pass
        
        self.is_playing = False
        self.is_paused = False
        self.current_song = ""
        self.current_artist = ""
        self.stream_title = ""
        self.bitrate = ""
        self.start_time = None
        self.playing_station_index = -1
        
        # Pulisci statistiche tecniche
        self.audio_bitrate = ""
        self.buffer_status = ""
        self.audio_codec = ""
        self.cache_duration = ""
        self.current_song_start_time = None
        self.pause_start_time = None
        self.total_pause_time = 0
    
    def change_selection(self, direction):
        """Cambia selezione"""
        if not self.stations:
            return
        self.selected_station_index = (self.selected_station_index + direction) % len(self.stations)
    
    def select_by_number(self, number):
        """Seleziona stazione per numero"""
        if not self.stations:
            return
        if 1 <= number <= len(self.stations):
            self.selected_station_index = number - 1
    
    def get_mpv_property(self, property_name):
        """Ottiene una proprietà da MPV tramite IPC - cross-platform"""
        try:
            import json
            
            # Crea il comando JSON
            cmd = {
                "command": ["get_property", property_name]
            }
            message = json.dumps(cmd) + "\n"
            
            if platform.system() == "Windows":
                # Windows: usa named pipes
                try:
                    import win32file
                    import win32pipe
                    
                    handle = win32file.CreateFile(
                        self.mpv_socket,
                        win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                        0,
                        None,
                        win32file.OPEN_EXISTING,
                        0,
                        None
                    )
                    
                    win32file.WriteFile(handle, message.encode('utf-8'))
                    result, data = win32file.ReadFile(handle, 1024)
                    win32file.CloseHandle(handle)
                    
                    if data:
                        response = json.loads(data.decode('utf-8').strip())
                        if response.get("error") == "success":
                            return response.get("data")
                except ImportError:
                    # Fallback se win32 non disponibile
                    return None
            else:
                # Linux: usa socket Unix
                if not os.path.exists(self.mpv_socket):
                    return None
                
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.settimeout(0.5)
                sock.connect(self.mpv_socket)
                sock.send(message.encode('utf-8'))
                response = sock.recv(1024).decode('utf-8')
                sock.close()
                
                if response:
                    result = json.loads(response.strip())
                    if result.get("error") == "success":
                        return result.get("data")
            
            return None
            
        except Exception:
            return None
    
    def update_stream_stats(self):
        """Aggiorna le statistiche dello stream"""
        if not self.is_playing or not self.mpv_process or self.mpv_process.poll() is not None:
            return
            
        # Ottieni bitrate audio
        bitrate = self.get_mpv_property("audio-bitrate")
        if bitrate:
            self.audio_bitrate = f"{int(bitrate/1000)} kbps"
        
        # Ottieni codec audio
        codec = self.get_mpv_property("audio-codec-name")
        if codec:
            self.audio_codec = codec.upper()
        
        # Ottieni durata buffer
        cache_duration = self.get_mpv_property("demuxer-cache-duration")
        if cache_duration:
            self.cache_duration = f"{cache_duration:.1f}s"
        
        # Verifica se è in buffering
        buffering = self.get_mpv_property("paused-for-cache")
        if buffering:
            self.buffer_status = "BUFFERING"
        else:
            # Ottieni percentuale cache
            cache_percent = self.get_mpv_property("cache-buffering-state")
            if cache_percent is not None:
                self.buffer_status = f"{cache_percent}%"
            else:
                self.buffer_status = "OK"
    
    def send_mpv_command(self, command, *args):
        """Invia comando a MPV tramite IPC - cross-platform"""
        try:
            import json
            
            # Crea il comando JSON
            cmd = {
                "command": [command] + list(args)
            }
            message = json.dumps(cmd) + "\n"
            
            if platform.system() == "Windows":
                # Windows: usa named pipes
                try:
                    import win32file
                    
                    handle = win32file.CreateFile(
                        self.mpv_socket,
                        win32file.GENERIC_WRITE,
                        0,
                        None,
                        win32file.OPEN_EXISTING,
                        0,
                        None
                    )
                    
                    win32file.WriteFile(handle, message.encode('utf-8'))
                    win32file.CloseHandle(handle)
                    return True
                except ImportError:
                    return False
            else:
                # Linux: usa socket Unix
                if not os.path.exists(self.mpv_socket):
                    return False
                
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.settimeout(1.0)
                sock.connect(self.mpv_socket)
                sock.send(message.encode('utf-8'))
                sock.close()
                return True
            
        except Exception:
            return False
        """Invia comando a MPV tramite socket JSON IPC"""
        if not os.path.exists(self.mpv_socket):
            return False
        
        try:
            import socket
            import json
            
            # Crea il comando JSON
            cmd = {
                "command": [command] + list(args)
            }
            
            # Connetti al socket
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            sock.connect(self.mpv_socket)
            
            # Invia comando
            message = json.dumps(cmd) + "\n"
            sock.send(message.encode('utf-8'))
            
            sock.close()
            return True
            
        except Exception:
            return False
    
    def change_volume(self, delta):
        """Cambia il volume - usando comando MPV diretto"""
        self.volume = max(0, min(100, self.volume + delta))
        
        # Invia comando di volume a MPV se sta suonando
        if self.is_playing and self.mpv_process and self.mpv_process.poll() is None:
            # Aspetta un po' che il socket sia pronto
            time.sleep(0.1)
            success = self.send_mpv_command("set_property", "volume", self.volume)
            
            if not success:
                # Se il comando IPC fallisce, fallback al volume di sistema
                try:
                    subprocess.run([
                        'amixer', 'set', 'Master', f"{self.volume}%"
                    ], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except:
                    pass
    
    def toggle_mute(self):
        """Attiva/disattiva il muto - cross-platform"""
        self.is_muted = not self.is_muted
        
        if self.is_playing and self.mpv_process and self.mpv_process.poll() is None:
            # Usa comando MPV per il muto
            success = self.send_mpv_command("set_property", "mute", self.is_muted)
            
            if not success and platform.system() != "Windows":
                # Fallback ai segnali solo su Linux (Windows non supporta SIGSTOP/SIGCONT)
                try:
                    if self.is_muted:
                        os.killpg(os.getpgid(self.mpv_process.pid), signal.SIGSTOP)
                    else:
                        os.killpg(os.getpgid(self.mpv_process.pid), signal.SIGCONT)
                except:
                    pass
    
    def handle_input(self):
        """Gestisce l'input da tastiera - con aggiornamento su richiesta"""
        while self.running:
            char = self.get_char()
            
            if char:
                # Modalità inserimento numero
                if self.number_input_mode:
                    if char.isdigit():
                        self.number_buffer += char
                        self.force_update = True
                    elif char == '\r' or char == '\n':
                        if self.number_buffer:
                            try:
                                number = int(self.number_buffer)
                                self.select_by_number(number)
                            except:
                                pass
                        self.number_input_mode = False
                        self.number_buffer = ""
                        self.force_update = True
                    elif char == 'ESC':
                        self.number_input_mode = False
                        self.number_buffer = ""
                        self.force_update = True
                    continue
                
                # Modalità normale
                if char.lower() == 'q':
                    self.running = False
                elif char.lower() == 'p' or char == ' ' or char == '\r' or char == '\n':
                    self.toggle_play_pause()
                    self.force_update = True
                elif char.lower() == 'm':
                    self.toggle_mute()
                    self.force_update = True
                elif char == '+' or char == '=':
                    self.change_volume(5)
                    self.force_update = True
                elif char == '-' or char == '_':
                    self.change_volume(-5)
                    self.force_update = True
                elif char == 'UP':
                    self.change_selection(-1)
                    self.force_update = True
                elif char == 'DOWN':
                    self.change_selection(1)
                    self.force_update = True
                elif char.lower() == 't':
                    # Toggle notifiche cambio canzone
                    self.show_song_popups = not self.show_song_popups
                    self.clear_screen()
                    print()
                    if self.show_song_popups:
                        print("🔔 Notifiche cambio canzone ATTIVATE")
                        print("   Verranno mostrate le notifiche di sistema")
                        print("   Premi 't' per disattivarle")
                    else:
                        print("🔔 Notifiche cambio canzone DISATTIVATE")
                        print("   Premi 't' per riattivarle")
                    print()
                    time.sleep(2)
                    self.force_update = True
                elif char.isdigit():
                    self.number_input_mode = True
                    self.number_buffer = char
                    self.force_update = True
            
            time.sleep(0.05)
    
    def run(self, m3u_file=None):
        """Avvia il player"""
        try:
            self.setup_terminal()
            
            # Carica file M3U
            if m3u_file:
                if not self.load_m3u_file(m3u_file):
                    return
            else:
                m3u_files = [f for f in os.listdir('.') if f.endswith('.m3u')]
                if m3u_files:
                    if not self.load_m3u_file(m3u_files[0]):
                        return
            
            self.display_interface()
            
            # Avvia il thread per gestire l'input
            input_thread = threading.Thread(target=self.handle_input, daemon=True)
            input_thread.start()
            
            # Loop principale con aggiornamento automatico ogni 0.3 secondi
            last_update = time.time()
            while self.running:
                current_time = time.time()
                
                # Aggiorna l'interfaccia ogni 0.3 secondi o se forzato
                if current_time - last_update >= 0.3 or self.force_update:
                    self.display_interface()
                    last_update = current_time
                    self.force_update = False
                
                time.sleep(0.1)  # Sleep breve per non consumare troppa CPU
                
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()
            self.restore_terminal()
            self.clear_screen()
            print("👋 Arrivederci!")

def main():
    """Funzione principale"""
    print("Radio Player M3U v1.0")
    print("Copyright (C) 2025 Andres Zanzani <azanzani@gmail.com>")
    print("Licensed under GPL 3 - https://www.gnu.org/licenses/gpl-3.0.html")
    
    # Mostra requisiti per sistema operativo
    if platform.system() == "Windows":
        print("Requisiti Windows: MPV, pywin32 (opzionale), win10toast (opzionale)")
    else:
        print("Requisiti Linux: MPV, notify-send/gdbus/zenity (per notifiche)")
    
    print()
    
    m3u_file = None
    if len(sys.argv) > 1:
        m3u_file = sys.argv[1]
        if not os.path.exists(m3u_file):
            print(f"❌ File non trovato: {m3u_file}")
            return
    
    try:
        player = TerminalRadioPlayer()
        player.run(m3u_file)
    except Exception as e:
        print(f"❌ Errore: {e}")
        if platform.system() == "Windows":
            print("Suggerimento: Assicurati che MPV sia nel PATH o nella stessa cartella")
        else:
            print("Suggerimento: Installa MPV con 'sudo apt install mpv' (Ubuntu/Debian)")

if __name__ == "__main__":
    main()
