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
import locale, subprocess, sys, time
from pathlib import Path

import numpy as np
import soundfile as sf
import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
RU = (locale.getlocale()[0] or "").lower().startswith("ru")  # the game's language follows the system's


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
            except Exception as e:  # bot check, or no Firefox profile for the cookie attempt
                if "not a bot" not in str(e) and "cookiesfrombrowser" not in extra:
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


def warp_to_grid(audio: np.ndarray, sr: int, beats: np.ndarray, idx: np.ndarray,
                 period: float, t0: float, target: float) -> np.ndarray:
    """Stretch the audio between beats so every beat lands on one constant grid of `target` seconds."""
    import pytsmod
    _, first = np.unique(idx, return_index=True)  # an extra beat shares its index: keep one
    beats, idx = beats[first], idx[first]
    # follow the drummer's tempo, not the tracker's per-beat noise: median over 9 beats
    drift = np.median(np.lib.stride_tricks.sliding_window_view(np.pad(beats - (t0 + idx * period), 4, "edge"), 9), 1)
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


CHECKPOINTS = ("final0", "final1", "final2")  # three independently trained Beat This! models vote


def analyze(wav: Path, warp: bool = True, period: float | None = None):
    """Beat grid of the file. With warp, an unsteady track is rewritten in place onto a constant tempo."""
    from beat_this.inference import Audio2Beats
    audio, sr = sf.read(wav, dtype="float64")
    mono = audio.mean(1) if audio.ndim == 2 else audio
    tracks = [np.asarray(Audio2Beats(checkpoint_path=c, device="cpu", dbn=False)(mono, sr)[0]) for c in CHECKPOINTS]
    beats = tracks[0]
    if period is None:
        period, t0, idx = fit_grid(beats)
        bpm_votes = [60 / fit_grid(b)[0] for b in tracks]
        period = 60 / float(np.median(bpm_votes))
    else:  # second pass over a warped file: its tempo is known exactly
        idx = np.round((beats - beats[0]) / period)
        t0 = np.median(beats - idx * period)
        bpm_votes = [60 / period]
    jitter_ms = float(np.sqrt(np.mean((beats - (t0 + idx * period)) ** 2)) * 1000)
    bpm = 60 / period
    snapped = abs(bpm - round(bpm)) < 0.03  # produced tracks are usually exactly integer BPM
    if warp and jitter_ms > 15 and not snapped:
        target = 60 / round(bpm, 2)  # the game takes BPM with 2 decimals: make the file match it exactly
        print(tr(f"Темп плавает (~{jitter_ms:.0f} мс), выравниваю трек на {num(round(bpm, 2), 2)}...",
                 f"Tempo drifts (~{jitter_ms:.0f} ms), warping the track to {num(round(bpm, 2), 2)}..."))
        sf.write(wav, warp_to_grid(audio, sr, beats, idx, period, t0, target), sr, subtype="PCM_16")
        return analyze(wav, warp=False, period=target) | {"warped_from_ms": jitter_ms, "bpm_votes": bpm_votes}
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
    return dict(bpm=60 / period, snapped=snapped, offset=round((t0 % period) * 1000), start=start_time(mono, sr),
                dur=len(mono) / sr, jitter_ms=jitter_ms, bpm_votes=bpm_votes,
                votes={k: round((v - t0) * 1000) for k, v in votes.items()})


def _selftest():
    rng = np.random.default_rng(0)
    period, t0 = 60 / 127.6, 0.1234
    beats = t0 + np.arange(380) * period
    beats = np.delete(beats, [50, 51, 200])                 # missed beats
    beats = np.round(beats / 0.02) * 0.02 + rng.normal(0, 0.003, len(beats))  # 50 fps frames + noise
    p, t, _ = fit_grid(beats)
    assert abs(60 / p - 127.6) < 0.01 and abs(t - t0) < 0.003, (60 / p, t)
    print("selftest ok")


def main():
    if len(sys.argv) < 2:
        sys.exit('usage: uv run disco_sync.py "<youtube url | audio file>" [out_dir]')
    if sys.argv[1] == "--test":
        return _selftest()
    out_dir = Path(sys.argv[2] if len(sys.argv) > 2 else ".").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    wav = fetch_wav(sys.argv[1], out_dir)
    print(tr("Анализ", "Analyzing") + f": {wav.name} ...")
    r = analyze(wav)
    bpm_txt = str(round(r["bpm"])) if r["snapped"] else num(r["bpm"], 2)
    print(tr("\nФайл: ", "\nFile: ") + str(wav))
    print(tr("\n  Моя музыка -> вбить в игру:", "\n  My Music -> enter in the game:"))
    print(tr("  Темп:                  ", "  BPM:                ") + bpm_txt)
    print(tr("  Смещение ритма (мс):   ", "  Beat Offset (ms):   ") + str(r["offset"]))
    print(tr("  Время начала (с):      ", "  Start Time (s):     ") + num(r["start"], 2))
    print(tr("  Время окончания (с):   ", "  End Time (s):       ") + num(r["dur"], 3))
    print(tr("\nWAV выделен в Проводнике: добавь в игру его и не перемещай потом.",
             "\nThe WAV is selected in Explorer: add it to the game and keep it in place."))
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", str(wav)])
    spread = max(r["votes"].values()) - min(r["votes"].values())
    votes = ", ".join(f"{k} {v:+d}" for k, v in r["votes"].items())
    bpms = " / ".join(num(b, 2) for b in r["bpm_votes"])
    print(tr(f"\nСверка: темп по моделям {bpms}; смещение относительно итога: {votes} мс (разброс {spread} мс)",
             f"\nCross-check: BPM per model {bpms}; offset vs result: {votes} ms (spread {spread} ms)"))
    if spread > 15:
        print(tr("  Голоса заметно расходятся: если в игре удары мимо, попробуй смещение ± эти мс.",
                 "  The votes disagree: if hits feel off in the game, try the offset +- these ms."))
    if "warped_from_ms" in r:
        print(tr(f"\nТрек выровнен под один темп: удары гуляли на ~{r['warped_from_ms']:.0f} мс, "
                 f"теперь ~{r['jitter_ms']:.0f} мс. Звук чуть растянут/сжат местами, на слух не заметно.",
                 f"\nTrack warped onto one tempo: beats wandered ~{r['warped_from_ms']:.0f} ms, "
                 f"now ~{r['jitter_ms']:.0f} ms. Audio is stretched by 1-2% in places, inaudible."))
    if r["jitter_ms"] > 15:
        print(tr(f"\nВНИМАНИЕ: удары всё ещё гуляют на ~{r['jitter_ms']:.0f} мс, проверь трек в игре.",
                 f"\nWARNING: beats still wander ~{r['jitter_ms']:.0f} ms, check the track in the game."))

if __name__ == "__main__":
    main()
