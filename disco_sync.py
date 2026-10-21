# /// script
# requires-python = ">=3.11,<3.12"
# # pinned to the tested set; yt-dlp stays fresh because YouTube keeps breaking old versions
# dependencies = [
#   "beat-this==1.1.0", "torch==2.14.1", "torchaudio==2.11.0", "einops==0.8.2", "rotary-embedding-torch==0.9.1",
#   "soxr==1.1.0", "numpy==2.4.6", "scipy==1.17.1", "soundfile==0.14.0", "imageio-ffmpeg==0.6.0",
#   "pytsmod==0.3.8", "sv-ttk==2.6.0", "pillow==11.3.0", "yt-dlp[default,deno]",
# ]
# ///
"""Dead as Disco sync: YouTube link or audio file -> WAV + BPM / Beat Offset / Start Time.

Run:  uv run disco_sync.py "https://youtu.be/..."   (or a local file path)
Import the WAV it writes into the game: the offset is measured on exactly that file.
"""
import hashlib, json, locale, os, random, shutil, subprocess, sys, time, urllib.request
from concurrent.futures import ProcessPoolExecutor
from functools import cache
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
GUI_HELP_RU = ("Готовая песня появится в «Моей музыке» после перезапуска игры: открой её и нажми «Автоматическое "
               "определение». Двойной щелчок по песне открывает её папку, правый щелчок показывает остальные действия.")
GUI_HELP_EN = ("The song shows up in My Music after a game restart: open it and press Auto-detect. "
               "Double-click a song to open its folder, right-click for more.")
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
        print(tr("Скачиваю", "Downloading") + f": {src}")
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
    # harmonic/percussive split keeps drum attacks sharp; it loops in Python, so each channel gets its own process
    chans = audio.T if audio.ndim == 2 else audio[None]
    with ProcessPoolExecutor(len(chans)) as ex:
        out = np.stack([np.ravel(c) for c in ex.map(pytsmod.hptsm, chans, [anchors] * len(chans))], axis=-1)
    out = out if audio.ndim == 2 else out[:, 0]
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


@cache
def beat_model(checkpoint: str):
    """Loaded once per run: the window analyses many songs, and the sync pass reuses them."""
    from beat_this.inference import Audio2Beats
    return Audio2Beats(checkpoint_path=checkpoint, device="cpu", dbn=False)


def analyze(wav: Path, warp: bool = True, period: float | None = None):
    """Beat grid of the file. With warp, an unsteady track also gets a "(sync)" copy warped onto one tempo."""
    audio, sr = sf.read(wav, dtype="float64")
    mono = audio.mean(1) if audio.ndim == 2 else audio
    tracks = [np.asarray(beat_model(c)(mono, sr)[0]) for c in CHECKPOINTS]
    tracks = [b for b in tracks if len(b) >= 8]  # a model can find no beat at all in ambient, speech or silence
    if not tracks:
        sys.exit(tr("В треке не нашлось долей: нужна песня с ритмом.", "No beats found: the track needs a rhythm."))
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
        return tr("пустая: сначала добавь одну песню через игру, потом программа сможет добавлять",
                  "empty: import one song in the game first, then the tool can add songs")
    return tr(f"найдена, песен: {n}", f"found, {n} songs")


def tempo_txt(v: dict) -> str:
    return str(round(v["bpm"])) if v["snapped"] else num(v["bpm"], 2)


WALLPAPER_URL = "https://images4.alphacoders.com/140/thumb-1920-1403387.png"  # Dead as Disco key art, alphacoders


