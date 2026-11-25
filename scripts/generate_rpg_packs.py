"""
名作RPG・任天堂ゲームの「嬉しくなる音楽文法」にインスパイアされた
5系統のオリジナルマルチトラック報酬ジングル生成スクリプト。
  1. rpg_poke     : 王道RPG（回復・レベルアップ風の繰り返し＆温かい解決）
  2. zelda_mystic : 冒険・謎解き（ハープ・チェレスタ・半音階上昇からの発見解決）
  3. persona_style: スタイリッシュRPG（Maj9・シンコペーション・艶エレピ＆ブラス）
  4. dq_fanfare   : クラシックRPG（3連符・ブラス・ティンパニの堂々たるファンファーレ）
  5. mario_pop    : ポップアクション（マリンバ・跳ねるリズム・爽快ゴール感）
"""

import os
import wave
import numpy as np
from scipy.signal import butter, sosfilt, fftconvolve

SR = 44100
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "public", "sfx")


def midi_to_hz(note: float) -> float:
    return 440.0 * (2.0 ** ((note - 69.0) / 12.0))


def lowpass(x: np.ndarray, cutoff: float, order: int = 3) -> np.ndarray:
    nyq = SR * 0.5
    sos = butter(order, min(nyq * 0.95, cutoff) / nyq, btype="low", output="sos")
    return sosfilt(sos, x)


def highpass(x: np.ndarray, cutoff: float, order: int = 2) -> np.ndarray:
    nyq = SR * 0.5
    sos = butter(order, max(20.0, cutoff) / nyq, btype="high", output="sos")
    return sosfilt(sos, x)


def make_hall_reverb(decay_sec: float = 0.75, damping_hz: float = 5500.0, seed: int = 77) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    n = int(SR * decay_sec)
    t = np.arange(n) / SR
    env = np.exp(-t * (5.8 / decay_sec))
    l = rng.standard_normal(n) * env
    r = rng.standard_normal(n) * env
    for ms, al, ar in [(11, 0.5, 0.25), (19, 0.22, 0.48), (29, 0.35, 0.28), (43, 0.2, 0.32)]:
        idx = int(SR * ms / 1000)
        if idx < n:
            l[idx] += al
            r[idx] += ar
    l = lowpass(l, damping_hz, 2)
    r = lowpass(r, damping_hz, 2)
    fade = min(int(SR * 0.006), n)
    l[:fade] *= np.linspace(0, 1, fade)
    r[:fade] *= np.linspace(0, 1, fade)
    norm = max(np.sqrt(np.sum(l**2)), np.sqrt(np.sum(r**2)), 1e-6)
    return l / norm, r / norm


def apply_reverb(stereo: np.ndarray, wet: float = 0.32, decay_sec: float = 0.65, seed: int = 77) -> np.ndarray:
    ir_l, ir_r = make_hall_reverb(decay_sec, 5800.0, seed)
    wl = fftconvolve(stereo[0], ir_l, mode="full")
    wr = fftconvolve(stereo[1], ir_r, mode="full")
    n = max(stereo.shape[1], len(wl))
    out = np.zeros((2, n), dtype=np.float64)
    out[:, : stereo.shape[1]] += stereo
    out[0, : len(wl)] += wl * wet
    out[1, : len(wr)] += wr * wet
    return out


def mix_at(canvas: np.ndarray, sig: np.ndarray, start_sec: float, pan: float = 0.0, gain: float = 1.0) -> None:
    idx = int(start_sec * SR)
    if idx < 0 or idx >= canvas.shape[1]:
        return
    if sig.ndim == 1:
        n = min(len(sig), canvas.shape[1] - idx)
        ang = (pan + 1.0) * 0.25 * np.pi
        canvas[0, idx : idx + n] += sig[:n] * (np.cos(ang) * gain)
        canvas[1, idx : idx + n] += sig[:n] * (np.sin(ang) * gain)
    else:
        n = min(sig.shape[1], canvas.shape[1] - idx)
        canvas[0, idx : idx + n] += sig[0, :n] * gain
        canvas[1, idx : idx + n] += sig[1, :n] * gain


