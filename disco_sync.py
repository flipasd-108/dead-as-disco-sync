# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["beat-this", "soundfile", "yt-dlp[default,deno]", "imageio-ffmpeg"]
# ///
"""Dead as Disco sync: YouTube link or audio file -> WAV + BPM / Beat Offset / Start Time.

Run:  uv run disco_sync.py "https://youtu.be/..."   (or a local file path)
Import the WAV it writes into the game: the offset is measured on exactly that file.
"""
import os, subprocess, sys, time
from pathlib import Path

import numpy as np
import soundfile as sf
import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


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
        }
        if os.environ.get("COOKIES_BROWSER"):  # e.g. chrome / firefox / edge, when YouTube asks to sign in
            opts["cookiesfrombrowser"] = (os.environ["COOKIES_BROWSER"],)
        with yt_dlp.YoutubeDL(opts) as ydl:
            for attempt in range(4):  # YouTube's bot check is intermittent, a retry usually passes
                try:
                    info = ydl.extract_info(src)
                    return Path(ydl.prepare_filename(info)).with_suffix(".wav")
                except yt_dlp.utils.DownloadError as e:
                    if "not a bot" not in str(e):
                        raise
                    print(f"YouTube bot check, retrying ({attempt + 1}/3)...")
                    time.sleep(5)
            sys.exit("YouTube wants a sign-in: try later, or set COOKIES_BROWSER=firefox (a browser logged in to YouTube).")
    src_path = Path(src)
    wav = out_dir / (src_path.stem + ".wav")
    if src_path.resolve() != wav.resolve():
        subprocess.run([FFMPEG, "-y", "-v", "error", "-i", str(src_path), wav], check=True)
    return wav


def fit_grid(beats: np.ndarray):
    """Least-squares constant grid through beat times. Returns period_s, t0_s, residuals_s."""
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
    return period, t0, resid[keep]


def rms_frames(mono: np.ndarray, hop: int) -> np.ndarray:
    return np.sqrt((mono[: len(mono) // hop * hop].reshape(-1, hop) ** 2).mean(1))


def start_time(mono: np.ndarray, sr: int) -> float:
    # first 10 ms frame within -40 dB of the loudest one
    hop = sr // 100
    env = rms_frames(mono, hop)
    return round(int(np.argmax(env > env.max() * 0.01)) * hop / sr, 2)


def refine_t0(mono: np.ndarray, sr: int, period: float, t0: float) -> float:
    # the beat tracker works in 20 ms frames: snap the grid onto the attacks (1 ms envelope),
    # but only when the best fit lies within one tracker frame; a far peak on a dense mix is another instrument
    hop = sr // 1000
    fps = sr / hop
    env = rms_frames(mono, hop)
    flux = np.maximum(0, np.diff(np.log(env + env.max() * 1e-3), prepend=0))
    grid = np.round((t0 % period + np.arange(int(len(env) / fps / period)) * period) * fps).astype(int)
    grid = grid[(grid >= 40) & (grid < len(flux) - 40)]
    shifts = np.arange(-40, 41)
    best = shifts[np.argmax([flux[grid + s].sum() for s in shifts])]
    return t0 + best / fps if abs(best) <= 12 else t0


def analyze(wav: Path):
    from beat_this.inference import Audio2Beats
    audio, sr = sf.read(wav, dtype="float64")
    mono = audio.mean(1) if audio.ndim == 2 else audio
    beats, _ = Audio2Beats(checkpoint_path="final0", device="cpu", dbn=False)(mono, sr)
    beats = np.asarray(beats)
    period, t0, resid = fit_grid(beats)
    bpm = 60 / period
    snapped = abs(bpm - round(bpm)) < 0.03  # produced tracks are usually exactly integer BPM
    if snapped:
        idx = np.round((beats - t0) / (60 / round(bpm)))
        period = 60 / round(bpm)
        t0 = np.median(beats - idx * period)
    offset_ms = round((refine_t0(mono, sr, period, t0) % period) * 1000)
    dur = len(mono) / sr
    sections = []  # live recordings drift: local grid per 30 s for the editor's BPM sections
    for s in range(0, int(dur), 30):
        w = beats[(beats >= s) & (beats < s + 30)]
        if len(w) >= 8:
            p, t, _ = fit_grid(w)
            sections.append((s, 60 / p, round((t % p) * 1000)))
    return dict(bpm=60 / period, snapped=snapped, offset=offset_ms, start=start_time(mono, sr), dur=dur,
                jitter_ms=float(np.sqrt(np.mean(resid ** 2)) * 1000), sections=sections)


def ru(x: float, digits: int) -> str:
    return f"{x:.{digits}f}".replace(".", ",")  # the game's Russian UI uses a decimal comma


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
    print(f"Анализ: {wav.name} ...")
    r = analyze(wav)
    bpm_txt = str(round(r["bpm"])) if r["snapped"] else ru(r["bpm"], 2)
    print(f"\nФайл: {wav}")
    print("\n  Моя музыка -> вбить в игру:")
    print(f"  Темп:                  {bpm_txt}")
    print(f"  Смещение ритма (мс):   {r['offset']}")
    print(f"  Время начала (с):      {ru(r['start'], 2)}")
    print(f"  Время окончания (с):   {ru(r['dur'], 3)}")
    print("\nWAV выделен в Проводнике: добавь в игру его и не перемещай потом.")
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", str(wav)])
    if r["jitter_ms"] > 15:
        print(f"\nВНИМАНИЕ: темп плавает (доли гуляют на ~{r['jitter_ms']:.0f} мс), живой барабанщик или смена темпа. "
              "Один темп будет уезжать; по кускам для секций в расширенном редакторе:")
        for s, b, o in r["sections"]:
            print(f"  с {s // 60}:{s % 60:02d}   Темп {ru(b, 2)}   Смещение {o}")


if __name__ == "__main__":
    main()