def backdrop(root, out_dir: Path):
    """A canvas filling the window with the game's art on it, darkened so the controls on top stay readable.
    Returns (canvas, has_art). The art isn't in the repo: a background.* next to the WAVs wins, else it is
    fetched once into that folder; offline the canvas is plain."""
    import tkinter as tk
    from tkinter import ttk
    from PIL import Image, ImageEnhance, ImageTk
    cv = tk.Canvas(root, highlightthickness=0, background=ttk.Style().lookup(".", "background") or "#1c1c1c")
    cv.pack(fill="both", expand=True)
    art = next(iter(sorted(out_dir.glob("background.*"))), None)
    try:
        if art is None:
            req = urllib.request.Request(WALLPAPER_URL, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=5).read()
            out_dir.mkdir(parents=True, exist_ok=True)
            art = out_dir / "background.png"
            art.write_bytes(data)
        img = Image.open(art).convert("RGB")
    except OSError:  # offline, the site moved the file, or not an image
        return cv, False
    img.thumbnail((1920, 1920))
    img = ImageEnhance.Brightness(img).enhance(0.45)
    bg = cv.create_image(0, 0, anchor="nw")
    size = [0, 0]

    def fit(e):
        if [e.width, e.height] == size:
            return
        size[:] = w, h = max(e.width, 1), max(e.height, 1)
        s = max(w / img.width, h / img.height)  # cover the whole window, crop what overflows
        im = img.resize((round(img.width * s), round(img.height * s)), Image.BILINEAR)
        x, y = (im.width - w) // 2, (im.height - h) // 4  # keep more of the top, where the faces are
        cv.photo = ImageTk.PhotoImage(im.crop((x, y, x + w, y + h)))
        cv.itemconfigure(bg, image=cv.photo)
        cv.tag_lower(bg)

    cv.bind("<Configure>", fit, add="+")
    return cv, True