# ============================================================
# 楽器音源ライブラリ
# ============================================================
def glockenspiel(midi_note: float, dur: float, vel: float = 1.0) -> np.ndarray:
    f = midi_to_hz(midi_note)
    n = int(SR * dur)
    t = np.arange(n) / SR
    atk = np.minimum(1.0, t / 0.002)
    sig = (
        1.00 * np.sin(2 * np.pi * f * t) * np.exp(-t * (4.2 / dur))
        + 0.35 * np.sin(2 * np.pi * f * 2.756 * t) * np.exp(-t * (10.0 / dur))
        + 0.16 * np.sin(2 * np.pi * f * 5.404 * t) * np.exp(-t * (18.0 / dur))
    ) * atk
    return sig * vel


def marimba(midi_note: float, dur: float, vel: float = 1.0) -> np.ndarray:
    f = midi_to_hz(midi_note)
    n = int(SR * dur)
    t = np.arange(n) / SR
    atk = np.minimum(1.0, t / 0.0018)
    sig = (
        1.00 * np.sin(2 * np.pi * f * t) * np.exp(-t * (6.2 / dur))
        + 0.32 * np.sin(2 * np.pi * f * 4.0 * t) * np.exp(-t * (28.0 / dur))
        + 0.12 * np.sin(2 * np.pi * f * 10.0 * t) * np.exp(-t * (48.0 / dur))
    ) * atk
    return lowpass(sig, 5200.0, 2) * vel


def harp_pluck(midi_note: float, dur: float, vel: float = 1.0, seed: int = 3) -> np.ndarray:
    f = midi_to_hz(midi_note)
    rng = np.random.default_rng(seed)
    n = int(SR * dur)
    delay = max(2, int(round(SR / f)))
    buf = lowpass(rng.standard_normal(delay), min(8500.0, f * 7.5), 2)
    out = np.zeros(n)
    decay = 0.9972 if f < 550 else 0.9955
    for i in range(n):
        v = buf[i % delay]
        out[i] = v
        buf[i % delay] = 0.5 * (v + buf[(i + 1) % delay]) * decay
    t = np.arange(n) / SR
    out *= np.exp(-t * (2.6 / dur))
    return highpass(out, 110.0) * vel


def warm_epiano(midi_note: float, dur: float, vel: float = 1.0) -> np.ndarray:
    f = midi_to_hz(midi_note)
    n = int(SR * dur)
    t = np.arange(n) / SR
    atk = np.minimum(1.0, t / 0.005)
    rel = np.minimum(1.0, np.maximum(0.0, (dur - t) / 0.06))
    mod = 1.5 * np.exp(-t * 13.0) * np.sin(2 * np.pi * f * 2.0 * t)
    sig = (
        0.78 * np.sin(2 * np.pi * f * t + mod)
        + 0.25 * np.sin(2 * np.pi * f * 2.0 * t) * np.exp(-t * 5.2)
        + 0.11 * np.sin(2 * np.pi * f * 3.0 * t) * np.exp(-t * 8.5)
    ) * np.exp(-t * (2.5 / dur)) * atk * rel
    return lowpass(sig, 4400.0, 2) * vel


def bright_brass(midi_note: float, dur: float, vel: float = 1.0, brightness: float = 3600.0) -> np.ndarray:
    f = midi_to_hz(midi_note)
    n = int(SR * dur)
    t = np.arange(n) / SR
    atk = np.minimum(1.0, t / 0.014)
    rel = np.minimum(1.0, np.maximum(0.0, (dur - t) / 0.05))
    l = np.zeros(n)
    r = np.zeros(n)
    for k in range(1, 8):
        if f * k >= SR * 0.42:
            break
        amp = 1.0 / (k ** 1.1)
        l += amp * np.sin(2 * np.pi * (f * 0.9968) * k * t)
        r += amp * np.sin(2 * np.pi * (f * 1.0032) * k * t)
    env = atk * rel * (0.84 + 0.16 * np.exp(-t * 7.0))
    l = lowpass(l * env, brightness, 2) * vel
    r = lowpass(r * env, brightness, 2) * vel
    return np.vstack([l, r])


