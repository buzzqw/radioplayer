#!/usr/bin/env python3
"""
Radio Player M3U - VERSIONE CON AGGIORNAMENTO ZERO-LAMPEGGIAMENTO

Copyright (C) 2025 Andres Zanzani <azanzani@gmail.com>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
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
        
        # Layout interfaccia - posizioni fisse delle righe
        self.HEADER_LINE = 1
        self.TITLE_LINE = 2
        self.TIME_LINE = 3
        self.SEPARATOR1_LINE = 4
        self.EMPTY1_LINE = 5
        self.STATUS_LINE = 6
        self.SONG_ARTIST_LINE = 7
        self.SONG_TITLE_LINE = 8
        self.EMPTY2_LINE = 9
        self.STATIONS_HEADER_LINE = 10
        self.STATIONS_SEPARATOR_LINE = 11
        self.STATIONS_START_LINE = 12
        # Le stazioni occupano fino a 12 righe (STATIONS_START_LINE + 11)
        self.CONTROLS_START_LINE = 25  # Dopo le stazioni
        self.NUMBER_INPUT_LINE = 31
        self.FOOTER_LINE = 32
        self.COPYRIGHT_LINE = 33
        
        # Flag per tracciare cosa deve essere aggiornato
        self.need_full_redraw = True
        self.need_timer_update = True
        self.need_status_update = False
        self.need_song_update = False
        self.need_stations_update = False
        self.need_input_update = False
        
        # Cache per evitare aggiornamenti identici
        self.last_timer_text = ""
        self.last_status_text = ""
        self.last_song_text = ""
        self.last_stations_selection = -1
        self.last_input_text = ""
        
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
                
                if char == '\xe0':
                    char = msvcrt.getch().decode('utf-8', errors='ignore')
                    if char == 'H':
                        return 'UP'
                    elif char == 'P':
                        return 'DOWN'
                    elif char == 'M':
                        return 'RIGHT'
                    elif char == 'K':
                        return 'LEFT'
                elif char == '\x1b':
                    return 'ESC'
                
                return char
            return None
        else:
            if select.select([sys.stdin], [], [], 0.1) == ([sys.stdin], [], []):
                char = sys.stdin.read(1)
                
                if char == '\x1b':
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
    
    # Utility per controllo cursore ANSI
    def move_to_line(self, line):
        """Sposta il cursore alla riga specificata, colonna 1"""
        print(f"\033[{line};1H", end="", flush=True)
    
    def clear_line(self):
        """Pulisce la riga corrente"""
        print("\033[K", end="", flush=True)
    
    def update_line(self, line, text):
        """Aggiorna una riga specifica con nuovo testo"""
        self.move_to_line(line)
        self.clear_line()
        print(text, end="", flush=True)
    
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
                elapsed = self.pause_start_time - self.current_song_start_time - self.total_pause_time
            else:
                elapsed = time.time() - self.current_song_start_time - self.total_pause_time
            
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
        """Restituisce le informazioni tecniche di destra"""
        right_info = ""
        
        if self.audio_bitrate:
            right_info += f"🔊 {self.audio_bitrate}"
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
                    right_info += f"🔊 {min_bitrate} kbps"
            else:
                right_info += f"🔊 {self.bitrate}"
        
        if self.audio_codec:
            right_info += f" {self.audio_codec}"
        
        if self.buffer_status:
            if self.buffer_status == "BUFFERING":
                right_info += f" 🔄 {self.buffer_status}"
            else:
                right_info += f" 📦 {self.buffer_status}"
        
        if self.cache_duration:
            right_info += f" ⏱️ {self.cache_duration}"
                
        return right_info
    
    def draw_full_interface(self):
        """Disegna l'interfaccia completa la prima volta"""
        self.clear_screen()
        
        # Header fisso
        print("=" * 75)
        print("🎵 RADIO PLAYER M3U - ZERO LAMPEGGIAMENTO")
        
        # Riga time (verrà aggiornata dinamicamente)
        print(" " * 75)  # Placeholder per timer
        
        print("=" * 75)
        print()
        
        if not self.stations:
            print("❌ Nessuna stazione caricata")
            print("Uso: python3 radio_player.py [file.m3u]")
            return
        
        # Placeholder per stato (verrà aggiornato dinamicamente)
        print(" " * 75)  # STATUS_LINE
        print(" " * 75)  # SONG_ARTIST_LINE 
        print(" " * 75)  # SONG_TITLE_LINE
        print()
        print("📻 STAZIONI DISPONIBILI:")
        print("-" * 50)
        
        # Placeholder per stazioni (verranno aggiornate dinamicamente)
        for i in range(12):  # Spazio per max 12 righe di stazioni
            print(" " * 75)
        
        print()
        print("🎮 CONTROLLI:")
        print("-" * 50)
        
        # Controlli fissi
        controls = [
            ("🔼 ↑/↓            : Seleziona stazione", "🔊 +/=            : Alza volume"),
            ("▶️  p/Spazio/Invio : Play/Pausa", "  🔉 -/_            : Abbassa volume"),
            ("🔇 m              : Muto/Riattiva", "🔢 1-9+Invio      : Vai a numero"),
            ("🔔 t              : Toggle notifiche brani", "❌ q              : Esci")
        ]
        
        for left, right in controls:
            print(f"{left:<42}{right}")
        
        # Placeholder per input numero
        print(" " * 75)  # NUMBER_INPUT_LINE
        print("=" * 75)
        print("© 2025 Andres Zanzani <azanzani@gmail.com> - GPL 3 License")
        
        # Ora forza l'aggiornamento di tutti gli elementi dinamici
        self.need_full_redraw = False
        self.need_timer_update = True
        self.need_status_update = True
        self.need_song_update = True
        self.need_stations_update = True
        self.need_input_update = True
    
    def update_timer_line(self):
        """Aggiorna solo la riga del timer"""
        current_time = datetime.now().strftime("%H:%M:%S")
        time_line = f"⏰ {current_time}"
        uptime_text = f"Uptime: {self.get_uptime()}"
        
        if self.is_muted:
            volume_text = "🔇 MUTO"
        else:
            volume_text = f"🔊 {self.volume}%"
            
        popup_status = "🔔 ON" if self.show_song_popups else "🔕 OFF"
        
        total_width = 75
        left_part = f"{time_line}  {uptime_text}"
        right_part = f"{popup_status}  {volume_text}"
        spaces_needed = total_width - len(left_part) - len(right_part) - 2
        
        if spaces_needed > 0:
            timer_text = f"{left_part}{' ' * spaces_needed}{right_part}"
        else:
            timer_text = f"{left_part}  {right_part}"
        
        # Aggiorna solo se è cambiato
        if timer_text != self.last_timer_text:
            self.update_line(self.TIME_LINE, timer_text)
            self.last_timer_text = timer_text
    
    def update_status_line(self):
        """Aggiorna solo la riga dello stato"""
        playing_station = self.stations[self.playing_station_index] if self.playing_station_index >= 0 else None
        
        if self.is_playing and not self.is_paused:
            status = "▶️ IN RIPRODUZIONE"
        elif self.is_paused:
            status = "⏸️ IN PAUSA"
        else:
            status = "⏹️ FERMATO"
        
        if playing_station:
            status_text = f"📡 STATO: {status} • {playing_station.name}"
        else:
            status_text = f"📡 STATO: {status}"
        
        # Aggiorna solo se è cambiato
        if status_text != self.last_status_text:
            self.update_line(self.STATUS_LINE, status_text)
            self.last_status_text = status_text
    
    def update_song_info(self):
        """Aggiorna solo le righe delle informazioni del brano"""
        artist_line = ""
        title_line = ""
        
        if self.is_playing:
            if self.current_artist and self.current_song:
                artist_line = f"🎤 Artista: {self.current_artist}"
                right_info = self.get_right_info()
                
                if right_info:
                    spaces_needed = 73 - len(artist_line) - len(right_info)
                    if spaces_needed > 0:
                        artist_line += " " * spaces_needed + right_info
                    else:
                        artist_line += f"  {right_info}"
                
                song_time = self.get_current_song_time()
                title_line = f"🎼 Titolo: {self.current_song}"
                if song_time != "00:00":
                    time_info = f"⏱️ {song_time}"
                    spaces_needed = 73 - len(title_line) - len(time_info)
                    if spaces_needed > 0:
                        title_line += " " * spaces_needed + time_info
                    else:
                        title_line += f"  {time_info}"
                
            elif self.current_song:
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
                
                # In questo caso, metti tutto sulla riga artist e lascia title vuota
                artist_line = song_line
                title_line = ""
                
            elif self.stream_title:
                title_line = f"📺 {self.stream_title}"
                right_info = self.get_right_info()
                
                if right_info:
                    spaces_needed = 73 - len(title_line) - len(right_info)
                    if spaces_needed > 0:
                        title_line += " " * spaces_needed + right_info
                    else:
                        title_line += f"  {right_info}"
                        
                artist_line = ""
            else:
                artist_line = f"🎤 Caricamento informazioni..."
                right_info = self.get_right_info()
                
                if right_info:
                    spaces_needed = 73 - len(artist_line) - len(right_info)
                    if spaces_needed > 0:
                        artist_line += " " * spaces_needed + right_info
                    else:
                        artist_line += f"  {right_info}"
                        
                title_line = ""
        
        song_text = f"{artist_line}|{title_line}"  # Uso | come separatore per cache
        
        # Aggiorna solo se è cambiato
        if song_text != self.last_song_text:
            self.update_line(self.SONG_ARTIST_LINE, artist_line)
            self.update_line(self.SONG_TITLE_LINE, title_line)
            self.last_song_text = song_text
    
    def update_stations_list(self):
        """Aggiorna solo la lista delle stazioni quando cambia la selezione"""
        # Aggiorna solo se è cambiata la selezione
        if self.selected_station_index != self.last_stations_selection:
            start_idx = max(0, self.selected_station_index - 5)
            end_idx = min(len(self.stations), start_idx + 10)
            
            line_counter = 0
            
            if start_idx > 0:
                self.update_line(self.STATIONS_START_LINE + line_counter, "    ⬆️  ... altre stazioni sopra ...")
                line_counter += 1
            else:
                self.update_line(self.STATIONS_START_LINE + line_counter, "")
                line_counter += 1
            
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
                
                line_text = f"{markers} {i+1:2d}. {station.name}"
                
                if i == self.selected_station_index:
                    line_text = f"\033[7m{line_text}\033[0m"  # Inversione colori
                
                self.update_line(self.STATIONS_START_LINE + line_counter, line_text)
                line_counter += 1
            
            if end_idx < len(self.stations):
                self.update_line(self.STATIONS_START_LINE + line_counter, "    ⬇️  ... altre stazioni sotto ...")
                line_counter += 1
            else:
                self.update_line(self.STATIONS_START_LINE + line_counter, "")
                line_counter += 1
            
            # Pulisci righe rimaste
            while line_counter < 12:
                self.update_line(self.STATIONS_START_LINE + line_counter, "")
                line_counter += 1
            
            self.last_stations_selection = self.selected_station_index
    
    def update_input_line(self):
        """Aggiorna solo la riga dell'input numerico"""
        if self.number_input_mode:
            input_text = f"🔢 INSERISCI NUMERO: {self.number_buffer}_ (Invio per confermare, Esc per annullare)"
        else:
            input_text = ""
        
        # Aggiorna solo se è cambiato
        if input_text != self.last_input_text:
            self.update_line(self.NUMBER_INPUT_LINE, input_text)
            self.last_input_text = input_text
    
    def display_interface(self):
        """Gestisce gli aggiornamenti dell'interfaccia in modo ottimale"""
        # Primo disegno completo
        if self.need_full_redraw:
            self.draw_full_interface()
            return
        
        # Aggiornamenti parziali secondo necessità
        if self.need_timer_update:
            self.update_timer_line()
            self.need_timer_update = False
        
        if self.need_status_update:
            self.update_status_line()
            self.need_status_update = False
        
        if self.need_song_update:
            self.update_song_info()
            self.need_song_update = False
        
        if self.need_stations_update:
            self.update_stations_list()
            self.need_stations_update = False
        
        if self.need_input_update:
            self.update_input_line()
            self.need_input_update = False
    
    def show_song_popup(self, artist, song):
        """Mostra notifica di sistema per cambio canzone"""
        if not self.show_song_popups:
            return
            
        try:
            if artist and song:
                message = f"{artist} - {song}"
                title = "🎵 Nuovo Brano"
            elif song:
                message = song
                title = "🎵 In Onda"
            else:
                return
            
            if platform.system() == "Windows":
                try:
                    from win10toast import ToastNotifier
                    toaster = ToastNotifier()
                    toaster.show_toast(title, message, icon_path=None, duration=4)
                except ImportError:
                    if WIN32_AVAILABLE:
                        import win32api
                        win32api.MessageBox(0, message, title, win32con.MB_ICONINFORMATION | win32con.MB_SETFOREGROUND)
            else:
                try:
                    subprocess.run([
                        'notify-send', title, message,
                        '--icon=audio-x-generic', '--expire-time=4000'
                    ], check=True, capture_output=True, timeout=5)
                except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                    try:
                        subprocess.run(['notify-send', f"{title}: {message}"], 
                                     check=True, capture_output=True, timeout=5)
                    except:
                        pass
        except Exception:
            pass
    
    def play_selected_station(self):
        """Avvia la riproduzione della stazione selezionata"""
        if not self.stations:
            return
        
        station = self.stations[self.selected_station_index]
        self.stop()
        
        self.playing_station_index = self.selected_station_index
        
        try:
            if platform.system() != "Windows" and os.path.exists(self.mpv_socket):
                os.remove(self.mpv_socket)
            
            cmd = [
                'mpv', '--no-video', f'--volume={self.volume}',
                '--quiet', '--no-terminal', '--cache=yes',
                '--demuxer-max-bytes=1M', '--audio-buffer=0.1',
                f'--input-ipc-server={self.mpv_socket}',
                station.url
            ]
            
            self.mpv_process = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid if platform.system() != "Windows" else None
            )
            
            time.sleep(1)
            
            if self.mpv_process and self.mpv_process.poll() is None:
                self.is_playing = True
                self.is_paused = False
                self.start_time = time.time()
                self.current_song_start_time = time.time()
                self.pause_start_time = None
                self.total_pause_time = 0
                
                # Marca aggiornamenti necessari
                self.need_status_update = True
                self.need_song_update = True
                self.need_stations_update = True
                
                # Avvia monitoraggio
                threading.Thread(target=self.monitor_metadata_continuous, daemon=True).start()
                threading.Thread(target=self.monitor_stream_stats, daemon=True).start()
                
        except Exception:
            self.is_playing = False
            self.playing_station_index = -1
            self.need_status_update = True
    
    def monitor_metadata_continuous(self):
        """Monitora i metadati dello stream"""
        while self.is_playing and self.running and self.playing_station_index >= 0:
            station = self.stations[self.playing_station_index]
            
            try:
                headers = {'Icy-MetaData': '1', 'User-Agent': 'RadioPlayer/1.0'}
                response = requests.get(station.url, headers=headers, stream=True, timeout=3)
                
                if not self.bitrate:
                    icy_bitrate = response.headers.get('icy-br', '')
                    if icy_bitrate:
                        self.bitrate = f"{icy_bitrate} kbps"
                        self.need_song_update = True
                
                metaint = response.headers.get('icy-metaint')
                if metaint:
                    try:
                        metaint = int(metaint)
                        audio_data = response.raw.read(metaint)
                        meta_length_byte = response.raw.read(1)
                        
                        if meta_length_byte:
                            meta_length = ord(meta_length_byte) * 16
                            
                            if meta_length > 0:
                                metadata = response.raw.read(meta_length).decode('utf-8', errors='ignore')
                                title_match = re.search(r"StreamTitle='([^']*)'", metadata)
                                
                                if title_match:
                                    stream_title = title_match.group(1).strip()
                                    
                                    if stream_title and stream_title != self.stream_title:
                                        old_artist = self.current_artist
                                        old_song = self.current_song
                                        
                                        self.stream_title = stream_title
                                        
                                        if ' - ' in stream_title:
                                            parts = stream_title.split(' - ', 1)
                                            new_artist = parts[0].strip()
                                            new_song = parts[1].strip()
                                            
                                            if new_artist != self.current_artist or new_song != self.current_song:
                                                self.current_artist = new_artist
                                                self.current_song = new_song
                                                self.current_song_start_time = time.time()
                                                self.pause_start_time = None
                                                self.total_pause_time = 0
                                                self.need_song_update = True
                                                
                                                if old_artist or old_song:
                                                    threading.Thread(target=self.show_song_popup, 
                                                                   args=(new_artist, new_song), daemon=True).start()
                                        else:
                                            if stream_title != self.current_song:
                                                old_song_for_popup = self.current_song
                                                self.current_artist = ""
                                                self.current_song = stream_title
                                                self.current_song_start_time = time.time()
                                                self.pause_start_time = None
                                                self.total_pause_time = 0
                                                self.need_song_update = True
                                                
                                                if old_song_for_popup:
                                                    threading.Thread(target=self.show_song_popup, 
                                                                   args=("", stream_title), daemon=True).start()
                    except Exception:
                        pass
                
                response.close()
            except Exception:
                pass
            
            time.sleep(2)
    
    def monitor_stream_stats(self):
        """Monitora le statistiche tecniche dello stream"""
        time.sleep(3)
        
        while self.is_playing and self.running and self.playing_station_index >= 0:
            self.update_stream_stats()
            time.sleep(2)
    
    def get_mpv_property(self, property_name):
        """Ottiene una proprietà da MPV tramite IPC"""
        try:
            cmd = {"command": ["get_property", property_name]}
            message = json.dumps(cmd) + "\n"
            
            if platform.system() == "Windows":
                try:
                    import win32file
                    handle = win32file.CreateFile(
                        self.mpv_socket, win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                        0, None, win32file.OPEN_EXISTING, 0, None
                    )
                    win32file.WriteFile(handle, message.encode('utf-8'))
                    result, data = win32file.ReadFile(handle, 1024)
                    win32file.CloseHandle(handle)
                    
                    if data:
                        response = json.loads(data.decode('utf-8').strip())
                        if response.get("error") == "success":
                            return response.get("data")
                except ImportError:
                    return None
            else:
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
        
        changed = False
        
        # Bitrate
        bitrate = self.get_mpv_property("audio-bitrate")
        if bitrate:
            new_bitrate = f"{int(bitrate/1000)} kbps"
            if new_bitrate != self.audio_bitrate:
                self.audio_bitrate = new_bitrate
                changed = True
        
        # Codec
        codec = self.get_mpv_property("audio-codec-name")
        if codec:
            new_codec = codec.upper()
            if new_codec != self.audio_codec:
                self.audio_codec = new_codec
                changed = True
        
        # Cache duration (non causa refresh immediato)
        cache_duration = self.get_mpv_property("demuxer-cache-duration")
        if cache_duration:
            self.cache_duration = f"{cache_duration:.1f}s"
        
        # Buffer status
        old_buffer = self.buffer_status
        buffering = self.get_mpv_property("paused-for-cache")
        if buffering:
            self.buffer_status = "BUFFERING"
        else:
            cache_percent = self.get_mpv_property("cache-buffering-state")
            if cache_percent is not None:
                self.buffer_status = f"{cache_percent}%"
            else:
                self.buffer_status = "OK"
        
        # Solo BUFFERING forza aggiornamento immediato
        if old_buffer != "BUFFERING" and self.buffer_status == "BUFFERING":
            changed = True
        
        if changed:
            self.need_song_update = True
    
    def send_mpv_command(self, command, *args):
        """Invia comando a MPV tramite IPC"""
        try:
            cmd = {"command": [command] + list(args)}
            message = json.dumps(cmd) + "\n"
            
            if platform.system() == "Windows":
                try:
                    import win32file
                    handle = win32file.CreateFile(
                        self.mpv_socket, win32file.GENERIC_WRITE,
                        0, None, win32file.OPEN_EXISTING, 0, None
                    )
                    win32file.WriteFile(handle, message.encode('utf-8'))
                    win32file.CloseHandle(handle)
                    return True
                except ImportError:
                    return False
            else:
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
                        if platform.system() != "Windows":
                            os.killpg(os.getpgid(self.mpv_process.pid), signal.SIGSTOP)
                        self.is_paused = True
                        self.need_status_update = True
                        self.need_stations_update = True
    
    def stop(self):
        """Ferma la riproduzione"""
        if self.mpv_process:
            try:
                if platform.system() == "Windows":
                    self.mpv_process.terminate()
                    self.mpv_process.wait(timeout=2)
                else:
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
        
        if platform.system() == "Linux" and os.path.exists(self.mpv_socket):
            try:
                os.remove(self.mpv_socket)
            except:
                pass
        
        # Reset stato
        self.is_playing = False
        self.is_paused = False
        self.current_song = ""
        self.current_artist = ""
        self.stream_title = ""
        self.bitrate = ""
        self.start_time = None
        self.playing_station_index = -1
        self.audio_bitrate = ""
        self.buffer_status = ""
        self.audio_codec = ""
        self.cache_duration = ""
        self.current_song_start_time = None
        self.pause_start_time = None
        self.total_pause_time = 0
        
        # Marca aggiornamenti necessari
        self.need_status_update = True
        self.need_song_update = True
        self.need_stations_update = True
    
    def change_selection(self, direction):
        """Cambia selezione"""
        if not self.stations:
            return
        self.selected_station_index = (self.selected_station_index + direction) % len(self.stations)
        self.need_stations_update = True
    
    def select_by_number(self, number):
        """Seleziona stazione per numero"""
        if not self.stations:
            return
        if 1 <= number <= len(self.stations):
            self.selected_station_index = number - 1
            self.need_stations_update = True
    
    def change_volume(self, delta):
        """Cambia il volume"""
        self.volume = max(0, min(100, self.volume + delta))
        self.need_timer_update = True  # Il volume è mostrato nella riga timer
        
        if self.is_playing and self.mpv_process and self.mpv_process.poll() is None:
            time.sleep(0.1)
            self.send_mpv_command("set_property", "volume", self.volume)
    
    def toggle_mute(self):
        """Attiva/disattiva il muto"""
        self.is_muted = not self.is_muted
        self.need_timer_update = True  # Il muto è mostrato nella riga timer
        
        if self.is_playing and self.mpv_process and self.mpv_process.poll() is None:
            success = self.send_mpv_command("set_property", "mute", self.is_muted)
            
            if not success and platform.system() != "Windows":
                try:
                    if self.is_muted:
                        os.killpg(os.getpgid(self.mpv_process.pid), signal.SIGSTOP)
                    else:
                        os.killpg(os.getpgid(self.mpv_process.pid), signal.SIGCONT)
                except:
                    pass
    
    def handle_input(self):
        """Gestisce l'input da tastiera"""
        while self.running:
            char = self.get_char()
            
            if char:
                if self.number_input_mode:
                    if char.isdigit():
                        self.number_buffer += char
                        self.need_input_update = True
                    elif char == '\r' or char == '\n':
                        if self.number_buffer:
                            try:
                                number = int(self.number_buffer)
                                self.select_by_number(number)
                            except:
                                pass
                        self.number_input_mode = False
                        self.number_buffer = ""
                        self.need_input_update = True
                    elif char == 'ESC':
                        self.number_input_mode = False
                        self.number_buffer = ""
                        self.need_input_update = True
                    continue
                
                if char.lower() == 'q':
                    self.running = False
                elif char.lower() == 'p' or char == ' ' or char == '\r' or char == '\n':
                    self.toggle_play_pause()
                elif char.lower() == 'm':
                    self.toggle_mute()
                elif char == '+' or char == '=':
                    self.change_volume(5)
                elif char == '-' or char == '_':
                    self.change_volume(-5)
                elif char == 'UP':
                    self.change_selection(-1)
                elif char == 'DOWN':
                    self.change_selection(1)
                elif char.lower() == 't':
                    self.show_song_popups = not self.show_song_popups
                    self.need_timer_update = True
                    # Mostra messaggio temporaneo
                    temp_line = self.NUMBER_INPUT_LINE - 1
                    if self.show_song_popups:
                        self.update_line(temp_line, "🔔 Notifiche cambio canzone ATTIVATE")
                    else:
                        self.update_line(temp_line, "🔕 Notifiche cambio canzone DISATTIVATE")
                    threading.Timer(2.0, lambda: self.update_line(temp_line, "")).start()
                elif char.isdigit():
                    self.number_input_mode = True
                    self.number_buffer = char
                    self.need_input_update = True
            
            time.sleep(0.05)
    
    def run(self, m3u_file=None):
        """Avvia il player con interfaccia a zero lampeggiamento"""
        try:
            self.setup_terminal()
            
            if m3u_file:
                if not self.load_m3u_file(m3u_file):
                    return
            else:
                m3u_files = [f for f in os.listdir('.') if f.endswith('.m3u')]
                if m3u_files:
                    if not self.load_m3u_file(m3u_files[0]):
                        return
            
            # Prima visualizzazione completa
            self.need_full_redraw = True
            self.display_interface()
            
            # Avvia thread input
            threading.Thread(target=self.handle_input, daemon=True).start()
            
            # Loop principale ottimizzato - aggiorna solo timer ogni secondo
            last_timer_update = 0
            
            while self.running:
                current_time = time.time()
                
                # Aggiorna timer ogni secondo
                if current_time - last_timer_update >= 1.0:
                    self.need_timer_update = True
                    last_timer_update = current_time
                
                # In riproduzione, aggiorna anche info brano ogni secondo (per il tempo)
                if self.is_playing and current_time - last_timer_update < 0.1:  # Appena aggiornato il timer
                    self.need_song_update = True
                
                # Esegui tutti gli aggiornamenti necessari
                self.display_interface()
                
                # Sleep breve per responsività input
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()
            self.restore_terminal()
            self.clear_screen()
            print("👋 Arrivederci!")

def main():
    """Funzione principale"""
    print("Radio Player M3U v2.0 - ZERO LAMPEGGIAMENTO")
    print("Copyright (C) 2025 Andres Zanzani <azanzani@gmail.com>")
    print("Aggiornamento parziale con ANSI escape sequences")
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
        print("Suggerimento: Assicurati che MPV sia installato")

if __name__ == "__main__":
    main()
