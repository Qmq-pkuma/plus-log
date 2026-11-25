"""
任天堂・ポケモン系RPGの報酬構造（リズムの繰り返し・和声解決・マルチトラック楽器・余韻）
にインスパイアされたオリジナル報酬ジングル＆経験値カウント音を生成するスクリプト。
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


# --- 楽器音源 ---
def glockenspiel(midi_note: float, dur: float, vel: float = 1.0) -> np.ndarray:
    """澄んだ任天堂系グロッケン（鉄琴・ベル）"""
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


def warm_epiano(midi_note: float, dur: float, vel: float = 1.0) -> np.ndarray:
    """温かいローズ／エレピ風和音楽器（ポケモンセンター回復の土台感）"""
    f = midi_to_hz(midi_note)
    n = int(SR * dur)
    t = np.arange(n) / SR
    atk = np.minimum(1.0, t / 0.006)
    rel = np.minimum(1.0, np.maximum(0.0, (dur - t) / 0.06))
    # 軽いFMタイン成分 + 温かい基音
    mod = 1.4 * np.exp(-t * 14.0) * np.sin(2 * np.pi * f * 2.0 * t)
    sig = (
        0.78 * np.sin(2 * np.pi * f * t + mod)
        + 0.25 * np.sin(2 * np.pi * f * 2.0 * t) * np.exp(-t * 5.5)
        + 0.10 * np.sin(2 * np.pi * f * 3.0 * t) * np.exp(-t * 9.0)
    ) * np.exp(-t * (2.6 / dur)) * atk * rel
    return lowpass(sig, 4200.0, 2) * vel


def bright_brass(midi_note: float, dur: float, vel: float = 1.0) -> np.ndarray:
    """RPGファンファーレ用の明るいブラス・シンセ"""
    f = midi_to_hz(midi_note)
    n = int(SR * dur)
    t = np.arange(n) / SR
    atk = np.minimum(1.0, t / 0.014)
    rel = np.minimum(1.0, np.maximum(0.0, (dur - t) / 0.05))
    # わずかにデチューンした2本のノコギリ波風倍音
    l = np.zeros(n)
    r = np.zeros(n)
    for k in range(1, 7):
        if f * k >= SR * 0.42:
            break
        amp = 1.0 / (k ** 1.15)
        l += amp * np.sin(2 * np.pi * (f * 0.997) * k * t)
        r += amp * np.sin(2 * np.pi * (f * 1.003) * k * t)
    env = atk * rel * (0.85 + 0.15 * np.exp(-t * 6.0))
    l = lowpass(l * env, 3600.0, 2) * vel
    r = lowpass(r * env, 3600.0, 2) * vel
    return np.vstack([l, r])


def warm_bass(midi_note: float, dur: float, vel: float = 1.0) -> np.ndarray:
    """下を支える丸いベース"""
    f = midi_to_hz(midi_note)
    n = int(SR * dur)
    t = np.arange(n) / SR
    atk = np.minimum(1.0, t / 0.008)
    rel = np.minimum(1.0, np.maximum(0.0, (dur - t) / 0.06))
    sig = (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * f * 2.0 * t)) * atk * rel * np.exp(-t * (2.2 / dur))
    return lowpass(np.tanh(sig * 1.2), 750.0, 2) * vel


def soft_shaker_hit(vel: float = 1.0, seed: int = 5) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(SR * 0.045)
    t = np.arange(n) / SR
    noise = rng.standard_normal(n) * np.exp(-t * 85.0)
    return highpass(noise, 3200.0, 2) * vel


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


# 1. 軽めタスク (+3〜5pt): 軽快な3音上昇＋温かい和音着地 (約0.75秒)
def build_light():
    c = np.zeros((2, int(SR * 0.95)))
    # D5 -> F#5 -> A5 (リズミカルな「タ・タ・ターン」)
    melody = [(74, 0.00, 0.16, -0.15), (78, 0.095, 0.18, 0.0), (81, 0.19, 0.48, 0.15)]
    for note, st, dur, pan in melody:
        mix_at(c, glockenspiel(note, dur, 0.72), st, pan, 0.85)
        mix_at(c, warm_epiano(note - 12, dur + 0.1, 0.55), st, -pan * 0.5, 0.75)
    # 着地和音 (D major add9)
    for note, pan in [(62, -0.25), (66, 0.0), (69, 0.25), (76, 0.1)]:
        mix_at(c, warm_epiano(note, 0.52, 0.42), 0.19, pan, 0.65)
    mix_at(c, warm_bass(50, 0.45, 0.55), 0.19, 0.0, 0.7)
    c = apply_reverb(c, wet=0.28, decay_sec=0.52, seed=11)
    save_wav(c, "rpg_poke_light.wav", 0.95)


# 2. 重めタスク (+10pt・お風呂など): ポケモンセンター回復風のリズミカル5音解決フレーズ (約1.4秒)
def build_heavy():
    c = np.zeros((2, int(SR * 1.7)))
    # リズム「タ・タ・タラ・ラーン♪」 (オリジナル音型: E5 - E5 - E5 - C#5 -> A5解決)
    # 温かいAメジャー進行で「ホッとする＋達成感」
    steps = [
        (76, 0.00, 0.18, -0.18, 0.85),  # E5
        (76, 0.19, 0.18, +0.18, 0.88),  # E5 (同じ音の繰り返し！)
        (76, 0.38, 0.14, -0.12, 0.90),  # E5
        (73, 0.51, 0.15, +0.12, 0.85),  # C#5 (一瞬下がるタメ)
        (81, 0.67, 0.75,  0.00, 1.00),  # A5 (明るく解決！)
    ]
    for note, st, dur, pan, vel in steps:
        mix_at(c, glockenspiel(note, dur + 0.12, vel), st, pan, 0.78)
        mix_at(c, warm_epiano(note - 12, dur + 0.15, vel * 0.7), st, -pan * 0.5, 0.72)

    # 解決ポイント(0.67s)で広がる温かいAメジャー9th和音＋キラキラ余韻
    for idx, (note, pan) in enumerate([(57, -0.3), (64, -0.12), (68, 0.12), (73, 0.3)]):
        mix_at(c, warm_epiano(note, 0.85, 0.5), 0.67 + idx * 0.012, pan, 0.62)
    mix_at(c, warm_bass(45, 0.8, 0.65), 0.67, 0.0, 0.72)
    # 余韻のキラキラ2音
    mix_at(c, glockenspiel(85, 0.48, 0.42), 0.80, -0.35, 0.6)
    mix_at(c, glockenspiel(88, 0.55, 0.38), 0.88, +0.35, 0.58)

    c = apply_reverb(c, wet=0.34, decay_sec=0.72, seed=22)
    save_wav(c, "rpg_poke_heavy.wav", 1.7)


# 3. 連動タスク（お風呂→保湿剤など）: アイテム入手風の跳ねる4音フレーズ (約1.05秒)
def build_chain():
    c = np.zeros((2, int(SR * 1.25)))
    # 軽快に跳ねる「タタタ・ターン♪」 (G5 -> A5 -> B5 -> D6)
    steps = [
        (79, 0.00, 0.13, -0.25, 0.82),
        (81, 0.09, 0.13, -0.08, 0.86),
        (83, 0.18, 0.14, +0.08, 0.90),
        (86, 0.29, 0.68, +0.20, 1.00),
    ]
    for note, st, dur, pan, vel in steps:
        mix_at(c, glockenspiel(note, dur + 0.1, vel), st, pan, 0.82)
        mix_at(c, warm_epiano(note - 12, dur + 0.12, vel * 0.65), st, -pan * 0.5, 0.68)
    for note, pan in [(67, -0.3), (71, 0.0), (74, 0.3)]:
        mix_at(c, warm_epiano(note, 0.7, 0.48), 0.29, pan, 0.65)
    mix_at(c, warm_bass(55, 0.65, 0.6), 0.29, 0.0, 0.7)
    mix_at(c, soft_shaker_hit(0.35, seed=31), 0.29, 0.0, 0.7)
    c = apply_reverb(c, wet=0.33, decay_sec=0.62, seed=33)
    save_wav(c, "rpg_poke_chain.wav", 1.25)


# 4. レベルアップ: 2段階構成のRPGレベルアップ・ファンファーレ (約1.95秒)
def build_levelup():
    c = np.zeros((2, int(SR * 2.2)))
    # 前半：勢いのある繰り返し＋駆け上がり「タタタ・タッ！」(F5-F5-F5 -> G5 -> A5 -> C6)
    intro = [
        (77, 0.00, 0.10, -0.2, 0.85),
        (77, 0.10, 0.10, +0.2, 0.88),
        (77, 0.20, 0.10, -0.1, 0.92),
        (79, 0.32, 0.12, +0.1, 0.90),
        (81, 0.44, 0.13, -0.15, 0.95),
    ]
    for note, st, dur, pan, vel in intro:
        mix_at(c, bright_brass(note - 12, dur + 0.04, vel * 0.65), st, 0.0, 0.7)
        mix_at(c, glockenspiel(note, dur + 0.08, vel * 0.85), st, pan, 0.75)
        mix_at(c, soft_shaker_hit(0.28, seed=int(note)), st, pan, 0.6)

    # 後半(0.58s)：一瞬のタメから華やかに広がる勝利和音「タラーーーン！！」+ キラキラ追撃
    t_hit = 0.58
    mix_at(c, warm_bass(53, 1.25, 0.85), t_hit, 0.0, 0.82)  # F3
    for note, pan in [(65, -0.35), (69, -0.12), (72, +0.12), (77, +0.35)]:
        mix_at(c, bright_brass(note, 1.15, 0.52), t_hit, 0.0, 0.65)
        mix_at(c, warm_epiano(note, 1.2, 0.48), t_hit, pan, 0.58)
    mix_at(c, glockenspiel(84, 1.1, 0.95), t_hit, 0.0, 0.82)  # C6
    # その後を追うキラキラ余韻（深みの第2波！）
    for idx, (note, pan) in enumerate([(86, -0.3), (89, 0.0), (93, +0.3)]):
        mix_at(c, glockenspiel(note, 0.75, 0.52), t_hit + 0.20 + idx * 0.075, pan, 0.68)

    c = apply_reverb(c, wet=0.38, decay_sec=0.88, seed=44)
    save_wav(c, "rpg_poke_levelup.wav", 2.15)


# 5. 経験値ゲージ上昇中の連続カウント音（約0.26秒）
def build_exp_tick():
    c = np.zeros((2, int(SR * 0.30)))
    # 6粒のピッチが駆け上がる軽い経験値カウント音
    for i in range(6):
        note = 72 + i * 2
        mix_at(c, glockenspiel(note, 0.065, 0.55 + i * 0.05), i * 0.036, (i - 2.5) * 0.1, 0.65)
    c = apply_reverb(c, wet=0.18, decay_sec=0.22, seed=55)
    save_wav(c, "exp_tick.wav", 0.30)


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    build_light()
    build_heavy()
    build_chain()
    build_levelup()
    build_exp_tick()
    print("Generated RPG jingles & exp_tick successfully")