def strings_pad(midi_note: float, dur: float, vel: float = 1.0) -> np.ndarray:
    f = midi_to_hz(midi_note)
    n = int(SR * dur)
    t = np.arange(n) / SR
    atk = np.minimum(1.0, t / 0.07)
    rel = np.minimum(1.0, np.maximum(0.0, (dur - t) / 0.18))
    l = np.zeros(n)
    r = np.zeros(n)
    for k in range(1, 6):
        if f * k >= SR * 0.4:
            break
        amp = 1.0 / (k ** 1.35)
        vib = 0.002 * np.sin(2 * np.pi * 5.2 * t)
        l += amp * np.sin(2 * np.pi * f * (0.996 + vib) * k * t)
        r += amp * np.sin(2 * np.pi * f * (1.004 - vib) * k * t)
    env = atk * rel
    return np.vstack([lowpass(l * env, 2800.0, 2) * vel, lowpass(r * env, 2800.0, 2) * vel])


def synth_lead(midi_note: float, dur: float, vel: float = 1.0) -> np.ndarray:
    """ポップアクション用の明るいシンセベル・リード"""
    f = midi_to_hz(midi_note)
    n = int(SR * dur)
    t = np.arange(n) / SR
    atk = np.minimum(1.0, t / 0.004)
    rel = np.minimum(1.0, np.maximum(0.0, (dur - t) / 0.04))
    sig = (
        0.7 * np.sin(2 * np.pi * f * t)
        + 0.35 * np.sign(np.sin(2 * np.pi * f * t)) * 0.45
        + 0.25 * np.sin(2 * np.pi * f * 2.0 * t)
    ) * atk * rel * np.exp(-t * (2.8 / dur))
    return lowpass(sig, 4600.0, 2) * vel


def warm_bass(midi_note: float, dur: float, vel: float = 1.0) -> np.ndarray:
    f = midi_to_hz(midi_note)
    n = int(SR * dur)
    t = np.arange(n) / SR
    atk = np.minimum(1.0, t / 0.007)
    rel = np.minimum(1.0, np.maximum(0.0, (dur - t) / 0.06))
    sig = (np.sin(2 * np.pi * f * t) + 0.38 * np.sin(2 * np.pi * f * 2.0 * t)) * atk * rel * np.exp(-t * (2.3 / dur))
    return lowpass(np.tanh(sig * 1.25), 800.0, 2) * vel


def timpani(midi_note: float, dur: float = 0.45, vel: float = 1.0) -> np.ndarray:
    f = midi_to_hz(midi_note)
    n = int(SR * dur)
    t = np.arange(n) / SR
    freqs = f * (1.0 + 0.22 * np.exp(-t * 32.0))
    phase = 2 * np.pi * np.cumsum(freqs) / SR
    env = np.exp(-t * (5.2 / dur)) * np.minimum(1.0, t / 0.004)
    sig = np.tanh((np.sin(phase) + 0.4 * np.sin(phase * 1.5)) * 1.4) * env
    return lowpass(sig, 600.0, 2) * vel


def soft_shaker(vel: float = 1.0, seed: int = 5) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(SR * 0.045)
    t = np.arange(n) / SR
    return highpass(rng.standard_normal(n) * np.exp(-t * 85.0), 3400.0, 2) * vel


def crisp_snare(vel: float = 1.0, seed: int = 9) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(SR * 0.09)
    t = np.arange(n) / SR
    body = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 45.0) * 0.45
    wire = highpass(rng.standard_normal(n) * np.exp(-t * 38.0), 1800.0, 2) * 0.65
    return (body + wire) * vel