def gui(out_dir: Path, src: str = ""):
    """Window: a link or file on top, songs in a table; double-click a song to open its folder."""
    global GAME_SONGS
    import ctypes, queue, threading, traceback, tkinter as tk, winreg
    from tkinter import filedialog, messagebox, ttk
    import sv_ttk
    out_dir = out_dir.resolve()
    saved, hist_file = out_dir / "game_folder.txt", out_dir / "history.json"  # both live next to the WAVs
    try:
        GAME_SONGS = find_game_songs(Path(saved.read_text(encoding="utf-8").strip()))
    except OSError:
        pass
    try:
        history = json.loads(hist_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        history = []
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # sharp text on scaled screens instead of a blurry bitmap
    except (AttributeError, OSError):
        pass
    root = tk.Tk()
    root.title("Dead as Disco Sync")
    root.geometry("880x660")
    root.minsize(640, 400)
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        light = winreg.QueryValueEx(key, "AppsUseLightTheme")[0]
    except OSError:
        light = 1
    sv_ttk.set_theme("light" if light else "dark")  # follow the Windows setting
    if not light:  # dark title bar to match (Windows 10 2004+ / 11), once the window is on screen
        root.bind("<Map>", lambda e: e.widget is root and ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.windll.user32.GetParent(root.winfo_id()), 20, ctypes.byref(ctypes.c_int(1)), 4), add="+")
    cv, art = backdrop(root, out_dir)
    # labels are canvas text, so the art shows around the controls; light text on the darkened art
    fg, dim = ("#ffffff", "#d6d6d6") if art or not light else ("#1a1a1a", "#5c5c5c")
    font = ("Segoe UI", 10)

    def text(t, color=fg):
        return cv.create_text(0, 0, anchor="nw", text=t, fill=color, font=font)

    t_game_title = text(tr("1. Папка «Моей музыки» в сохранениях игры", "1. My Music folder in the game's saves"))
    game_path = ttk.Entry(cv, state="readonly")  # readonly: the whole path is visible and copyable
    game_btn = ttk.Button(cv, text=tr("Указать", "Pick"))
    t_game = text("", dim)
    t_song_title = text(tr("2. Ссылка на YouTube, SoundCloud, VK или аудио- или видеофайл",
                           "2. A YouTube, SoundCloud or VK link, or an audio or video file"))
    entry = ttk.Entry(cv)
    if src:
        entry.insert(0, src)

    def pick():
        f = filedialog.askopenfilename(filetypes=[(tr("Аудио и видео", "Audio and video"), MEDIA_TYPES),
                                                  (tr("Все файлы", "All files"), "*.*")])
        if f:
            entry.delete(0, "end")
            entry.insert(0, f)

    browse = ttk.Button(cv, text=tr("Обзор", "Browse"), command=pick)
    start = ttk.Button(cv, text=tr("Старт", "Start"), style="Accent.TButton", command=lambda: go())
    t_help = text(GUI_HELP_RU if RU else GUI_HELP_EN, dim)
    table = ttk.Frame(cv)
    wins = {w: cv.create_window(0, 0, anchor="nw", window=w) for w in (game_path, game_btn, entry, browse, start, table)}

    def relayout(_=None):
        """Stack the rows top-down; a row is a stretching entry plus buttons on its right."""
        W, H = cv.winfo_width(), cv.winfo_height()
        x0, width, y = 24, max(cv.winfo_width() - 48, 200), 20

        def put_text(item, gap):
            nonlocal y
            cv.coords(item, x0, y)
            cv.itemconfigure(item, width=width)
            x1, y1, x2, y2 = cv.bbox(item)
            y += (y2 - y1) + gap

        def put_row(field, buttons, gap):
            nonlocal y
            h = max(w.winfo_reqheight() for w in (field, *buttons))
            x = x0 + width
            for b in reversed(buttons):
                x -= b.winfo_reqwidth()
                cv.coords(wins[b], x, y)
                cv.itemconfigure(wins[b], height=h)
                x -= 8
            cv.coords(wins[field], x0, y)
            cv.itemconfigure(wins[field], width=x - x0, height=h)
            y += h + gap

        put_text(t_game_title, 4)
        put_row(game_path, [game_btn], 4)
        put_text(t_game, 16)
        put_text(t_song_title, 4)
        put_row(entry, [browse, start], 6)
        put_text(t_help, 12)
        cv.coords(wins[table], x0, y)
        cv.itemconfigure(wins[table], width=width, height=max(H - y - 24, 80))

    cv.bind("<Configure>", relayout, add="+")

    def show_game():
        game_path.configure(state="normal")
        game_path.delete(0, "end")
        game_path.insert(0, str(GAME_SONGS))
        game_path.configure(state="readonly")
        status = game_status(GAME_SONGS)
        if not GAME_SONGS.is_dir():
            status += tr(r". Обычно это %LOCALAPPDATA%\Pagoda\Saved\ImportedSongs",
                         r". Usually %LOCALAPPDATA%\Pagoda\Saved\ImportedSongs")
        cv.itemconfigure(t_game, text=status[0].upper() + status[1:])
        relayout()

    def pick_game():
        global GAME_SONGS
        d = filedialog.askdirectory(initialdir=GAME_SONGS if GAME_SONGS.is_dir() else None, title=tr(
            r"Папка ImportedSongs, обычно %LOCALAPPDATA%\Pagoda\Saved\ImportedSongs",
            r"The ImportedSongs folder, usually %LOCALAPPDATA%\Pagoda\Saved\ImportedSongs"))
        if d:
            GAME_SONGS = find_game_songs(Path(d))
            out_dir.mkdir(parents=True, exist_ok=True)
            saved.write_text(str(GAME_SONGS), encoding="utf-8")
            show_game()

    game_btn.configure(command=pick_game)
    show_game()

    cols = ("name", "tempo", "state")
    tree = ttk.Treeview(table, columns=cols, show="headings", selectmode="extended")
    for c, t, w in zip(cols, (tr("Песня", "Song"), tr("Темп", "BPM"), tr("Статус", "Status")), (380, 80, 260)):
        tree.heading(c, text=t, anchor="w")
        tree.column(c, width=w, stretch=c == "name")
    scroll = ttk.Scrollbar(table, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    tree.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")
    rows = {}  # tree item id -> (song entry, variant or None)

    def row_list(h):
        """One row per variant; a queued, running or failed song is one row."""
        if h.get("busy"):
            step = h.get("step", "")
            if "t0" in h:  # a ticking counter shows a long analysis is alive
                step = f"{step[:44]} · {time.time() - h['t0']:.0f} " + tr("с", "s")
            return [((h["name"], "", step), None)]
        if h.get("error"):
            return [((h["name"], "", tr("Ошибка, дважды щёлкни", "Error, double-click")), None)]
        vs, out = h["variants"], []
        for i, v in enumerate(vs):
            state = tr("В игре", "In game") if v["game"] else tr("WAV готов", "WAV ready")
            if len(vs) > 1:
                state += tr(", выровненный, рекомендую", ", warped, recommended") if i else tr(", оригинал", ", original")
            out.append(((Path(v["wav"]).stem, tempo_txt(v), state), v))
        return out

    def iids_of(h):
        return [i for i, (hh, _) in rows.items() if hh is h]

    def add_rows(h, at=0):
        iids = []
        for i, (values, v) in enumerate(row_list(h)):
            iid = tree.insert("", at + i if at != "end" else "end", values=values)
            rows[iid] = (h, v)
            iids.append(iid)
        return iids

    def redraw(h):
        """Replace the song's rows in place: its variants may have changed."""
        old = iids_of(h)
        at = tree.index(old[0]) if old else 0
        for iid in old:
            rows.pop(iid)
            tree.delete(iid)
        return add_rows(h, at)

    def selected():
        return [rows[i] for i in tree.selection()]

    def open_game(v):
        if v and v["game"] and Path(v["game"]).is_dir():
            os.startfile(v["game"])

    def show_wav(v):
        if v and Path(v["wav"]).exists():
            subprocess.Popen(["explorer", "/select,", v["wav"]])

    def open_row(_=None):
        if not tree.selection():
            return
        h, v = selected()[0]
        if h.get("error"):
            messagebox.showerror(h["name"], h["error"])
        elif v and v["game"] and Path(v["game"]).is_dir():
            open_game(v)
        else:
            show_wav(v)

    def save_history():
        out_dir.mkdir(parents=True, exist_ok=True)
        hist_file.write_text(json.dumps(history[:200], ensure_ascii=False, indent=1), encoding="utf-8")

    def delete_rows(_=None):
        items = [(h, v) for h, v in selected() if h is not current.get("h")]  # the running song can't go
        if not items:
            return
        names = "\n".join(f"  {tree.set(i, 'name')}" for i in tree.selection() if rows[i][0] is not current.get("h"))
        if not messagebox.askyesno(tr("Удалить", "Delete"), tr(
                f"Удалить?\n{names}\n\nПесни пропадут из списка, из «Моей музыки» игры и с диска.",
                f"Delete?\n{names}\n\nThe songs leave this list, the game's My Music and the disk."), icon="warning"):
            return
        failed, touched = [], []
        for h, v in items:
            touched.append(h)
            if h in jobs:  # still waiting: just drop it
                jobs.remove(h)
            elif v:
                try:
                    Path(v["wav"]).unlink(missing_ok=True)
                    g = Path(v["game"]) if v["game"] else None
                    # only a song folder of the game: ImportedSongs\<song>\ with its Meta.json
                    if g and g.parent.name == "ImportedSongs" and (g / "Meta.json").is_file():
                        shutil.rmtree(g)
                except OSError as e:  # the game may hold the file open while it runs
                    failed.append(f"{Path(v['wav']).stem}: {e}")
                    continue
                h["variants"].remove(v)
            if h in history and not h.get("variants"):
                history.remove(h)
            for iid in [i for i, (hh, vv) in rows.items() if hh is h and vv is v]:
                rows.pop(iid)
                tree.delete(iid)
        for h in {id(h): h for h in touched}.values():
            if iids_of(h):  # one of two variants left: its status loses the "original / warped" note
                redraw(h)
        save_history()
        show_game()
        if failed:
            messagebox.showerror(tr("Не всё удалилось", "Not everything was deleted"), tr(
                "Закрой игру и попробуй снова.\n\n", "Close the game and try again.\n\n") + "\n".join(failed))

    menu = tk.Menu(root, tearoff=0)
    menu.add_command(label=tr("Открыть папку в игре", "Open folder in game"), command=lambda: open_game(selected()[0][1]))
    menu.add_command(label=tr("Показать WAV", "Show WAV"), command=lambda: show_wav(selected()[0][1]))
    menu.add_command(label=tr("Показать ошибку", "Show error"), command=open_row)
    menu.add_separator()
    menu.add_command(label=tr("Удалить", "Delete"), accelerator="Del", command=delete_rows)

    def popup(e):
        iid = tree.identify_row(e.y)
        if not iid:
            return
        if iid not in tree.selection():
            tree.selection_set(iid)
        h, v = selected()[0]
        ok = {0: bool(v and v["game"] and Path(v["game"]).is_dir()), 1: bool(v and Path(v["wav"]).exists()),
              2: bool(h.get("error")), 4: h is not current.get("h")}
        for i, on in ok.items():
            menu.entryconfigure(i, state="normal" if on else "disabled")
        menu.tk_popup(e.x_root, e.y_root)

    tree.bind("<Double-1>", open_row)
    tree.bind("<Return>", open_row)
    tree.bind("<Delete>", delete_rows)
    tree.bind("<Button-3>", popup)
    for h in history:
        add_rows(h, "end")

    # the analysis runs in a thread; tk is not thread-safe, so the thread only writes to the queue
    q = queue.Queue()
    current = {}
    jobs = []  # songs waiting their turn, oldest first

    class Out:
        def write(self, s):
            q.put(("log", s))

        def flush(self):
            pass

    sys.stdout = sys.stderr = Out()

    def work(s):
        try:
            q.put(("done",) + run(s, out_dir, reveal_wav=False))
        except SystemExit as e:  # fetch_wav exits with a message when YouTube blocks the download
            q.put(("error", str(e.code or "")))
        except Exception as e:
            traceback.print_exc(file=sys.__stderr__)
            q.put(("error", str(e)))

    def go(_=None):
        s = entry.get().strip().strip('"')
        if not s:
            return
        if not s.startswith(("http://", "https://")) and not Path(s).is_file():
            messagebox.showerror("Dead as Disco Sync", tr(f"Файл не найден:\n{s}", f"File not found:\n{s}"))
            return
        h = {"name": s if s.startswith("http") else Path(s).stem, "src": s, "busy": True,
             "step": tr("В очереди", "Queued"), "log": ""}
        add_rows(h)
        entry.delete(0, "end")  # ready for the next link while this one waits or runs
        jobs.append(h)
        if not current:
            next_job()

    def next_job():
        if not jobs:
            return
        h = jobs.pop(0)
        h["step"], h["t0"] = tr("Начинаю", "Starting"), time.time()
        current["h"] = h
        redraw(h)
        threading.Thread(target=work, args=(h["src"],), daemon=True).start()

    def finish(h):
        for k in ("busy", "step", "t0"):
            h.pop(k, None)
        history.insert(0, h)
        save_history()
        redraw(h)
        current.clear()
        show_game()
        if h.get("error"):
            messagebox.showerror(h["name"], h["error"])
        next_job()

    def pump():
        while not q.empty():
            msg = q.get()
            h = current.get("h")
            if h is None:
                continue
            if msg[0] == "log":
                h["log"] += msg[1]
                h["step"] = next((ln.strip() for ln in reversed(h["log"].splitlines()) if ln.strip()), h["step"])
            elif msg[0] == "done":
                r, games = msg[1], msg[2]
                vs = [r] + ([r["sync"]] if "sync" in r else [])
                h["name"] = r["wav"].stem
                h["variants"] = [dict(wav=str(v["wav"]), bpm=float(v["bpm"]), snapped=bool(v["snapped"]),
                                      offset=int(v["offset"]), start=float(v["start"]), dur=float(v["dur"]),
                                      trim=float(v["trim"]), jitter=float(v["jitter_ms"]), game=str(g or ""))
                                 for v, g in zip(vs, games)]
                finish(h)
            else:
                h["error"] = (msg[1] or tr("Не получилось", "Failed")) + "\n\n" + h["log"].strip()[-1500:]
                finish(h)
        h = current.get("h")
        if h and iids_of(h):  # tick the counter
            tree.item(iids_of(h)[0], values=row_list(h)[0][0])
        root.after(200, pump)

    entry.bind("<Return>", go)
    entry.focus_set()
    # load the models while the user pastes a link; a song started earlier just waits on the same cache
    threading.Thread(target=lambda: [beat_model(c) for c in CHECKPOINTS], daemon=True).start()
    pump()
    if src:  # a file dropped onto the .bat starts right away
        root.after(300, go)
    root.mainloop()


def run(src: str, out_dir: Path, reveal_wav: bool = True):
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
    games = [add_to_game(v) for v in (r, r.get("sync")) if v]
    added = [f for f in games if f]
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
        if reveal_wav and sys.platform == "win32":  # the window has its own "Show WAV" button
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
    return r, games


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
