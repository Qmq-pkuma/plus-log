"""
DS/3DS携帯機RPGの「道具ゲット」「レベルアップ」のキレ・歯切れ・ドライな明瞭さに着目し、
リバーブのもっさり感を徹底排除した『携帯機RPG（キレ重視）』パック (handheld_rpg_*.wav) を生成する。
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


def apply_tight_room(stereo: np.ndarray, wet: float = 0.09, seed: int = 12) -> np.ndarray:
    """膨らまない極短タイトルーム残響のみ（キレを維持）"""
    rng = np.random.default_rng(seed)
    n = int(SR * 0.16)
    t = np.arange(n) / SR
    env = np.exp(-t * 32.0)
    ir_l = lowpass(rng.standard_normal(n) * env, 4800.0, 2)
    ir_r = lowpass(rng.standard_normal(n) * env, 4800.0, 2)
    norm = max(np.sqrt(np.sum(ir_l**2)), np.sqrt(np.sum(ir_r**2)), 1e-6)
    ir_l /= norm
    ir_r /= norm
    wl = fftconvolve(stereo[0], ir_l, mode="full")
    wr = fftconvolve(stereo[1], ir_r, mode="full")
    out_n = max(stereo.shape[1], len(wl))
    out = np.zeros((2, out_n), dtype=np.float64)
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


# --- 携帯機RPG用の輪郭クッキリ音源 ---
def ds_lead_horn(midi_note: float, dur: float, vel: float = 1.0) -> np.ndarray:
    """DS/3DSのアイテムゲット・LvUP主旋律のような芯のある明るいリードブラス"""
    f = midi_to_hz(midi_note)
    n = int(SR * dur)
    t = np.arange(n) / SR
    atk = np.minimum(1.0, t / 0.003)  # 超高速アタックでキレを出す
    rel = np.minimum(1.0, np.maximum(0.0, (dur - t) / 0.018))
    # パルス波＋ノコギリ波の中間的な明瞭な倍音
    sig = np.zeros(n)
    for k, amp in [(1, 1.0), (2, 0.58), (3, 0.42), (4, 0.24), (5, 0.16), (6, 0.08)]:
        if f * k >= SR * 0.44:
            break
        sig += amp * np.sin(2 * np.pi * f * k * t)
    # 立ち上がりだけ少し明るくしてパキッとさせる
    bite = np.sin(2 * np.pi * f * 2.0 * t) * np.exp(-t * 55.0) * 0.35
    sig = lowpass((sig + bite) * atk * rel, 5600.0, 2)
    return sig * vel


def ds_bell(midi_note: float, dur: float, vel: float = 1.0) -> np.ndarray:
    """輪郭のくっきりした高音ベル（道具ゲットのキラッ）"""
    f = midi_to_hz(midi_note)
    n = int(SR * dur)
    t = np.arange(n) / SR
    atk = np.minimum(1.0, t / 0.001)
    sig = (
        1.00 * np.sin(2 * np.pi * f * t) * np.exp(-t * (5.2 / dur))
        + 0.42 * np.sin(2 * np.pi * f * 2.0 * t) * np.exp(-t * (8.5 / dur))
        + 0.22 * np.sin(2 * np.pi * f * 3.0 * t) * np.exp(-t * (14.0 / dur))
    ) * atk
    return sig * vel


def ds_bass(midi_note: float, dur: float, vel: float = 1.0) -> np.ndarray:
    """締まった携帯機PCMベース"""
    f = midi_to_hz(midi_note)
    n = int(SR * dur)
    t = np.arange(n) / SR
    atk = np.minimum(1.0, t / 0.003)
    rel = np.minimum(1.0, np.maximum(0.0, (dur - t) / 0.02))
    sig = (np.sin(2 * np.pi * f * t) + 0.45 * np.sin(2 * np.pi * f * 2.0 * t) + 0.18 * np.sin(2 * np.pi * f * 3.0 * t))
    return lowpass(sig * atk * rel, 1100.0, 2) * vel


def tight_snare(vel: float = 1.0, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(SR * 0.065)
    t = np.arange(n) / SR
    body = np.sin(2 * np.pi * 220 * t) * np.exp(-t * 60.0) * 0.5
    snap = highpass(rng.standard_normal(n) * np.exp(-t * 55.0), 2200.0, 2) * 0.7
    return (body + snap) * vel


def save_wav(stereo: np.ndarray, filename: str, max_dur_sec: float | None = None) -> None:
    if max_dur_sec is not None:
        max_n = int(SR * max_dur_sec)
        if stereo.shape[1] > max_n:
            stereo = stereo[:, :max_n].copy()
            fade = int(SR * 0.025)
            stereo[:, -fade:] *= np.linspace(1.0, 0.0, fade)

    stereo = np.vstack([highpass(stereo[0], 40.0, 2), highpass(stereo[1], 40.0, 2)])
    peak = np.max(np.abs(stereo))
    if peak > 1e-6:
        stereo = stereo / peak
    stereo = np.tanh(stereo * 1.15) / np.tanh(1.15) * 0.90

    mag = np.max(np.abs(stereo), axis=0)
    nz = np.where(mag > 0.0015)[0]
    if len(nz) > 0:
        stereo = stereo[:, : min(stereo.shape[1], int(nz[-1]) + int(SR * 0.02))]

    pcm = np.clip(stereo.T * 32767.0, -32768, 32767).astype(np.int16)
    with wave.open(os.path.join(OUT_DIR, filename), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())


# 1. light (+3〜5pt): キビキビした2音上昇チャイム (0.48s)
def build_light():
    c = np.zeros((2, int(SR * 0.55)))
    mix_at(c, ds_bell(76, 0.14, 0.85), 0.00, -0.1, 0.85)
    mix_at(c, ds_lead_horn(64, 0.08, 0.45), 0.00, 0.0, 0.65)
    mix_at(c, ds_bell(83, 0.36, 0.95), 0.08, +0.1, 0.90)
    mix_at(c, ds_lead_horn(71, 0.24, 0.55), 0.08, 0.0, 0.72)
    mix_at(c, ds_bass(52, 0.24, 0.55), 0.08, 0.0, 0.68)
    c = apply_tight_room(c, wet=0.08, seed=101)
    save_wav(c, "handheld_rpg_light.wav", 0.55)


# 2. heavy (+10pt お風呂): 「道具ゲット！」着想の歯切れ良いリズミカルファンファーレ (1.05s)
def build_heavy():
    c = np.zeros((2, int(SR * 1.15)))
    # キビキビした16分〜8分の跳ねるリズム「タ・タタ・タッ・ターン！」
    # オリジナル音型 (Gメジャー: B4-D5-D5-E5-G5!)
    mel = [
        (71, 0.000, 0.075),
        (74, 0.085, 0.065),
        (74, 0.155, 0.065),
        (76, 0.230, 0.095),
        (79, 0.340, 0.540),
    ]
    for i, (n, st, dur) in enumerate(mel):
        mix_at(c, ds_lead_horn(n, dur, 0.85), st, 0.0, 0.82)
        mix_at(c, ds_bell(n + 12, dur + 0.08, 0.62), st, (i - 2) * 0.12, 0.72)
    # 締まったベース＋ハモリ＋スネア
    mix_at(c, ds_bass(55, 0.14, 0.70), 0.00, 0.0, 0.75)
    mix_at(c, ds_bass(57, 0.10, 0.72), 0.23, 0.0, 0.75)
    mix_at(c, ds_bass(55, 0.52, 0.82), 0.34, 0.0, 0.80)
    mix_at(c, ds_lead_horn(71, 0.50, 0.52), 0.34, -0.25, 0.68)
    mix_at(c, ds_lead_horn(74, 0.50, 0.52), 0.34, +0.25, 0.68)
    mix_at(c, tight_snare(0.35, seed=11), 0.085, 0.0, 0.7)
    mix_at(c, tight_snare(0.45, seed=12), 0.340, 0.0, 0.78)
    c = apply_tight_room(c, wet=0.09, seed=102)
    save_wav(c, "handheld_rpg_heavy.wav", 1.15)


# 3. chain (連動): パキッと決まるコンボ取得フレーズ (0.85s)
def build_chain():
    c = np.zeros((2, int(SR * 0.92)))
    mel = [(74, 0.00, 0.07), (78, 0.075, 0.07), (81, 0.15, 0.07), (86, 0.23, 0.48)]
    for i, (n, st, dur) in enumerate(mel):
        mix_at(c, ds_bell(n, dur + 0.08, 0.88), st, (i - 1.5) * 0.15, 0.85)
        mix_at(c, ds_lead_horn(n - 12, dur, 0.68), st, 0.0, 0.75)
    mix_at(c, ds_bass(50, 0.45, 0.75), 0.23, 0.0, 0.78)
    mix_at(c, tight_snare(0.38, seed=13), 0.23, 0.0, 0.75)
    c = apply_tight_room(c, wet=0.09, seed=103)
    save_wav(c, "handheld_rpg_chain.wav", 0.92)


# 4. levelup: 「レベルアップおめでとう！」着想の歯切れ抜群ファンファーレ (1.45s)
def build_levelup():
    c = np.zeros((2, int(SR * 1.55)))
    # 歯切れのよい連打＋跳躍「タタタ・タ・タ・ターン！」(C5-C5-C5 -> G4 -> B4 -> C5/E5/G5!)
    mel = [
        (72, 0.000, 0.070),
        (72, 0.080, 0.070),
        (72, 0.160, 0.070),
        (72, 0.245, 0.120),
        (74, 0.375, 0.105),
        (76, 0.490, 0.105),
        (79, 0.610, 0.720),
    ]
    for i, (n, st, dur) in enumerate(mel):
        mix_at(c, ds_lead_horn(n, dur, 0.88), st, 0.0, 0.84)
        mix_at(c, ds_bell(n + 12, dur + 0.08, 0.65), st, (i - 3) * 0.08, 0.74)
        if i in (0, 1, 2, 3, 6):
            mix_at(c, tight_snare(0.50 if i == 6 else 0.28, seed=20 + i), st, 0.0, 0.78)

    # フィニッシュ和音 (0.61s): パキッと力強く解決！
    t_fin = 0.610
    mix_at(c, ds_bass(48, 0.72, 0.88), t_fin, 0.0, 0.85)
    for n, pan in [(64, -0.3), (67, 0.0), (72, +0.3)]:
        mix_at(c, ds_lead_horn(n, 0.68, 0.56), t_fin, pan, 0.72)
    # 最後のキラッ2音
    mix_at(c, ds_bell(88, 0.32, 0.55), t_fin + 0.14, -0.25, 0.70)
    mix_at(c, ds_bell(91, 0.42, 0.60), t_fin + 0.22, +0.25, 0.72)

    c = apply_tight_room(c, wet=0.10, seed=104)
    save_wav(c, "handheld_rpg_levelup.wav", 1.55)


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    build_light()
    build_heavy()
    build_chain()
    build_levelup()
    print("Generated tight handheld_rpg pack successfully")