def save_wav(stereo: np.ndarray, filename: str, max_dur_sec: float | None = None) -> None:
    if max_dur_sec is not None:
        max_n = int(SR * max_dur_sec)
        if stereo.shape[1] > max_n:
            stereo = stereo[:, :max_n].copy()
            fade = int(SR * 0.05)
            stereo[:, -fade:] *= np.linspace(1.0, 0.0, fade)

    stereo = np.vstack([highpass(stereo[0], 35.0, 2), highpass(stereo[1], 35.0, 2)])
    peak = np.max(np.abs(stereo))
    if peak > 1e-6:
        stereo = stereo / peak
    stereo = np.tanh(stereo * 1.12) / np.tanh(1.12) * 0.88

    mag = np.max(np.abs(stereo), axis=0)
    nz = np.where(mag > 0.0012)[0]
    if len(nz) > 0:
        stereo = stereo[:, : min(stereo.shape[1], int(nz[-1]) + int(SR * 0.03))]

    pcm = np.clip(stereo.T * 32767.0, -32768, 32767).astype(np.int16)
    with wave.open(os.path.join(OUT_DIR, filename), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())


# ============================================================
# Pack 2: 冒険・謎解き発見系 (zelda_mystic)
# ============================================================
def build_zelda():
    # light: ハープの軽快な発見3音
    c = np.zeros((2, int(SR * 1.05)))
    for i, (n, st, pan) in enumerate([(71, 0.0, -0.25), (74, 0.08, 0.0), (79, 0.16, 0.25)]):
        mix_at(c, harp_pluck(n, 0.55, 0.85, seed=101 + i), st, pan, 0.85)
        mix_at(c, glockenspiel(n + 12, 0.35, 0.38), st + 0.008, -pan * 0.5, 0.65)
    c = apply_reverb(c, wet=0.36, decay_sec=0.62, seed=201)
    save_wav(c, "zelda_mystic_light.wav", 1.05)

    # heavy: 半音階ミステリアス上昇 -> 視界が開ける大発見解決！
    c = np.zeros((2, int(SR * 1.75)))
    # F#5 -> G5 -> G#5 -> A5 -> C#6 -> D6 (謎が解けてパッと晴れる！)
    run = [(78, 0.0, -0.3), (79, 0.10, -0.15), (80, 0.20, 0.0), (81, 0.30, 0.15), (85, 0.42, 0.25)]
    for i, (n, st, pan) in enumerate(run):
        mix_at(c, harp_pluck(n, 0.42, 0.85, seed=110 + i), st, pan, 0.8)
        mix_at(c, glockenspiel(n, 0.25, 0.52), st, -pan * 0.5, 0.65)
    # 解決 Dメジャー (0.56s)
    t_res = 0.56
    mix_at(c, warm_bass(50, 0.95, 0.72), t_res, 0.0, 0.75)
    for n in [62, 66, 69, 74]:
        mix_at(c, strings_pad(n, 0.95, 0.36), t_res, 0.0, 0.65)
    mix_at(c, glockenspiel(86, 0.95, 0.95), t_res, 0.0, 0.88)
    mix_at(c, harp_pluck(74, 0.85, 0.75, seed=120), t_res, -0.2, 0.7)
    mix_at(c, glockenspiel(90, 0.65, 0.45), t_res + 0.14, +0.3, 0.62)
    c = apply_reverb(c, wet=0.42, decay_sec=0.82, seed=202)
    save_wav(c, "zelda_mystic_heavy.wav", 1.75)

    # chain: 宝箱の光が溢れるハープアルペジオ
    c = np.zeros((2, int(SR * 1.35)))
    arp = [69, 73, 76, 81, 85, 88]
    for i, n in enumerate(arp):
        st = i * 0.055
        pan = -0.35 + i * 0.14
        mix_at(c, harp_pluck(n, 0.65, 0.85, seed=130 + i), st, pan, 0.82)
        mix_at(c, glockenspiel(n, 0.42, 0.45), st + 0.006, -pan * 0.4, 0.6)
    mix_at(c, strings_pad(69, 0.75, 0.35), 0.25, 0.0, 0.6)
    c = apply_reverb(c, wet=0.40, decay_sec=0.72, seed=203)
    save_wav(c, "zelda_mystic_chain.wav", 1.35)

    # levelup: 壮大な冒険の大発見ファンファーレ
    c = np.zeros((2, int(SR * 2.25)))
    # 期待を高める4音上昇 (G4 -> A4 -> B4 -> C#5 -> D5 解決！)
    build = [(67, 0.00, 0.14), (69, 0.14, 0.14), (71, 0.28, 0.14), (73, 0.42, 0.16)]
    for i, (n, st, dur) in enumerate(build):
        mix_at(c, bright_brass(n, dur + 0.04, 0.58, 3000.0), st, 0.0, 0.68)
        mix_at(c, harp_pluck(n + 12, 0.38, 0.75, seed=140 + i), st, (i - 1.5) * 0.2, 0.75)
    t_hit = 0.60
    mix_at(c, timpani(50, 0.55, 0.85), t_hit, 0.0, 0.8)
    mix_at(c, warm_bass(50, 1.35, 0.75), t_hit, 0.0, 0.75)
    for n in [62, 66, 69, 74]:
        mix_at(c, bright_brass(n, 1.25, 0.48, 3400.0), t_hit, 0.0, 0.62)
        mix_at(c, strings_pad(n, 1.35, 0.42), t_hit, 0.0, 0.65)
    for i, n in enumerate([74, 78, 81, 86, 90]):
        mix_at(c, glockenspiel(n, 0.85, 0.62), t_hit + 0.05 + i * 0.06, (i - 2) * 0.18, 0.7)
    c = apply_reverb(c, wet=0.44, decay_sec=0.92, seed=204)
    save_wav(c, "zelda_mystic_levelup.wav", 2.25)


