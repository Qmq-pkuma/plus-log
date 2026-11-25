"""
好評だった「王道RPG（グロッケン＋温かいエレピ＋繰り返し解決＋第2波余韻）」の勝ち音色をベースに、
  - rpg_bright : 王道RPG・爽快版（同系統の澄んだ音色で軽快な別フレーズ）
  - dq_fanfare : オーケストラ改（ホルン風の柔らかいフィルタ開閉＋弦＋重厚ティンパニ＋ベル重ね）
を生成するスクリプト。既存の rpg_poke_*.wav はそのまま維持する。
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


def make_hall_reverb(decay_sec: float = 0.80, damping_hz: float = 5200.0, seed: int = 88) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    n = int(SR * decay_sec)
    t = np.arange(n) / SR
    env = np.exp(-t * (5.6 / decay_sec))
    l = rng.standard_normal(n) * env
    r = rng.standard_normal(n) * env
    for ms, al, ar in [(12, 0.48, 0.24), (21, 0.22, 0.46), (33, 0.34, 0.29), (47, 0.21, 0.31)]:
        idx = int(SR * ms / 1000)
        if idx < n:
            l[idx] += al
            r[idx] += ar
    l = lowpass(l, damping_hz, 2)
    r = lowpass(r, damping_hz, 2)
    fade = min(int(SR * 0.008), n)
    l[:fade] *= np.linspace(0, 1, fade)
    r[:fade] *= np.linspace(0, 1, fade)
    norm = max(np.sqrt(np.sum(l**2)), np.sqrt(np.sum(r**2)), 1e-6)
    return l / norm, r / norm


def apply_reverb(stereo: np.ndarray, wet: float = 0.35, decay_sec: float = 0.72, seed: int = 88) -> np.ndarray:
    ir_l, ir_r = make_hall_reverb(decay_sec, 5400.0, seed)
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


def glockenspiel(midi_note: float, dur: float, vel: float = 1.0) -> np.ndarray:
    f = midi_to_hz(midi_note)
    n = int(SR * dur)
    t = np.arange(n) / SR
    atk = np.minimum(1.0, t / 0.002)
    sig = (
        1.00 * np.sin(2 * np.pi * f * t) * np.exp(-t * (4.1 / dur))
        + 0.34 * np.sin(2 * np.pi * f * 2.756 * t) * np.exp(-t * (10.0 / dur))
        + 0.15 * np.sin(2 * np.pi * f * 5.404 * t) * np.exp(-t * (18.0 / dur))
    ) * atk
    return sig * vel


def warm_epiano(midi_note: float, dur: float, vel: float = 1.0) -> np.ndarray:
    f = midi_to_hz(midi_note)
    n = int(SR * dur)
    t = np.arange(n) / SR
    atk = np.minimum(1.0, t / 0.005)
    rel = np.minimum(1.0, np.maximum(0.0, (dur - t) / 0.06))
    mod = 1.45 * np.exp(-t * 13.5) * np.sin(2 * np.pi * f * 2.0 * t)
    sig = (
        0.80 * np.sin(2 * np.pi * f * t + mod)
        + 0.24 * np.sin(2 * np.pi * f * 2.0 * t) * np.exp(-t * 5.2)
        + 0.10 * np.sin(2 * np.pi * f * 3.0 * t) * np.exp(-t * 8.8)
    ) * np.exp(-t * (2.5 / dur)) * atk * rel
    return lowpass(sig, 4200.0, 2) * vel


def warm_horn_section(midi_note: float, dur: float, vel: float = 1.0) -> np.ndarray:
    """硬いシンセ臭を消した温かいオーケストラ・ホルン＆トランペットセクション"""
    f = midi_to_hz(midi_note)
    n = int(SR * dur)
    t = np.arange(n) / SR
    # 息の立ち上がりを再現（少し丸いアタック＋わずかなビブラート）
    atk = np.minimum(1.0, t / 0.028) ** 0.8
    rel = np.minimum(1.0, np.maximum(0.0, (dur - t) / 0.08))
    # 管楽器らしいフォルマント寄りの倍音バランス（2・3次倍音を豊かに、高次を丸める）
    harmonics = [(1, 1.0), (2, 0.72), (3, 0.45), (4, 0.22), (5, 0.10), (6, 0.04)]
    l = np.zeros(n)
    r = np.zeros(n)
    vib = 0.0024 * np.sin(2 * np.pi * 5.0 * t) * np.minimum(1.0, t / 0.25)
    for k, amp in harmonics:
        if f * k >= SR * 0.4:
            break
        # 高次倍音ほど立ち上がりを遅らせて管楽器の息の開きを再現
        h_atk = np.minimum(1.0, t / (0.018 + k * 0.009))
        l += amp * h_atk * np.sin(2 * np.pi * f * (0.997 + vib) * k * t)
        r += amp * h_atk * np.sin(2 * np.pi * f * (1.003 - vib) * k * t)
    env = atk * rel * (0.88 + 0.12 * np.exp(-t * 4.5))
    l = lowpass(l * env, 2400.0, 2) * vel
    r = lowpass(r * env, 2400.0, 2) * vel
    return np.vstack([l, r])


def strings_ensemble(midi_note: float, dur: float, vel: float = 1.0) -> np.ndarray:
    f = midi_to_hz(midi_note)
    n = int(SR * dur)
    t = np.arange(n) / SR
    atk = np.minimum(1.0, t / 0.055)
    rel = np.minimum(1.0, np.maximum(0.0, (dur - t) / 0.16))
    l = np.zeros(n)
    r = np.zeros(n)
    for k, amp in [(1, 1.0), (2, 0.5), (3, 0.25), (4, 0.12)]:
        if f * k >= SR * 0.4:
            break
        vib = 0.0022 * np.sin(2 * np.pi * 5.4 * t)
        l += amp * np.sin(2 * np.pi * f * (0.996 + vib) * k * t)
        r += amp * np.sin(2 * np.pi * f * (1.004 - vib) * k * t)
    env = atk * rel
    return np.vstack([lowpass(l * env, 2600.0, 2) * vel, lowpass(r * env, 2600.0, 2) * vel])


def warm_bass(midi_note: float, dur: float, vel: float = 1.0) -> np.ndarray:
    f = midi_to_hz(midi_note)
    n = int(SR * dur)
    t = np.arange(n) / SR
    atk = np.minimum(1.0, t / 0.008)
    rel = np.minimum(1.0, np.maximum(0.0, (dur - t) / 0.07))
    sig = (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * f * 2.0 * t)) * atk * rel * np.exp(-t * (2.2 / dur))
    return lowpass(np.tanh(sig * 1.2), 720.0, 2) * vel


def timpani(midi_note: float, dur: float = 0.55, vel: float = 1.0) -> np.ndarray:
    f = midi_to_hz(midi_note)
    n = int(SR * dur)
    t = np.arange(n) / SR
    freqs = f * (1.0 + 0.18 * np.exp(-t * 28.0))
    phase = 2 * np.pi * np.cumsum(freqs) / SR
    env = np.exp(-t * (4.6 / dur)) * np.minimum(1.0, t / 0.005)
    sig = np.tanh((np.sin(phase) + 0.38 * np.sin(phase * 1.5)) * 1.35) * env
    return lowpass(sig, 520.0, 2) * vel


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
    stereo = np.tanh(stereo * 1.1) / np.tanh(1.1) * 0.88

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
# Pack 2: 王道RPG・爽快版 (rpg_bright)
# 好評だったグロッケン＋温かいエレピの勝ち音色で、テンポよく晴れやかな別フレーズ
# ============================================================
def build_rpg_bright():
    # light: 「タ・タラ・ン♪」と軽やかに跳ねる3音
    c = np.zeros((2, int(SR * 0.90)))
    for note, st, dur, pan in [(76, 0.0, 0.14, -0.18), (79, 0.085, 0.14, 0.0), (84, 0.17, 0.48, 0.18)]:
        mix_at(c, glockenspiel(note, dur, 0.78), st, pan, 0.85)
        mix_at(c, warm_epiano(note - 12, dur + 0.1, 0.56), st, -pan * 0.5, 0.74)
    for note, pan in [(60, -0.25), (64, 0.0), (67, 0.25)]:
        mix_at(c, warm_epiano(note, 0.48, 0.42), 0.17, pan, 0.64)
    mix_at(c, warm_bass(48, 0.42, 0.55), 0.17, 0.0, 0.7)
    c = apply_reverb(c, wet=0.28, decay_sec=0.52, seed=601)
    save_wav(c, "rpg_bright_light.wav", 0.90)

    # heavy: 「タ・タ・タラ・ターン♪」の爽快達成フレーズ（Gメジャーで晴れやか）
    c = np.zeros((2, int(SR * 1.55)))
    steps = [
        (74, 0.00, 0.15, -0.20, 0.84),  # D5
        (74, 0.15, 0.15, +0.20, 0.88),  # D5 (繰り返し)
        (79, 0.30, 0.14, -0.10, 0.90),  # G5 (跳躍)
        (81, 0.43, 0.14, +0.10, 0.92),  # A5
        (83, 0.57, 0.72,  0.00, 1.00),  # B5 (晴れやかに着地！)
    ]
    for note, st, dur, pan, vel in steps:
        mix_at(c, glockenspiel(note, dur + 0.12, vel), st, pan, 0.80)
        mix_at(c, warm_epiano(note - 12, dur + 0.14, vel * 0.68), st, -pan * 0.5, 0.72)
    for idx, (note, pan) in enumerate([(55, -0.3), (62, -0.1), (67, 0.1), (71, 0.3)]):
        mix_at(c, warm_epiano(note, 0.78, 0.5), 0.57 + idx * 0.01, pan, 0.64)
    mix_at(c, warm_bass(43, 0.75, 0.65), 0.57, 0.0, 0.72)
    # 第2波キラキラ余韻
    mix_at(c, glockenspiel(86, 0.46, 0.44), 0.71, -0.32, 0.6)
    mix_at(c, glockenspiel(91, 0.54, 0.40), 0.79, +0.32, 0.58)
    c = apply_reverb(c, wet=0.33, decay_sec=0.68, seed=602)
    save_wav(c, "rpg_bright_heavy.wav", 1.55)

    # chain: スッと繋がるコンボ4音
    c = np.zeros((2, int(SR * 1.15)))
    for i, (note, st) in enumerate([(76, 0.0), (79, 0.08), (83, 0.16), (88, 0.26)]):
        pan = (i - 1.5) * 0.18
        dur = 0.14 if i < 3 else 0.62
        mix_at(c, glockenspiel(note, dur + 0.1, 0.88), st, pan, 0.82)
        mix_at(c, warm_epiano(note - 12, dur + 0.12, 0.64), st, -pan * 0.5, 0.70)
    mix_at(c, warm_bass(52, 0.58, 0.62), 0.26, 0.0, 0.70)
    c = apply_reverb(c, wet=0.32, decay_sec=0.60, seed=603)
    save_wav(c, "rpg_bright_chain.wav", 1.15)

    # levelup: 晴れやかに駆け上がる2段階レベルアップ
    c = np.zeros((2, int(SR * 2.05)))
    intro = [
        (79, 0.00, 0.09), (79, 0.095, 0.09), (79, 0.19, 0.09),
        (81, 0.30, 0.12), (83, 0.42, 0.13),
    ]
    for i, (note, st, dur) in enumerate(intro):
        pan = (i - 2) * 0.15
        mix_at(c, glockenspiel(note, dur + 0.08, 0.88), st, pan, 0.80)
        mix_at(c, warm_epiano(note - 12, dur + 0.1, 0.68), st, -pan * 0.5, 0.72)
        mix_at(c, warm_horn_section(note - 12, dur + 0.04, 0.48), st, 0.0, 0.62)
    t_hit = 0.56
    mix_at(c, warm_bass(48, 1.2, 0.82), t_hit, 0.0, 0.82)
    for note, pan in [(60, -0.35), (64, -0.12), (67, 0.12), (72, 0.35)]:
        mix_at(c, warm_epiano(note, 1.15, 0.54), t_hit, pan, 0.64)
        mix_at(c, warm_horn_section(note, 1.10, 0.46), t_hit, 0.0, 0.62)
    mix_at(c, glockenspiel(84, 1.05, 0.96), t_hit, 0.0, 0.85)
    for idx, (note, pan) in enumerate([(88, -0.32), (91, 0.0), (96, +0.32)]):
        mix_at(c, glockenspiel(note, 0.75, 0.50), t_hit + 0.18 + idx * 0.075, pan, 0.68)
    c = apply_reverb(c, wet=0.36, decay_sec=0.82, seed=604)
    save_wav(c, "rpg_bright_levelup.wav", 2.05)


# ============================================================
# Pack 3: オーケストラ改 (dq_fanfare)
# 硬いシンセブラスを温かいホルン＋弦＋重厚ティンパニ＋高音ベルに刷新
# ============================================================
def build_dq_improved():
    # light: ホルン＋ベルの品の良い3音確定
    c = np.zeros((2, int(SR * 1.00)))
    for i, (n, st, dur) in enumerate([(67, 0.0, 0.11), (71, 0.095, 0.11), (74, 0.19, 0.52)]):
        mix_at(c, warm_horn_section(n, dur + 0.05, 0.72), st, 0.0, 0.76)
        mix_at(c, glockenspiel(n + 12, dur + 0.1, 0.46), st, (i - 1) * 0.2, 0.66)
    mix_at(c, timpani(43, 0.38, 0.72), 0.19, 0.0, 0.74)
    c = apply_reverb(c, wet=0.36, decay_sec=0.68, seed=701)
    save_wav(c, "dq_fanfare_light.wav", 1.00)

    # heavy: 3連符＋タメ＋温かいオーケストラ解決＋ベル余韻
    c = np.zeros((2, int(SR * 1.75)))
    notes = [
        (67, 0.00, 0.095), (69, 0.095, 0.095), (71, 0.19, 0.095),
        (72, 0.29, 0.24), (74, 0.55, 0.15), (79, 0.71, 0.78),
    ]
    for n, st, dur in notes:
        mix_at(c, warm_horn_section(n, dur + 0.05, 0.76), st, 0.0, 0.78)
        mix_at(c, glockenspiel(n + 12, dur + 0.12, 0.36), st, 0.0, 0.62)
    mix_at(c, timpani(48, 0.38, 0.68), 0.29, 0.0, 0.72)
    mix_at(c, timpani(55, 0.62, 0.90), 0.71, 0.0, 0.85)
    for n in [67, 71, 74, 79]:
        mix_at(c, strings_ensemble(n, 0.85, 0.46), 0.71, 0.0, 0.70)
    # 第2波の澄んだベル余韻
    mix_at(c, glockenspiel(86, 0.55, 0.45), 0.84, -0.28, 0.64)
    mix_at(c, glockenspiel(91, 0.65, 0.48), 0.92, +0.28, 0.66)
    c = apply_reverb(c, wet=0.40, decay_sec=0.80, seed=702)
    save_wav(c, "dq_fanfare_heavy.wav", 1.75)

    # chain: 弦とホルンの爽やかな跳躍
    c = np.zeros((2, int(SR * 1.30)))
    for i, (n, st, dur) in enumerate([(72, 0.0, 0.10), (74, 0.09, 0.10), (76, 0.18, 0.10), (79, 0.28, 0.14), (84, 0.43, 0.62)]):
        mix_at(c, warm_horn_section(n - 12, dur + 0.05, 0.68), st, 0.0, 0.72)
        mix_at(c, glockenspiel(n, dur + 0.12, 0.55), st, (i - 2) * 0.16, 0.70)
    mix_at(c, timpani(48, 0.46, 0.82), 0.43, 0.0, 0.78)
    for n in [60, 64, 67, 72]:
        mix_at(c, strings_ensemble(n, 0.68, 0.42), 0.43, 0.0, 0.65)
    c = apply_reverb(c, wet=0.38, decay_sec=0.72, seed=703)
    save_wav(c, "dq_fanfare_chain.wav", 1.30)

    # levelup: 堂々たる温かいオーケストラ勝利ファンファーレ＋第2波ベル
    c = np.zeros((2, int(SR * 2.30)))
    fan = [
        (72, 0.00, 0.095), (72, 0.095, 0.095), (72, 0.19, 0.095),
        (72, 0.29, 0.22), (70, 0.53, 0.18), (74, 0.72, 0.18),
        (72, 0.92, 1.02),
    ]
    for n, st, dur in fan:
        mix_at(c, warm_horn_section(n, dur + 0.06, 0.78), st, 0.0, 0.78)
        mix_at(c, warm_horn_section(n - 12, dur + 0.06, 0.52), st, 0.0, 0.64)
        mix_at(c, glockenspiel(n + 12, dur + 0.12, 0.34), st, 0.0, 0.58)
    mix_at(c, timpani(48, 0.38, 0.76), 0.29, 0.0, 0.76)
    mix_at(c, timpani(48, 0.72, 0.96), 0.92, 0.0, 0.88)
    for n in [60, 64, 67, 72, 76]:
        mix_at(c, strings_ensemble(n, 1.12, 0.44), 0.92, 0.0, 0.68)
    for i, n in enumerate([84, 88, 91]):
        mix_at(c, glockenspiel(n, 0.80, 0.56), 1.05 + i * 0.075, (i - 1) * 0.26, 0.70)
    c = apply_reverb(c, wet=0.42, decay_sec=0.92, seed=704)
    save_wav(c, "dq_fanfare_levelup.wav", 2.30)


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    build_rpg_bright()
    build_dq_improved()
    print("Generated refined rpg_bright and dq_fanfare packs successfully")
