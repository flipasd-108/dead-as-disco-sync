# /// script
# requires-python = ">=3.11,<3.12"
# # pinned to the tested set; yt-dlp stays fresh because YouTube keeps breaking old versions
# dependencies = [
#   "beat-this==1.1.0", "torch==2.14.1", "torchaudio==2.11.0", "einops==0.8.2", "rotary-embedding-torch==0.9.1",
#   "soxr==1.1.0", "numpy==2.4.6", "scipy==1.17.1", "soundfile==0.14.0", "imageio-ffmpeg==0.6.0",
#   "pytsmod==0.3.8", "yt-dlp[default,deno]",
# ]
# ///
"""Dead as Disco sync: YouTube link or audio file -> WAV + BPM / Beat Offset / Start Time.

Run:  uv run disco_sync.py "https://youtu.be/..."   (or a local file path)
Import the WAV it writes into the game: the offset is measured on exactly that file.
"""
import hashlib, json, locale, os, random, shutil, subprocess, sys, time
from pathlib import Path

import numpy as np
import soundfile as sf
import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
RU = (locale.getlocale()[0] or "").lower().startswith("ru")  # the game's language follows the system's
AUTO_HINT_RU = ("Дальше в игре открой песню и нажми «Автоматическое определение»: трек уже начинается на доле, и на нём "
                "игра сама точно ставит темп и смещение. Числа выше нужны, только если она промахнулась.")
AUTO_HINT_EN = ("Then open the song in the game and press Auto-detect: the track already starts on a beat, so the game's "
                "own detection sets the tempo and offset right. The numbers above are only for when it misses.")
MEDIA_TYPES = "*.mp3 *.wav *.flac *.ogg *.m4a *.opus *.aac *.wma *.aiff *.mp4 *.mkv *.webm *.mov"
GUI_HELP_RU = """Подходит ссылка на YouTube, SoundCloud или VK и любой аудиофайл (MP3, WAV, FLAC, OGG, M4A) или видео (MP4, MKV). Spotify и Яндекс Музыка не подходят.
Готовая песня сама появится в «Моей музыке» после перезапуска игры. Там открой её и нажми «Автоматическое определение».
Если песни нет, добавь в игру WAV из папки с готовыми WAV и потом не перемещай его.
Первый запуск качает около 1 ГБ."""
GUI_HELP_EN = """Takes a YouTube, SoundCloud or VK link, any audio file (MP3, WAV, FLAC, OGG, M4A) or a video (MP4, MKV). Not Spotify.
The song shows up in My Music after a game restart. Open it there and press Auto-detect.
If it isn't there, add the WAV from the finished WAV folder to the game and keep it in place.
The first run downloads about 1 GB."""
GAME_SONGS = Path(os.environ.get("LOCALAPPDATA", "")) / "Pagoda" / "Saved" / "ImportedSongs"  # Dead as Disco's My Music


def add_to_game(r: dict) -> Path | None:
    """Add the song to the game's My Music the way its own import does: a folder with the audio and Meta.json.
    Only creates a new folder, never touches existing songs."""
    sample = next((f for f in GAME_SONGS.glob("*/Audio*") if f.is_file()), None) if GAME_SONGS.is_dir() else None
    if sample is None:  # game not installed here, or no import of its own to copy the audio file layout from
        return None
    name = "".join("_" if c in '<>:"/\\|?*' else c for c in r["wav"].stem).strip(" .")
    folder, n = GAME_SONGS / name, 2
    while folder.exists():
        folder, n = GAME_SONGS / f"{name} ({n})", n + 1
    folder.mkdir()
    audio = folder / ("Audio" + sample.suffix)
    if sample.suffix.lower() in ("", ".wav"):
        shutil.copyfile(r["wav"], audio)
    else:  # the game keeps another format: convert, the WAV already starts on a beat
        subprocess.run([FFMPEG, "-y", "-v", "error", "-i", str(r["wav"]), str(audio)], check=True)
    meta = {
        "version": 1, "uniqueId": random.getrandbits(32), "songName": folder.name, "performedBy": [], "writtenBy": [],
        "seed": random.getrandbits(31), "tempo": round(r["bpm"], 2), "customTempoSections": [],
        "beatOffset": r["offset"], "startSongOffset": r["start"], "endSongOffset": 0, "uEAssetName": folder.name,
        "originalAudioFileHash": hashlib.md5(r["wav"].read_bytes()).hexdigest(),
        "originalAudioFilePath": r["wav"].as_posix(),
        "analyseResult": {"bAnalyseSuccessful": False, "bFoundTempo": False, "bFoundOffset": False, "tempo": 0,
                          "beatOffset": 0, "fitQuality": 0, "errorCode": {"code": 0, "messageKey": "None", "message": ""}},
        "beatTracks": [],
    }
    (folder / "Meta.json").write_text(json.dumps(meta, indent=4, ensure_ascii=False), encoding="utf-8")
    return folder