# ============================================================
# Pack 3: スタイリッシュ都会派RPG系 (persona_style)
# ============================================================
def build_persona():
    # light: おしゃれなMaj9エレピ2打「タ・ターン♪」
    c = np.zeros((2, int(SR * 0.95)))
    # Cmaj9 -> Dmaj9 的な都会的スライド
    for n, pan in [(60, -0.2), (64, 0.0), (67, 0.2), (71, 0.3)]:
        mix_at(c, warm_epiano(n, 0.14, 0.62), 0.0, pan, 0.72)
    mix_at(c, crisp_snare(0.28, seed=301), 0.0, 0.0, 0.65)
    for n, pan in [(62, -0.25), (66, -0.05), (69, 0.15), (73, 0.3), (76, 0.1)]:
        mix_at(c, warm_epiano(n, 0.58, 0.72), 0.11, pan, 0.78)
    mix_at(c, warm_bass(50, 0.48, 0.68), 0.11, 0.0, 0.75)
    c = apply_reverb(c, wet=0.25, decay_sec=0.45, seed=311)
    save_wav(c, "persona_style_light.wav", 0.95)

    # heavy: シンコペーションで跳ねる都会派キメフレーズ
    c = np.zeros((2, int(SR * 1.45)))
    # 跳ねるリズム: 0.00, 0.12, 0.28(裏拍), 0.44(キメ!)
    hits = [
        (0.00, [64, 67, 71, 74], 52, 0.13),  # Em7
        (0.13, [66, 69, 73, 76], 54, 0.13),  # F#m7
        (0.29, [67, 71, 74, 78], 55, 0.15),  # Gmaj7
        (0.45, [69, 73, 76, 80, 83], 57, 0.75),  # Amaj9 キメ！
    ]
    for idx, (st, chord, bass, dur) in enumerate(hits):
        mix_at(c, warm_bass(bass, dur + 0.05, 0.78), st, 0.0, 0.82)
        for ci, n in enumerate(chord):
            mix_at(c, warm_epiano(n, dur + 0.08, 0.65), st, (ci - 1.5) * 0.18, 0.72)
        if idx in (0, 2, 3):
            mix_at(c, bright_brass(chord[-1], dur, 0.42, 4200.0), st, 0.0, 0.58)
        if idx in (1, 3):
            mix_at(c, crisp_snare(0.38 if idx == 3 else 0.24, seed=320 + idx), st, 0.0, 0.75)
    # 艶のある高音ベル余韻
    mix_at(c, glockenspiel(88, 0.55, 0.45), 0.56, 0.3, 0.6)
    c = apply_reverb(c, wet=0.28, decay_sec=0.55, seed=312)
    save_wav(c, "persona_style_heavy.wav", 1.45)

    # chain: スタイリッシュなコンボ確定ブラス＆エレピ
    c = np.zeros((2, int(SR * 1.15)))
    for i, (st, n) in enumerate([(0.0, 71), (0.08, 74), (0.16, 78), (0.26, 83)]):
        mix_at(c, warm_epiano(n, 0.35 if i < 3 else 0.65, 0.78), st, (i - 1.5) * 0.18, 0.8)
        mix_at(c, bright_brass(n - 12, 0.14 if i < 3 else 0.55, 0.45, 4400.0), st, 0.0, 0.6)
    mix_at(c, warm_bass(59, 0.55, 0.75), 0.26, 0.0, 0.8)
    mix_at(c, crisp_snare(0.35, seed=330), 0.26, 0.0, 0.72)
    c = apply_reverb(c, wet=0.26, decay_sec=0.48, seed=313)
    save_wav(c, "persona_style_chain.wav", 1.15)

    # levelup: 都会派ジャズ・ブラスキメの超スタイリッシュLvUP!
    c = np.zeros((2, int(SR * 1.95)))
    seq = [
        (0.00, [62, 66, 69, 73], 50, 0.12),
        (0.11, [64, 68, 71, 75], 52, 0.12),
        (0.22, [65, 69, 72, 76], 53, 0.12),
        (0.35, [67, 71, 74, 78], 55, 0.16),
        (0.53, [69, 73, 76, 80, 83], 45, 1.05),
    ]
    for idx, (st, chord, bass, dur) in enumerate(seq):
        mix_at(c, warm_bass(bass, dur + 0.08, 0.85), st, 0.0, 0.85)
        for ci, n in enumerate(chord):
            mix_at(c, warm_epiano(n, dur + 0.1, 0.62), st, (ci - 2) * 0.16, 0.7)
            if idx == 4 or ci >= len(chord) - 2:
                mix_at(c, bright_brass(n, dur, 0.46, 4400.0), st, 0.0, 0.62)
        mix_at(c, crisp_snare(0.45 if idx == 4 else 0.24, seed=340 + idx), st, 0.0, 0.75)
    for i, n in enumerate([83, 85, 88]):
        mix_at(c, glockenspiel(n, 0.65, 0.48), 0.70 + i * 0.07, (i - 1) * 0.28, 0.65)
    c = apply_reverb(c, wet=0.30, decay_sec=0.65, seed=314)
    save_wav(c, "persona_style_levelup.wav", 1.95)


