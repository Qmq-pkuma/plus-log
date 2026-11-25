"""
「王道RPG」を超えるための新作2パック生成スクリプト (44.1kHz / 16bit / Stereo):
  1. ds_exp       : DS/3DS世代ポケモン着想（経験値流入グリッサンド＋澄んだ確定チャイム＋華やかLvUP）
  2. genshin_open : 原神等のオープンワールドRPG着想（澄んだピアノ＆ハープのステレオアルペジオ＋星屑シマー＋深い空間残響）
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


def make_reverb(decay_sec: float, damping_hz: float, seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    n = int(SR * decay_sec)
    t = np.arange(n) / SR
    env = np.exp(-t * (5.5 / decay_sec))
    l = rng.standard_normal(n) * env
    r = rng.standard_normal(n) * env
    for ms, al, ar in [(13, 0.45, 0.20), (24, 0.20, 0.44), (37, 0.32, 0.26), (53, 0.22, 0.30)]:
        idx = int(SR * ms / 1000)
        if idx < n:
            l[idx] += al
            r[idx] += ar
    l = lowpass(l, damping_hz, 2)
    r = lowpass(r, damping_hz, 2)
    fade = min(int(SR * 0.01), n)
    l[:fade] *= np.linspace(0, 1, fade)
    r[:fade] *= np.linspace(0, 1, fade)
    norm = max(np.sqrt(np.sum(l**2)), np.sqrt(np.sum(r**2)), 1e-6)
    return l / norm, r / norm


def apply_reverb(stereo: np.ndarray, wet: float, decay_sec: float, damping_hz: float = 6200.0, seed: int = 99) -> np.ndarray:
    ir_l, ir_r = make_reverb(decay_sec, damping_hz, seed)
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
# 高品質インストゥルメント
# ============================================================
def crystal_bell(midi_note: float, dur: float, vel: float = 1.0) -> np.ndarray:
    """DS/3DS・原神系の澄んだクリスタルベル／チェレスタ"""
    f = midi_to_hz(midi_note)
    n = int(SR * dur)
    t = np.arange(n) / SR
    atk = np.minimum(1.0, t / 0.0018)
    sig = (
        1.00 * np.sin(2 * np.pi * f * t) * np.exp(-t * (3.8 / dur))
        + 0.36 * np.sin(2 * np.pi * f * 2.001 * t) * np.exp(-t * (6.5 / dur))
        + 0.22 * np.sin(2 * np.pi * f * 2.756 * t) * np.exp(-t * (11.0 / dur))
        + 0.12 * np.sin(2 * np.pi * f * 5.404 * t) * np.exp(-t * (18.0 / dur))
    ) * atk
    return sig * vel


def grand_piano(midi_note: float, dur: float, vel: float = 1.0) -> np.ndarray:
    """透明感とハンマーの芯があるアコースティック・ピアノ風音源"""
    f = midi_to_hz(midi_note)
    n = int(SR * dur)
    t = np.arange(n) / SR
    atk = np.minimum(1.0, t / 0.003)
    rel = np.minimum(1.0, np.maximum(0.0, (dur - t) / 0.09))
    # ピアノのインハーモニシティ（わずかに高次倍音がシャープ）を再現
    B = 0.00022
    l = np.zeros(n)
    r = np.zeros(n)
    weights = [(1, 1.00, 2.2), (2, 0.56, 3.4), (3, 0.30, 5.2), (4, 0.16, 7.5), (5, 0.08, 10.5), (6, 0.04, 14.0)]
    for k, amp, dec in weights:
        fk = f * k * np.sqrt(1.0 + B * k * k)
        if fk >= SR * 0.44:
            break
        env = np.exp(-t * (dec / dur))
        # ユニゾン弦のわずかなデチューンで生ピアノの艶を作る
        l += amp * env * np.sin(2 * np.pi * (fk * 0.9992) * t)
        r += amp * env * np.sin(2 * np.pi * (fk * 1.0008) * t)
    l = lowpass(l * atk * rel, 5800.0, 2) * vel
    r = lowpass(r * atk * rel, 5800.0, 2) * vel
    return np.vstack([l, r])


def concert_harp(midi_note: float, dur: float, vel: float = 1.0, seed: int = 7) -> np.ndarray:
    """原神の探索・任務完了のような澄んだコンサートハープ"""
    f = midi_to_hz(midi_note)
    rng = np.random.default_rng(seed)
    n = int(SR * dur)
    delay = max(2, int(round(SR / f)))
    buf = lowpass(rng.standard_normal(delay), min(9200.0, f * 8.0), 2)
    out = np.zeros(n)
    decay = 0.9978 if f < 550 else 0.9962
    for i in range(n):
        v = buf[i % delay]
        out[i] = v
        buf[i % delay] = 0.5 * (v + buf[(i + 1) % delay]) * decay
    t = np.arange(n) / SR
    out *= np.exp(-t * (2.2 / dur))
    # 澄んだ基音ボディを薄く重ねて太さを補う
    body = np.sin(2 * np.pi * f * t) * np.exp(-t * (3.2 / dur)) * np.minimum(1.0, t / 0.002) * 0.22
    return (highpass(out, 110.0) * 0.85 + body) * vel


def ethereal_pad(midi_note: float, dur: float, vel: float = 1.0) -> np.ndarray:
    """オープンワールドRPGの壮大な弦＋クワイア風の温かい広がり"""
    f = midi_to_hz(midi_note)
    n = int(SR * dur)
    t = np.arange(n) / SR
    atk = np.minimum(1.0, t / 0.14) ** 1.2
    rel = np.minimum(1.0, np.maximum(0.0, (dur - t) / 0.35))
    l = np.zeros(n)
    r = np.zeros(n)
    for k, amp in [(1, 1.0), (2, 0.42), (3, 0.18), (4, 0.07)]:
        if f * k >= SR * 0.4:
            break
        vib = 0.0028 * np.sin(2 * np.pi * 4.6 * t + k)
        l += amp * np.sin(2 * np.pi * f * (0.995 + vib) * k * t)
        r += amp * np.sin(2 * np.pi * f * (1.005 - vib) * k * t)
    env = atk * rel
    return np.vstack([lowpass(l * env, 2100.0, 2) * vel, lowpass(r * env, 2100.0, 2) * vel])


def ds_exp_stream(start_midi: float, end_midi: float, dur: float, steps: int, vel: float = 1.0) -> np.ndarray:
    """DS/3DS世代ポケモンの「経験値がゲージへ流れ込む」滑らかな上昇音"""
    n = int(SR * (dur + 0.08))
    c = np.zeros((2, n))
    notes = np.linspace(start_midi, end_midi, steps)
    dt = dur / max(1, steps)
    for i, m in enumerate(notes):
        st = i * dt
        f = midi_to_hz(m)
        ln = int(SR * max(0.045, dt * 2.1))
        t = np.arange(ln) / SR
        atk = np.minimum(1.0, t / 0.0015)
        # クリアなDS音源風のサイン＋2倍音＋微細なトライアングル
        sig = (
            0.78 * np.sin(2 * np.pi * f * t)
            + 0.25 * np.sin(2 * np.pi * f * 2.0 * t)
            + 0.10 * np.sin(2 * np.pi * f * 3.0 * t)
        ) * np.exp(-t * 28.0) * atk * vel * (0.65 + 0.35 * (i / max(1, steps - 1)))
        pan = -0.25 + 0.5 * (i / max(1, steps - 1))
        mix_at(c, sig, st, pan, 0.8)
    return c


def warm_epiano(midi_note: float, dur: float, vel: float = 1.0) -> np.ndarray:
    f = midi_to_hz(midi_note)
    n = int(SR * dur)
    t = np.arange(n) / SR
    atk = np.minimum(1.0, t / 0.004)
    rel = np.minimum(1.0, np.maximum(0.0, (dur - t) / 0.06))
    mod = 1.4 * np.exp(-t * 14.0) * np.sin(2 * np.pi * f * 2.0 * t)
    sig = (
        0.80 * np.sin(2 * np.pi * f * t + mod)
        + 0.24 * np.sin(2 * np.pi * f * 2.0 * t) * np.exp(-t * 5.2)
    ) * np.exp(-t * (2.6 / dur)) * atk * rel
    return lowpass(sig, 4300.0, 2) * vel


def warm_bass(midi_note: float, dur: float, vel: float = 1.0) -> np.ndarray:
    f = midi_to_hz(midi_note)
    n = int(SR * dur)
    t = np.arange(n) / SR
    atk = np.minimum(1.0, t / 0.008)
    rel = np.minimum(1.0, np.maximum(0.0, (dur - t) / 0.08))
    sig = (np.sin(2 * np.pi * f * t) + 0.32 * np.sin(2 * np.pi * f * 2.0 * t)) * atk * rel * np.exp(-t * (2.0 / dur))
    return lowpass(np.tanh(sig * 1.15), 680.0, 2) * vel


def star_shimmer(notes: list[float], start_sec: float, step_sec: float = 0.055, vel: float = 0.42) -> np.ndarray:
    """原神風の星が瞬く高域ウィンドチャイム余韻"""
    total = start_sec + len(notes) * step_sec + 0.75
    c = np.zeros((2, int(SR * total)))
    for i, m in enumerate(notes):
        pan = -0.45 + 0.9 * (i / max(1, len(notes) - 1))
        mix_at(c, crystal_bell(m, 0.58, vel * (0.8 + 0.2 * (i % 2))), start_sec + i * step_sec, pan, 0.72)
    return c


def save_wav(stereo: np.ndarray, filename: str, max_dur_sec: float | None = None) -> None:
    if max_dur_sec is not None:
        max_n = int(SR * max_dur_sec)
        if stereo.shape[1] > max_n:
            stereo = stereo[:, :max_n].copy()
            fade = int(SR * 0.06)
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
# Pack A: DS/3DS 経験値・キラキラ育成系 (ds_exp)
# 経験値がゲージへ流れ込む連続上昇音 → キラッと確定チャイムの2段快感
# ============================================================
def build_ds_exp():
    # light: 短い経験値流入(0.16s) -> キラッと確定2音
    c = np.zeros((2, int(SR * 0.95)))
    mix_at(c, ds_exp_stream(69, 81, 0.16, 7, 0.72), 0.0, 0.0, 0.85)
    mix_at(c, crystal_bell(81, 0.45, 0.88), 0.17, -0.1, 0.85)
    mix_at(c, crystal_bell(88, 0.52, 0.72), 0.22, +0.15, 0.80)
    for n, pan in [(64, -0.2), (69, 0.0), (73, 0.2)]:
        mix_at(c, warm_epiano(n, 0.48, 0.42), 0.17, pan, 0.65)
    c = apply_reverb(c, wet=0.28, decay_sec=0.52, seed=801)
    save_wav(c, "ds_exp_light.wav", 0.95)

    # heavy (+10 お風呂): たっぷり経験値が溜まる上昇流(0.28s) -> 満タン達成の3音解決＋星屑余韻！
    c = np.zeros((2, int(SR * 1.65)))
    mix_at(c, ds_exp_stream(64, 83, 0.28, 12, 0.78), 0.0, 0.0, 0.88)
    # 満タン着地 + 明るい3音確定フレーズ
    t_land = 0.30
    mix_at(c, warm_bass(45, 0.92, 0.70), t_land, 0.0, 0.76)
    for idx, (n, st, pan) in enumerate([(81, t_land, -0.18), (85, t_land + 0.10, +0.18), (88, t_land + 0.21, 0.0)]):
        dur = 0.18 if idx < 2 else 0.78
        mix_at(c, crystal_bell(n, dur + 0.1, 0.95), st, pan, 0.86)
        mix_at(c, warm_epiano(n - 12, dur + 0.15, 0.65), st, -pan * 0.5, 0.74)
    for n, pan in [(57, -0.3), (64, -0.1), (69, 0.1), (73, 0.3)]:
        mix_at(c, warm_epiano(n, 0.82, 0.45), t_land + 0.21, pan, 0.62)
    mix_at(c, star_shimmer([93, 97, 100], 0.0, 0.06, 0.38), t_land + 0.36, 0.0, 0.78)
    c = apply_reverb(c, wet=0.34, decay_sec=0.70, seed=802)
    save_wav(c, "ds_exp_heavy.wav", 1.65)

    # chain (連動): 2段跳ねの経験値流入 -> 爽快コンボ着地
    c = np.zeros((2, int(SR * 1.25)))
    mix_at(c, ds_exp_stream(67, 79, 0.14, 6, 0.75), 0.0, 0.0, 0.82)
    mix_at(c, ds_exp_stream(74, 86, 0.14, 6, 0.82), 0.15, 0.0, 0.88)
    mix_at(c, crystal_bell(86, 0.68, 0.95), 0.30, 0.0, 0.88)
    for n, pan in [(62, -0.25), (67, 0.0), (71, 0.25), (74, 0.1)]:
        mix_at(c, warm_epiano(n, 0.65, 0.48), 0.30, pan, 0.68)
    mix_at(c, warm_bass(55, 0.60, 0.65), 0.30, 0.0, 0.72)
    mix_at(c, star_shimmer([91, 95], 0.0, 0.055, 0.40), 0.40, 0.0, 0.76)
    c = apply_reverb(c, wet=0.33, decay_sec=0.62, seed=803)
    save_wav(c, "ds_exp_chain.wav", 1.25)

    # levelup: DS/3DS世代の華やかさ全開レベルアップ！（高速上昇＋繰り返し＋輝く和音＋星屑シャワー）
    c = np.zeros((2, int(SR * 2.25)))
    # 軽快な駆け上がり繰り返し「タタタ・タッ！」
    seq = [(76, 0.00, 0.09), (76, 0.09, 0.09), (76, 0.18, 0.09), (79, 0.28, 0.11), (83, 0.39, 0.13)]
    for i, (n, st, dur) in enumerate(seq):
        pan = (i - 2) * 0.16
        mix_at(c, crystal_bell(n, dur + 0.09, 0.90), st, pan, 0.84)
        mix_at(c, warm_epiano(n - 12, dur + 0.12, 0.70), st, -pan * 0.5, 0.75)
        mix_at(c, grand_piano(n - 12, dur + 0.15, 0.55), st, 0.0, 0.68)
    # 頂点着地 (0.54s): Cメジャー9thの晴れやかな輝き！
    t_hit = 0.54
    mix_at(c, warm_bass(48, 1.35, 0.82), t_hit, 0.0, 0.82)
    for n in [60, 64, 67, 71, 74]:
        mix_at(c, grand_piano(n, 1.25, 0.48), t_hit, 0.0, 0.68)
        mix_at(c, ethereal_pad(n, 1.35, 0.34), t_hit, 0.0, 0.60)
    mix_at(c, crystal_bell(84, 1.15, 0.96), t_hit, 0.0, 0.88)
    # 星屑の追撃シャワー
    mix_at(c, star_shimmer([88, 91, 95, 96], 0.0, 0.065, 0.45), t_hit + 0.16, 0.0, 0.82)
    c = apply_reverb(c, wet=0.38, decay_sec=0.88, seed=804)
    save_wav(c, "ds_exp_levelup.wav", 2.25)


# ============================================================
# Pack B: オープンワールドRPG・任務達成系 (genshin_open)
# 原神着想：澄んだピアノ＆ハープのステレオアルペジオ＋星屑シマー＋深い空間残響
# ============================================================
def build_genshin():
    # light: 探索発見・アイテム拾得の透明感あるピアノ＆ハープ
    c = np.zeros((2, int(SR * 1.25)))
    # Dmaj9 の澄んだ2音＋ハープさざ波
    mix_at(c, concert_harp(74, 0.65, 0.78, seed=901), 0.00, -0.28, 0.80)
    mix_at(c, concert_harp(78, 0.68, 0.80, seed=902), 0.055, 0.00, 0.82)
    mix_at(c, concert_harp(81, 0.75, 0.84, seed=903), 0.11, +0.28, 0.85)
    mix_at(c, grand_piano(62, 0.85, 0.55), 0.00, 0.0, 0.70)
    mix_at(c, grand_piano(74, 0.85, 0.62), 0.11, 0.0, 0.75)
    mix_at(c, crystal_bell(90, 0.60, 0.42), 0.16, +0.22, 0.65)
    c = apply_reverb(c, wet=0.44, decay_sec=0.82, damping_hz=6800.0, seed=911)
    save_wav(c, "genshin_open_light.wav", 1.25)

    # heavy (+10 お風呂): デイリー依頼完了・宝箱オープン風のステレオハープ大アルペジオ＋温かい和音！
    c = np.zeros((2, int(SR * 2.05)))
    # L -> R へ美しく駆け上がるハープアルペジオ (Gmaj9)
    arp = [62, 67, 71, 74, 78, 81, 83, 86]
    for i, n in enumerate(arp):
        st = i * 0.052
        pan = -0.45 + 0.9 * (i / (len(arp) - 1))
        mix_at(c, concert_harp(n, 0.95, 0.85, seed=920 + i), st, pan, 0.82)
    # アルペジオ頂点(0.40s)で生ピアノと壮大な弦パッドがふわっと広がる！
    t_bloom = 0.40
    mix_at(c, warm_bass(43, 1.35, 0.72), t_bloom, 0.0, 0.76)
    for n in [55, 62, 67, 71, 74]:
        mix_at(c, ethereal_pad(n, 1.40, 0.36), t_bloom, 0.0, 0.64)
    mix_at(c, grand_piano(74, 1.15, 0.72), t_bloom, 0.0, 0.78)
    mix_at(c, grand_piano(78, 1.15, 0.66), t_bloom + 0.04, 0.0, 0.72)
    mix_at(c, grand_piano(83, 1.20, 0.75), t_bloom + 0.18, 0.0, 0.80)
    # 星屑シマー余韻
    mix_at(c, star_shimmer([86, 90, 95, 98], 0.0, 0.07, 0.38), t_bloom + 0.22, 0.0, 0.78)
    c = apply_reverb(c, wet=0.48, decay_sec=1.05, damping_hz=6600.0, seed=912)
    save_wav(c, "genshin_open_heavy.wav", 2.05)

    # chain (連動): ワープ解放・元素共鳴風の透明感ある5度跳躍＆クリスタル
    c = np.zeros((2, int(SR * 1.55)))
    for i, n in enumerate([69, 76, 81, 85, 88]):
        st = i * 0.06
        pan = -0.35 + i * 0.175
        mix_at(c, concert_harp(n, 0.85, 0.82, seed=940 + i), st, pan, 0.80)
        mix_at(c, crystal_bell(n, 0.65, 0.55), st + 0.01, -pan * 0.5, 0.72)
    mix_at(c, grand_piano(57, 1.05, 0.65), 0.18, 0.0, 0.74)
    mix_at(c, grand_piano(76, 1.05, 0.68), 0.24, 0.0, 0.76)
    mix_at(c, ethereal_pad(69, 1.05, 0.34), 0.20, 0.0, 0.62)
    c = apply_reverb(c, wet=0.46, decay_sec=0.92, damping_hz=7000.0, seed=913)
    save_wav(c, "genshin_open_chain.wav", 1.55)

    # levelup: 冒険ランクアップ・任務完了の感動的で澄み渡るオープンワールド達成曲！
    c = np.zeros((2, int(SR * 2.55)))
    # 前半：美しく上へ開くピアノ＆ハープの3段モチーフ (D -> E -> F# -> A -> D)
    motif = [(74, 0.00), (76, 0.13), (78, 0.26), (81, 0.40)]
    for i, (n, st) in enumerate(motif):
        pan = -0.25 + i * 0.16
        mix_at(c, grand_piano(n, 0.55, 0.76), st, 0.0, 0.78)
        mix_at(c, concert_harp(n, 0.70, 0.82, seed=960 + i), st, pan, 0.78)
        mix_at(c, crystal_bell(n + 12, 0.42, 0.38), st + 0.01, -pan * 0.5, 0.65)
    # 頂点(0.58s)：深いDメジャー9thの光が草原いっぱいに広がる！
    t_peak = 0.58
    mix_at(c, warm_bass(50, 1.65, 0.80), t_peak, 0.0, 0.80)
    for n in [50, 57, 62, 66, 69, 73, 76]:
        mix_at(c, ethereal_pad(n, 1.70, 0.34), t_peak, 0.0, 0.62)
    for i, n in enumerate([62, 66, 69, 74, 78, 81, 86]):
        mix_at(c, concert_harp(n, 1.25, 0.75, seed=970 + i), t_peak + i * 0.032, -0.4 + i * 0.13, 0.74)
    mix_at(c, grand_piano(86, 1.50, 0.82), t_peak + 0.04, 0.0, 0.84)
    # 星屑の長い余韻
    mix_at(c, star_shimmer([88, 90, 93, 98], 0.0, 0.085, 0.42), t_peak + 0.28, 0.0, 0.82)
    c = apply_reverb(c, wet=0.50, decay_sec=1.20, damping_hz=6800.0, seed=914)
    save_wav(c, "genshin_open_levelup.wav", 2.55)


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    build_ds_exp()
    build_genshin()
    print("Generated ds_exp and genshin_open packs successfully")