def tr(ru: str, en: str) -> str:
    return ru if RU else en


def num(x: float, digits: int) -> str:
    s = f"{x:.{digits}f}"
    return s.replace(".", ",") if RU else s  # the Russian UI uses a decimal comma


def fetch_wav(src: str, out_dir: Path) -> Path:
    if src.startswith(("http://", "https://")):
        import yt_dlp
        opts = {
            "format": "bestaudio/best",
            "outtmpl": str(out_dir / "%(title).80s.%(ext)s"),
            "ffmpeg_location": FFMPEG,
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}],
            "noplaylist": True,
            "quiet": True,
            "noprogress": True,
        }
        # YouTube's bot check is per IP: retry, then a signed-in session. Chrome/Edge cookies can't be
        # decrypted on Windows (app-bound encryption), so Firefox or an exported cookies.txt
        cookies_txt = out_dir.parent / "cookies.txt"
        tries = [{"cookiefile": str(cookies_txt)}] if cookies_txt.exists() else []
        tries += [{}, {}, {"cookiesfrombrowser": ("firefox",)}]
        for extra in tries:
            try:
                with yt_dlp.YoutubeDL(opts | extra) as ydl:
                    info = ydl.extract_info(src)
                    return Path(ydl.prepare_filename(info)).with_suffix(".wav")
            except Exception as e:  # bot check or 403 on the media URL, or no Firefox profile for the cookie attempt
                if not any(m in str(e) for m in ("not a bot", "403")) and "cookiesfrombrowser" not in extra:
                    raise
                print(tr("YouTube: проверка на бота, пробую по-другому...", "YouTube bot check, trying another way..."))
                time.sleep(3)
        sys.exit(tr("\nYouTube не пускает (проверка на бота). Варианты:\n"
                    "  1) войти в YouTube в Firefox и запустить снова: программа возьмёт вход оттуда;\n"
                    "  2) в Chrome поставить расширение «Get cookies.txt LOCALLY», на youtube.com нажать Export\n"
                    f"     и положить файл cookies.txt сюда: {cookies_txt.parent}\n"
                    "  3) скачать песню любым способом и перетащить файл на DeadAsDiscoSync.bat.",
                    "\nYouTube blocks the download (bot check). Options:\n"
                    "  1) sign in to YouTube in Firefox and run again: the session is picked up from there;\n"
                    "  2) in Chrome install the 'Get cookies.txt LOCALLY' extension, press Export on youtube.com\n"
                    f"     and put cookies.txt here: {cookies_txt.parent}\n"
                    "  3) get the song any other way and drop the file onto DeadAsDiscoSync.bat."))
    src_path = Path(src)
    wav = out_dir / (src_path.stem + ".wav")
    if src_path.resolve() != wav.resolve():
        subprocess.run([FFMPEG, "-y", "-v", "error", "-i", str(src_path), wav], check=True)
    return wav


def fit_grid(beats: np.ndarray):
    """Least-squares constant grid through beat times. Returns period_s, t0_s, beat indices on the grid."""
    # index each beat by local rounding, so a missed or extra beat doesn't shift the rest
    idx = np.concatenate([[0], np.cumsum(np.round(np.diff(beats) / np.median(np.diff(beats))))])
    keep = np.ones(len(beats), bool)
    for _ in range(3):
        A = np.column_stack([idx[keep], np.ones(keep.sum())])
        (period, t0), *_ = np.linalg.lstsq(A, beats[keep], rcond=None)
        resid = beats - (t0 + idx * period)
        if (np.abs(resid) < 0.05).sum() < 8:
            break
        keep = np.abs(resid) < 0.05
    return period, t0, idx