# ============================================================
# Pack 4: クラシック・オーケストラRPG系 (dq_fanfare)
# ============================================================
def build_dq():
    # light: 元気な3音ブラス＆弦の確定
    c = np.zeros((2, int(SR * 0.95)))
    for i, (n, st, dur) in enumerate([(72, 0.0, 0.10), (76, 0.09, 0.10), (79, 0.18, 0.48)]):
        mix_at(c, bright_brass(n, dur, 0.68, 3600.0), st, 0.0, 0.75)
        mix_at(c, glockenspiel(n + 12, dur, 0.35), st, (i - 1) * 0.2, 0.6)
    mix_at(c, timpani(48, 0.32, 0.75), 0.18, 0.0, 0.75)
    c = apply_reverb(c, wet=0.34, decay_sec=0.62, seed=401)
    save_wav(c, "dq_fanfare_light.wav", 0.95)

    # heavy: 3連符で駆け上がって堂々と決まるクエスト達成！
    c = np.zeros((2, int(SR * 1.65)))
    # 3連符「タタタ・ターン！ タ・ターン！」 (G4-A4-B4 -> C5, D5 -> G5)
    notes = [
        (67, 0.00, 0.09), (69, 0.09, 0.09), (71, 0.18, 0.09),
        (72, 0.27, 0.24), (74, 0.53, 0.14), (79, 0.68, 0.72),
    ]
    for n, st, dur in notes:
        mix_at(c, bright_brass(n, dur + 0.03, 0.72, 3800.0), st, 0.0, 0.78)
    mix_at(c, timpani(48, 0.35, 0.7), 0.27, 0.0, 0.7)
    mix_at(c, timpani(55, 0.55, 0.88), 0.68, 0.0, 0.82)
    for n in [67, 71, 74, 79]:
        mix_at(c, strings_pad(n, 0.78, 0.42), 0.68, 0.0, 0.68)
    mix_at(c, glockenspiel(91, 0.65, 0.55), 0.70, 0.0, 0.65)
    c = apply_reverb(c, wet=0.38, decay_sec=0.75, seed=402)
    save_wav(c, "dq_fanfare_heavy.wav", 1.65)

    # chain: 軽快な跳躍オーケストラフレーズ
    c = np.zeros((2, int(SR * 1.25)))
    for i, (n, st, dur) in enumerate([(72, 0.0, 0.10), (74, 0.09, 0.10), (76, 0.18, 0.10), (79, 0.28, 0.14), (84, 0.42, 0.58)]):
        mix_at(c, bright_brass(n, dur + 0.03, 0.66, 3700.0), st, 0.0, 0.72)
        mix_at(c, glockenspiel(n, dur + 0.1, 0.45), st, (i - 2) * 0.16, 0.65)
    mix_at(c, timpani(48, 0.42, 0.8), 0.42, 0.0, 0.78)
    c = apply_reverb(c, wet=0.36, decay_sec=0.68, seed=403)
    save_wav(c, "dq_fanfare_chain.wav", 1.25)

    # levelup: 王道クラシックRPGの堂々たるレベルアップファンファーレ！
    c = np.zeros((2, int(SR * 2.25)))
    # 3連符×2で高揚させてドーン！
    fan = [
        (72, 0.00, 0.09), (72, 0.09, 0.09), (72, 0.18, 0.09),
        (72, 0.28, 0.22), (70, 0.52, 0.18), (74, 0.71, 0.18),
        (72, 0.90, 0.98),
    ]
    for n, st, dur in fan:
        mix_at(c, bright_brass(n, dur + 0.04, 0.75, 4000.0), st, 0.0, 0.78)
        mix_at(c, bright_brass(n - 12, dur + 0.04, 0.48, 3000.0), st, 0.0, 0.62)
    mix_at(c, timpani(48, 0.35, 0.75), 0.28, 0.0, 0.75)
    mix_at(c, timpani(48, 0.65, 0.95), 0.90, 0.0, 0.88)
    for n in [60, 64, 67, 72, 76]:
        mix_at(c, strings_pad(n, 1.05, 0.4), 0.90, 0.0, 0.65)
    for i, n in enumerate([84, 88, 91]):
        mix_at(c, glockenspiel(n, 0.75, 0.55), 0.94 + i * 0.06, (i - 1) * 0.25, 0.68)
    c = apply_reverb(c, wet=0.40, decay_sec=0.88, seed=404)
    save_wav(c, "dq_fanfare_levelup.wav", 2.25)


