```python
#!/usr/bin/env python3
"""
Spotify Synced Lyrics Viewer
Displays synchronized lyrics from LRCLIB based on the currently
playing Spotify track through MPRIS.
"""

import dbus
import requests
import os
import sys
import re
import select
import tty
import termios

C_RESET  = "\033[0m"
C_BOLD   = "\033[1m"
C_GREEN  = "\033[92m"
C_CYAN   = "\033[96m"
C_YELLOW = "\033[93m"
C_MAGENTA= "\033[95m"
C_RED    = "\033[91m"
C_DIM    = "\033[2;37m"

ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

def center_ansi(text, width):
    visible_text = ANSI_ESCAPE.sub('', text)
    visible_len = len(visible_text)

    if visible_len >= width:
        return text

    pad = (width - visible_len) // 2
    return " " * pad + text

def get_current_song():
    try:
        bus = dbus.SessionBus()
        proxy = bus.get_object(
            "org.mpris.MediaPlayer2.spotify",
            "/org/mpris/MediaPlayer2"
        )
        props = dbus.Interface(
            proxy,
            "org.freedesktop.DBus.Properties"
        )

        metadata = props.Get("org.mpris.MediaPlayer2.Player", "Metadata")
        status = props.Get("org.mpris.MediaPlayer2.Player", "PlaybackStatus")
        position = props.Get("org.mpris.MediaPlayer2.Player", "Position")

        title = str(metadata.get("xesam:title", ""))
        artists = metadata.get("xesam:artist", [])
        artist = str(artists[0]) if artists else ""
        album = str(metadata.get("xesam:album", ""))
        length = int(metadata.get("mpris:length", 0))

        return title, artist, album, str(status), int(position), length

    except Exception:
        return None, None, None, None, 0, 0

def get_lyrics(artist, title, album, duration):
    try:
        url = "https://lrclib.net/api/get"
        params = {
            "artist_name": artist,
            "track_name": title,
            "album_name": album,
            "duration": duration
        }

        resp = requests.get(url, params=params, timeout=5)

        if resp.status_code == 200:
            data = resp.json()

            if data.get("syncedLyrics"):
                return parse_lrc(data["syncedLyrics"])

            elif data.get("plainLyrics"):
                return data["plainLyrics"]

        return None

    except Exception:
        return None

def parse_lrc(lrc_string):
    lines = []
    pattern = re.compile(r'\[(\d+):(\d+)(?:\.(\d+))?\](.*)')

    for line in lrc_string.split('\n'):
        match = pattern.match(line)

        if match:
            m, s, ms, text = match.groups()
            time_in_sec = int(m) * 60 + int(s)

            if ms:
                time_in_sec += int(ms) / 1000.0

            lines.append((time_in_sec, text.strip()))

    return lines if lines else None

def fmt_time(microseconds):
    seconds = microseconds // 1_000_000
    m, s = divmod(seconds, 60)

    return f"{m:02d}:{s:02d}"

def clear():
    sys.stdout.write("\033[H\033[J")

def display(artist, title, status, lyrics_data, pos, length, width):
    clear()

    print(center_ansi(f"{C_BOLD}{C_CYAN}{title}{C_RESET}", width))
    print(center_ansi(f"{C_BOLD}{C_YELLOW}{artist}{C_RESET}", width))
    print()

    icon = "▶" if status == "Playing" else "⏸"
    status_str = f"{C_MAGENTA}{icon}  {status}{C_RESET}"
    print(center_ansi(status_str, width))

    if length > 0:
        pct = min(pos / length, 1.0)
        filled = int(pct * 30)

        bar_prog = "█" * filled + "░" * (30 - filled)
        prog_str = (
            f"{C_DIM}{bar_prog}{C_RESET} "
            f"{C_BOLD}{fmt_time(pos)} / {fmt_time(length)}{C_RESET}"
        )

        print(center_ansi(prog_str, width))

    print()

    if not lyrics_data:
        print(center_ansi(
            f"{C_RED}✗ Lyrics not found on LRCLIB{C_RESET}",
            width
        ))
        print(center_ansi(
            f"{C_DIM}{artist} - {title}{C_RESET}",
            width
        ))
        return

    current_pos_sec = pos // 1_000_000

    if isinstance(lyrics_data, str):
        for line in lyrics_data.split("\n"):
            print(center_ansi(line, width))

    elif isinstance(lyrics_data, list):
        current_idx = -1

        for i, (t, _) in enumerate(lyrics_data):
            if t <= current_pos_sec:
                current_idx = i
            else:
                break

        if current_idx != -1:
            start_idx = max(0, current_idx - 3)
            end_idx = min(len(lyrics_data), current_idx + 5)

            for i in range(start_idx, end_idx):
                t, text = lyrics_data[i]

                if not text:
                    text = "♪"

                if i == current_idx:
                    active_str = (
                        f"{C_BOLD}{C_GREEN}► {text}{C_RESET}"
                    )
                    print(center_ansi(active_str, width))
                else:
                    print(center_ansi(
                        f"{C_DIM}{text}{C_RESET}",
                        width
                    ))
        else:
            print(center_ansi(
                f"{C_DIM}♪ (Waiting for lyrics to start...){C_RESET}",
                width
            ))

    print()
    print(center_ansi(
        f"{C_DIM}Press 'q' or Ctrl+C to exit | Real-time Synced{C_RESET}",
        width
    ))

def main():
    last_song = None
    cached_lyrics = None

    sys.stdout.write("\033[?25l")
    sys.stdout.flush()

    old_settings = termios.tcgetattr(sys.stdin)
    tty.setcbreak(sys.stdin.fileno())

    try:
        while True:
            try:
                width = os.get_terminal_size().columns
            except:
                width = 80

            title, artist, album, status, pos, length = get_current_song()

            if title and artist:
                song_key = f"{artist} - {title}"
                duration_sec = length // 1_000_000

                if song_key != last_song:
                    last_song = song_key
                    cached_lyrics = get_lyrics(
                        artist,
                        title,
                        album,
                        duration_sec
                    )

                display(
                    artist,
                    title,
                    status,
                    cached_lyrics,
                    pos,
                    length,
                    width
                )

            else:
                clear()

                print(center_ansi(
                    f"\n{C_YELLOW}⚠  Spotify not detected!{C_RESET}",
                    width
                ))
                print(center_ansi(
                    f"{C_DIM}Make sure Spotify desktop is running.{C_RESET}\n",
                    width
                ))

            i, o, e = select.select([sys.stdin], [], [], 1.0)

            if i:
                key = sys.stdin.read(1)

                if key.lower() == 'q':
                    break

    except KeyboardInterrupt:
        pass

    finally:
        termios.tcsetattr(
            sys.stdin,
            termios.TCSADRAIN,
            old_settings
        )

        sys.stdout.write("\033[?25h")
        sys.stdout.flush()

        clear()
        print(f"{C_GREEN}\n  👋 Goodbye!\n{C_RESET}")

        sys.exit(0)

if __name__ == "__main__":
    main()
```