def smooth_drift(resid: np.ndarray) -> np.ndarray:
    # median over 9 beats: follows the tempo drift, drops the tracker's single wrong or extra beats
    return np.median(np.lib.stride_tricks.sliding_window_view(np.pad(resid, 4, "edge"), 9), 1)


def warp_to_grid(audio: np.ndarray, sr: int, beats: np.ndarray, idx: np.ndarray,
                 period: float, t0: float, target: float) -> np.ndarray:
    """Stretch the audio between beats so every beat lands on one constant grid of `target` seconds."""
    import pytsmod
    _, first = np.unique(idx, return_index=True)  # an extra beat shares its index: keep one
    beats, idx = beats[first], idx[first]
    drift = smooth_drift(beats - (t0 + idx * period))
    src, dst = t0 + idx * period + drift, t0 + idx * target
    ok = (src > 0.05) & (dst > 0.05) & (src < len(audio) / sr - 0.05)
    src, dst = src[ok], dst[ok]
    end = len(audio) - 1
    anchors = np.array([np.r_[0, src * sr, end], np.r_[0, dst * sr, dst[-1] * sr + end - src[-1] * sr]])
    out = pytsmod.hptsm(audio.T, anchors).T  # harmonic/percussive split keeps drum attacks sharp
    return out / max(1.0, np.abs(out).max())  # stretching can overshoot full scale: avoid clipping