# ============================================================
# Pack 5: ポップ＆爽快アクション系 (mario_pop)
# ============================================================
def build_mario():
    # light: ポン・ポロン♪と弾むマリンバ＆シンセ
    c = np.zeros((2, int(SR * 0.85)))
    for i, (n, st, pan) in enumerate([(76, 0.0, -0.2), (83, 0.085, 0.2)]):
        mix_at(c, marimba(n, 0.22 if i == 0 else 0.45, 0.85), st, pan, 0.85)
        mix_at(c, synth_lead(n, 0.14 if i == 0 else 0.35, 0.45), st, -pan * 0.5, 0.65)
    mix_at(c, soft_shaker(0.32, seed=501), 0.085, 0.0, 0.7)
    c = apply_reverb(c, wet=0.22, decay_sec=0.42, seed=511)
    save_wav(c, "mario_pop_light.wav", 0.85)

    # heavy: チェックポイント通過風の弾む5音メロディ！
    c = np.zeros((2, int(SR * 1.35)))
    mel = [(72, 0.0, 0.12), (76, 0.10, 0.12), (79, 0.20, 0.12), (84, 0.31, 0.18), (88, 0.48, 0.58)]
    for i, (n, st, dur) in enumerate(mel):
        pan = -0.3 + i * 0.15
        mix_at(c, marimba(n, dur + 0.1, 0.88), st, pan, 0.85)
        mix_at(c, synth_lead(n, dur + 0.05, 0.52), st, -pan * 0.5, 0.68)
    mix_at(c, warm_bass(48, 0.65, 0.75), 0.48, 0.0, 0.78)
    for n, pan in [(64, -0.25), (67, 0.0), (72, 0.25)]:
        mix_at(c, warm_epiano(n, 0.62, 0.48), 0.48, pan, 0.65)
    mix_at(c, soft_shaker(0.38, seed=502), 0.48, 0.0, 0.75)
    c = apply_reverb(c, wet=0.26, decay_sec=0.52, seed=512)
    save_wav(c, "mario_pop_heavy.wav", 1.35)

    # chain: パワーアップ風のキュッと駆け上がる爽快フレーズ
    c = np.zeros((2, int(SR * 1.1)))
    notes = [67, 71, 74, 79, 83, 86]
    for i, n in enumerate(notes):
        st = i * 0.055
        mix_at(c, synth_lead(n, 0.14 if i < 5 else 0.52, 0.68), st, (i - 2.5) * 0.14, 0.78)
        mix_at(c, marimba(n, 0.18 if i < 5 else 0.55, 0.78), st, -(i - 2.5) * 0.1, 0.75)
    mix_at(c, warm_bass(55, 0.48, 0.7), 0.28, 0.0, 0.72)
    c = apply_reverb(c, wet=0.25, decay_sec=0.48, seed=513)
    save_wav(c, "mario_pop_chain.wav", 1.1)

    # levelup: コースクリア！みたいに弾け飛ぶポップゴールファンファーレ
    c = np.zeros((2, int(SR * 1.95)))
    seq = [
        (72, 0.00, 0.10), (76, 0.09, 0.10), (79, 0.18, 0.10),
        (84, 0.28, 0.16), (79, 0.45, 0.12), (88, 0.58, 0.95),
    ]
    for i, (n, st, dur) in enumerate(seq):
        mix_at(c, synth_lead(n, dur + 0.06, 0.62), st, (i - 2.5) * 0.12, 0.78)
        mix_at(c, marimba(n, dur + 0.12, 0.85), st, -(i - 2.5) * 0.1, 0.82)
        if i in (0, 3, 5):
            mix_at(c, crisp_snare(0.32 if i == 5 else 0.2, seed=520 + i), st, 0.0, 0.7)
    mix_at(c, warm_bass(48, 1.05, 0.82), 0.58, 0.0, 0.82)
    for n, pan in [(64, -0.3), (67, 0.0), (72, 0.3), (76, 0.15)]:
        mix_at(c, warm_epiano(n, 1.0, 0.52), 0.58, pan, 0.68)
    for i, n in enumerate([88, 91, 96]):
        mix_at(c, glockenspiel(n, 0.65, 0.52), 0.72 + i * 0.065, (i - 1) * 0.28, 0.68)
    c = apply_reverb(c, wet=0.30, decay_sec=0.62, seed=514)
    save_wav(c, "mario_pop_levelup.wav", 1.95)


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    build_zelda()
    build_persona()
    build_dq()
    build_mario()
    print("Generated 4 new game-inspired jingle packs (16 WAVs) successfully")
