# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["beat-this", "soundfile", "yt-dlp[default,deno]", "imageio-ffmpeg", "pytsmod"]
# ///
"""Dead as Disco sync: YouTube link or audio file -> WAV + BPM / Beat Offset / Start Time.

Run:  uv run disco_sync.py "https://youtu.be/..."   (or a local file path)
Import the WAV it writes into the game: the offset is measured on exactly that file.
"""
import subprocess, sys, time
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
                print("YouTube: проверка на бота, пробую по-другому...")
                time.sleep(3)
        sys.exit("\nYouTube не пускает (проверка на бота). Варианты:\n"
                 "  1) войти в YouTube в Firefox и запустить снова: программа возьмёт вход оттуда;\n"
                 "  2) в Chrome поставить расширение «Get cookies.txt LOCALLY», на youtube.com нажать Export\n"
                 f"     и положить файл cookies.txt сюда: {cookies_txt.parent}\n"
                 "  3) скачать песню любым способом и перетащить файл на DeadAsDiscoSync.bat.")
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


def analyze(wav: Path, warp: bool = True, period: float | None = None):
    """Beat grid of the file. With warp, an unsteady track is rewritten in place onto a constant tempo."""
    from beat_this.inference import Audio2Beats
    audio, sr = sf.read(wav, dtype="float64")
    mono = audio.mean(1) if audio.ndim == 2 else audio
    beats, _ = Audio2Beats(checkpoint_path="final0", device="cpu", dbn=False)(mono, sr)
    beats = np.asarray(beats)
    if period is None:
        period, t0, idx = fit_grid(beats)
    else:  # second pass over a warped file: its tempo is known exactly
        idx = np.round((beats - beats[0]) / period)
        t0 = np.median(beats - idx * period)
    resid = beats - (t0 + idx * period)
    jitter_ms = float(np.sqrt(np.mean(resid ** 2)) * 1000)
    bpm = 60 / period
    snapped = abs(bpm - round(bpm)) < 0.03  # produced tracks are usually exactly integer BPM
    if warp and jitter_ms > 15 and not snapped:
        target = 60 / round(bpm, 2)  # the game takes BPM with 2 decimals: make the file match it exactly
        print(f"Темп плавает (~{jitter_ms:.0f} мс), выравниваю трек на {ru(round(bpm, 2), 2)}...")
        sf.write(wav, warp_to_grid(audio, sr, beats, idx, period, t0, target), sr, subtype="PCM_16")
        return analyze(wav, warp=False, period=target) | {"warped_from_ms": jitter_ms}
    if snapped:
        idx = np.round((beats - t0) / (60 / round(bpm)))
        period = 60 / round(bpm)
        t0 = np.median(beats - idx * period)
    offset_ms = round((refine_t0(mono, sr, period, t0) % period) * 1000)
    return dict(bpm=60 / period, snapped=snapped, offset=offset_ms, start=start_time(mono, sr),
                dur=len(mono) / sr, jitter_ms=jitter_ms)


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
    if "warped_from_ms" in r:
        print(f"\nТрек выровнен под один темп: удары гуляли на ~{r['warped_from_ms']:.0f} мс, "
              f"теперь ~{r['jitter_ms']:.0f} мс. Звук чуть растянут/сжат местами, на слух не заметно.")
    if r["jitter_ms"] > 15:
        print(f"\nВНИМАНИЕ: удары всё ещё гуляют на ~{r['jitter_ms']:.0f} мс, проверь трек в игре.")


if __name__ == "__main__":
    main()