def rms_frames(mono: np.ndarray, hop: int) -> np.ndarray:
    return np.sqrt((mono[: len(mono) // hop * hop].reshape(-1, hop) ** 2).mean(1))


def start_time(mono: np.ndarray, sr: int) -> float:
    # first 10 ms frame within -40 dB of the loudest one
    hop = sr // 100
    env = rms_frames(mono, hop)
    return round(int(np.argmax(env > env.max() * 0.01)) * hop / sr, 2)


def attack_t0(mono: np.ndarray, sr: int, period: float, t0: float) -> float:
    # signal-based vote: slide the grid +-40 ms onto the sharpest energy rises (1 ms envelope)
    hop = sr // 1000
    fps = sr / hop
    env = rms_frames(mono, hop)
    flux = np.maximum(0, np.diff(np.log(env + env.max() * 1e-3), prepend=0))
    grid = np.round((t0 % period + np.arange(int(len(env) / fps / period)) * period) * fps).astype(int)
    grid = grid[(grid >= 40) & (grid < len(flux) - 40)]
    shifts = np.arange(-40, 41)
    return t0 + shifts[np.argmax([flux[grid + s].sum() for s in shifts])] / fps


def grid_t0(beats: np.ndarray, period: float) -> float:
    idx = np.round((beats - beats[0]) / period)
    return float(np.median(beats - idx * period))


def align_to_beat(audio: np.ndarray, sr: int, lead: float, period: float, first_sound: float):
    """Cut or pad the start so the file begins exactly on a beat (the developers: "the song is cut so that
    it starts on a beat"), which makes Beat Offset 0. Returns the audio and seconds cut (>0) or padded (<0)."""
    n = round(lead * sr)
    if first_sound >= lead - 0.05:  # silence before the first beat, or only its own attack: cut it
        return audio[n:], n / sr
    pad = round((period - lead) * sr)  # pickup notes before it: pad silence up to the beat before instead
    return np.concatenate([np.zeros((pad,) + audio.shape[1:]), audio]), -pad / sr


GOOD_MS = 20  # players: under ~20 ms off the grid feels right
CHECKPOINTS = ("final0", "final1", "final2")  # three independently trained Beat This! models vote


def analyze(wav: Path, warp: bool = True, period: float | None = None):
    """Beat grid of the file. With warp, an unsteady track also gets a "(sync)" copy warped onto one tempo."""
    from beat_this.inference import Audio2Beats
    audio, sr = sf.read(wav, dtype="float64")
    mono = audio.mean(1) if audio.ndim == 2 else audio
    tracks = [np.asarray(Audio2Beats(checkpoint_path=c, device="cpu", dbn=False)(mono, sr)[0]) for c in CHECKPOINTS]
    bpm_votes = [60 / fit_grid(b)[0] for b in tracks] if period is None else [60 / period]
    period = 60 / float(np.median(bpm_votes))  # a warped file's tempo is known exactly: second pass passes it

    def grid(b: np.ndarray):
        idx = np.round((b - b[0]) / period) if len(bpm_votes) == 1 else fit_grid(b)[2]
        return float(np.median(b - idx * period)), idx

    # 90th percentile of the smoothed drift: a beatless intro or a few tracker slips don't trigger a warp.
    # The cleanest model is the reference: one that jumps to double time in a section would fake a drift
    drifts = [np.percentile(np.abs(smooth_drift(b - (t + i * period))), 90) for b in tracks for t, i in [grid(b)]]
    beats = tracks[int(np.argmin(drifts))]
    t0, idx = grid(beats)
    jitter_ms = float(min(drifts) * 1000)
    bpm = 60 / period
    snapped = abs(bpm - round(bpm)) < 0.03  # produced tracks are usually exactly integer BPM
    fit_period, fit_t0 = period, t0
    if snapped:
        period = 60 / round(bpm)
    # offset: each model's grid, aligned around model 1 (wrap at period), plus the attacks vote. Models sit
    # ~5 ms late on clean clicks (20 ms frames), so the attacks win when they agree within 12 ms;
    # a far attack peak on a dense mix is another instrument, then the models' median wins
    votes = {f"{tr('модель', 'model')} {i + 1}": grid_t0(b, period) for i, b in enumerate(tracks)}
    ref = next(iter(votes.values()))
    votes = {k: ref + (v - ref + period / 2) % period - period / 2 for k, v in votes.items()}
    models = float(np.median(list(votes.values())))
    attacks = tr("атаки", "attacks")
    votes[attacks] = attack_t0(mono, sr, period, models)
    t0 = votes[attacks] if abs(votes[attacks] - models) <= 0.012 else models
    res = dict(wav=wav, bpm=60 / period, snapped=snapped, offset=round((t0 % period) * 1000),
               start=start_time(mono, sr), dur=len(mono) / sr, jitter_ms=jitter_ms, bpm_votes=bpm_votes,
               votes={k: round((v - t0) * 1000) for k, v in votes.items()})
    if warp and jitter_ms > GOOD_MS and not snapped:
        target = 60 / round(bpm, 2)  # the game takes BPM with 2 decimals: make the file match it exactly
        print(tr(f"Темп плавает (~{jitter_ms:.0f} мс), делаю выровненную копию на {num(round(bpm, 2), 2)}...",
                 f"Tempo drifts (~{jitter_ms:.0f} ms), making a copy warped to {num(round(bpm, 2), 2)}..."))
        sync = wav.with_name(wav.stem + " (sync).wav")
        sf.write(sync, warp_to_grid(audio, sr, beats, idx, fit_period, fit_t0, target), sr, subtype="PCM_16")
        res["sync"] = analyze(sync, warp=False, period=target)
    aligned, trim = align_to_beat(audio, sr, t0 % period, period, res["start"])
    sf.write(wav, aligned, sr, subtype="PCM_16")
    res |= dict(offset=0, start=0.0, dur=len(aligned) / sr, trim=trim)
    return res


def _selftest():
    rng = np.random.default_rng(0)
    period, t0 = 60 / 127.6, 0.1234
    beats = t0 + np.arange(380) * period
    beats = np.delete(beats, [50, 51, 200])                 # missed beats
    beats = np.round(beats / 0.02) * 0.02 + rng.normal(0, 0.003, len(beats))  # 50 fps frames + noise
    p, t, _ = fit_grid(beats)
    assert abs(60 / p - 127.6) < 0.01 and abs(t - t0) < 0.003, (60 / p, t)
    # first beat at 0.7 s after silence: cut; a pickup note at 0.2 s before it: pad up to the beat before (2 s beats)
    x = np.zeros(5000); x[700] = 1
    a, trim = align_to_beat(x, 1000, 0.7, 2.0, 0.68)
    assert a[0] == 1 and trim == 0.7, trim
    x[200] = 1
    a, trim = align_to_beat(x, 1000, 0.7, 2.0, 0.2)
    assert a[2000] == 1 and a[1500] == 1 and trim == -1.3, trim
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        songs = Path(t) / "Pagoda" / "Saved" / "ImportedSongs"
        songs.mkdir(parents=True)
        assert find_game_songs(Path(t)) == songs and find_game_songs(songs.parent.parent) == songs
        assert find_game_songs(songs) == songs and game_status(songs) != game_status(Path(t) / "nope")
    print("selftest ok")


def main():
    args = sys.argv[1:]
    if args[:1] == ["--test"]:
        return _selftest()
    if args[:1] == ["--gui"]:
        return gui(Path(args[1] if len(args) > 1 else "songs"), args[2] if len(args) > 2 else "")
    if not args:
        sys.exit('usage: uv run disco_sync.py "<youtube url | audio file>" [out_dir]\n'
                 '       uv run disco_sync.py --gui [out_dir] [youtube url | audio file]')
    run(args[0], Path(args[1] if len(args) > 1 else "."))


def find_game_songs(d: Path) -> Path:
    """Accept the songs folder itself or any parent of it up to Pagoda."""
    for c in (d, d / "ImportedSongs", d / "Saved" / "ImportedSongs", d / "Pagoda" / "Saved" / "ImportedSongs"):
        if c.is_dir() and c.name == "ImportedSongs":
            return c
    return d


def game_status(d: Path) -> str:
    if not d.is_dir():
        return tr("не найдена, укажи вручную", "not found, pick it")
    n = sum(1 for f in d.glob("*/Audio*") if f.is_file())
    if not n:  # add_to_game copies the audio format from a song the game imported itself
        return tr("пустая: добавь в игре одну песню сама, потом программа сможет добавлять",
                  "empty: import one song in the game first, then the tool can add songs")
    return tr(f"найдена, песен: {n}", f"found, {n} songs")


def gui(out_dir: Path, src: str = ""):
    """A window for people who never used a terminal: paste a link or pick a file, press Start, read the result."""
    global GAME_SONGS
    import queue, threading, traceback, tkinter as tk
    from tkinter import filedialog, scrolledtext
    saved = out_dir / "game_folder.txt"  # a folder picked by hand is remembered next to the WAVs
    try:
        GAME_SONGS = find_game_songs(Path(saved.read_text(encoding="utf-8").strip()))
    except OSError:
        pass
    root = tk.Tk()
    root.title("Dead as Disco Sync")
    root.geometry("900x620")
    tk.Label(root, text=GUI_HELP_RU if RU else GUI_HELP_EN, justify="left", anchor="w", wraplength=870
             ).pack(fill="x", padx=8, pady=(8, 0))

    game = tk.Frame(root)
    game.pack(fill="x", padx=8, pady=(8, 0))
    tk.Label(game, text=tr("Папка песен игры:", "Game songs folder:")).pack(side="left")
    game_var = tk.StringVar(value=str(GAME_SONGS))
    tk.Entry(game, textvariable=game_var, state="readonly").pack(side="left", fill="x", expand=True, padx=6)
    status = tk.Label(game, text=game_status(GAME_SONGS))

    def pick_game():
        global GAME_SONGS
        d = filedialog.askdirectory(initialdir=GAME_SONGS if GAME_SONGS.is_dir() else None)
        if d:
            GAME_SONGS = find_game_songs(Path(d))
            game_var.set(str(GAME_SONGS))
            status.config(text=game_status(GAME_SONGS))
            out_dir.mkdir(parents=True, exist_ok=True)
            saved.write_text(str(GAME_SONGS), encoding="utf-8")

    tk.Button(game, text=tr("Выбрать...", "Pick..."), command=pick_game).pack(side="left")
    status.pack(side="left", padx=6)

    top = tk.Frame(root)
    top.pack(fill="x", padx=8, pady=8)
    tk.Label(top, text=tr("Ссылка или файл:", "Link or file:")).pack(side="left")
    entry = tk.Entry(top)
    entry.pack(side="left", fill="x", expand=True, padx=6)
    entry.insert(0, src)

    def pick():
        f = filedialog.askopenfilename(filetypes=[(tr("Аудио и видео", "Audio and video"), MEDIA_TYPES),
                                                  (tr("Все файлы", "All files"), "*.*")])
        if f:
            entry.delete(0, "end")
            entry.insert(0, f)

    tk.Button(top, text=tr("Файл...", "File..."), command=pick).pack(side="left")
    btn = tk.Button(top, text=tr("Старт", "Start"), width=10)
    btn.pack(side="left", padx=(6, 0))
    bottom = tk.Frame(root)
    bottom.pack(side="bottom", fill="x", padx=8, pady=(0, 8))

    def open_dir(d: Path):
        if d.is_dir():
            os.startfile(d)
        else:
            print(tr(f"\nПапки пока нет: {d}", f"\nNo such folder yet: {d}"))

    tk.Button(bottom, text=tr("Папка с готовыми WAV", "Finished WAV folder"),
              command=lambda: open_dir(out_dir.resolve())).pack(side="left")
    tk.Button(bottom, text=tr("Открыть папку игры", "Open game folder"),
              command=lambda: open_dir(GAME_SONGS)).pack(side="left", padx=6)
    log = scrolledtext.ScrolledText(root, font=("Consolas", 10), wrap="word")
    log.pack(fill="both", expand=True, padx=8, pady=(0, 8))
    log.insert("end", tr("Здесь появится результат.\n", "The result shows up here.\n"))
    q = queue.Queue()  # tk is not thread-safe: the worker only writes here, the window drains it

    class Out:
        def write(self, s):
            q.put(s)

        def flush(self):
            pass

    sys.stdout = sys.stderr = Out()

    def work(s):
        try:
            run(s, out_dir)
            print(tr("\nГотово.", "\nDone."))
        except SystemExit as e:  # fetch_wav exits with a message when YouTube blocks the download
            if e.code:
                print(e.code)
        except Exception as e:
            traceback.print_exc(file=sys.__stderr__)
            print(tr("\nОшибка: ", "\nError: ") + str(e))
        q.put(None)

    def start(_=None):
        s = entry.get().strip().strip('"')
        if s and btn["state"] == "normal":
            btn.config(state="disabled")
            log.delete("1.0", "end")
            threading.Thread(target=work, args=(s,), daemon=True).start()

    def pump():
        while not q.empty():
            s = q.get()
            if s is None:
                btn.config(state="normal")
            else:
                log.insert("end", s)
                log.see("end")
        root.after(100, pump)

    btn.config(command=start)
    entry.bind("<Return>", start)
    pump()
    if src:  # a file dropped onto the .bat starts right away
        root.after(300, start)
    root.mainloop()


def run(src: str, out_dir: Path):
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    wav = fetch_wav(src, out_dir)
    print(tr("Анализ", "Analyzing") + f": {wav.name} ...")
    r = analyze(wav)
    if "sync" in r:
        print(tr(f"\nТемп плавает: удары уходят от ровного темпа на ~{r['jitter_ms']:.0f} мс. Два варианта на выбор:",
                 f"\nTempo drifts: beats stray ~{r['jitter_ms']:.0f} ms from a steady tempo. Two options:"))
        show(r, tr("А: оригинал. Звук не тронут, но удары местами разъезжаются с сеткой",
                   "A: original. Audio untouched, but beats drift off the grid in places"))
        show(r["sync"], tr(f"Б: выровненный. Удары на сетке (~{r['sync']['jitter_ms']:.0f} мс), звук местами "
                           "растянут на 1-2%. Рекомендую", f"B: warped. Beats on the grid (~{r['sync']['jitter_ms']:.0f} ms), "
                           "audio stretched 1-2% in places. Recommended"))
    else:
        show(r, tr("Моя музыка -> вбить в игру", "My Music -> enter in the game"))
    added = [f for f in (add_to_game(v) for v in (r, r.get("sync")) if v) if f]
    if added:
        print(tr("\nДобавлено в игру, вбивать ничего не нужно: перезапусти игру, и песня будет в «Моей музыке».",
                 "\nAdded to the game, nothing to type: restart the game and the song is in My Music."))
        print(tr(AUTO_HINT_RU, AUTO_HINT_EN))
        for f in added:
            print(f"  + {f.name}")
        print(tr("Если в игре не появилось, добавь вручную WAV отсюда и вбей числа выше:",
                 "If it doesn't show up, add the WAV from here by hand and enter the numbers above:"))
        for v in (r, r.get("sync")):
            if v:
                print(f"  {v['wav']}")
        print(tr(f"Папка песен игры: {GAME_SONGS}", f"Game songs folder: {GAME_SONGS}"))
    else:
        shown = r.get("sync", r)["wav"]
        print(tr("\nWAV выделен в Проводнике: добавь в игру его и не перемещай потом.",
                 "\nThe WAV is selected in Explorer: add it to the game and keep it in place."))
        print(tr(AUTO_HINT_RU, AUTO_HINT_EN))
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", str(shown)])
    c = r.get("sync", r)  # cross-check the recommended file
    models = list(c["votes"].values())[:-1]  # the attacks vote is blurry on real mixes: it informs, not alarms
    spread = max(models) - min(models)
    votes = ", ".join(f"{k} {v:+d}" for k, v in c["votes"].items())
    bpms = " / ".join(num(b, 2) for b in r["bpm_votes"])
    print(tr(f"\nСверка: темп по моделям {bpms}; смещение относительно итога: {votes} мс (разброс моделей {spread} мс)",
             f"\nCross-check: BPM per model {bpms}; offset vs result: {votes} ms (model spread {spread} ms)"))
    if spread > GOOD_MS:
        print(tr("  Голоса заметно расходятся: если в игре удары мимо, попробуй смещение ± эти мс.",
                 "  The votes disagree: if hits feel off in the game, try the offset +- these ms."))
    if r.get("sync", {}).get("jitter_ms", 0) > GOOD_MS:
        print(tr(f"\nВНИМАНИЕ: и в выровненном удары гуляют на ~{r['sync']['jitter_ms']:.0f} мс, проверь трек в игре.",
                 f"\nWARNING: beats still wander ~{r['sync']['jitter_ms']:.0f} ms after warping, check it in the game."))


def show(r: dict, title: str):
    bpm_txt = str(round(r["bpm"])) if r["snapped"] else num(r["bpm"], 2)
    print(f"\n  {title}:")
    print(tr("  Файл:                  ", "  File:               ") + r["wav"].name)
    print(tr("  Темп:                  ", "  BPM:                ") + bpm_txt)
    print(tr("  Смещение ритма (мс):   ", "  Beat Offset (ms):   ") + str(r["offset"]))
    print(tr("  Время начала (с):      ", "  Start Time (s):     ") + num(r["start"], 2))
    print(tr("  Время окончания (с):   ", "  End Time (s):       ") + num(r["dur"], 3))
    if r["trim"] > 0:
        print(tr(f"  Подрезка: отрезал {num(r['trim'], 3)} с до первой доли, трек начинается на доле",
                 f"  Trim: cut {num(r['trim'], 3)} s before the first beat, the track starts on the beat"))
    else:
        print(tr(f"  Подрезка: добавил {num(-r['trim'], 3)} с тишины в начало (там затакт), трек начинается на доле",
                 f"  Trim: added {num(-r['trim'], 3)} s of silence (pickup notes), the track starts on the beat"))
    if r["bpm"] < 120:
        print(tr(f"  Игра советует темп 120–200: можно вбить {num(2 * r['bpm'], 2)}, смещение то же",
                 f"  The game suggests 120-200 BPM: you can enter {num(2 * r['bpm'], 2)}, same offset"))

if __name__ == "__main__":
    main()
