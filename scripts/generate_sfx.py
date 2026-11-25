"""
オリジナル高品質効果音WAV生成スクリプト (44.1kHz / 16bit / Stereo)
多層レイヤー（サブパンチ・トランジェント・FM/物理倍音・ステレオ空間リバーブ・ソフトリミッター）で
ブラウザの簡易シンセでは出せないゲームUI・高級ガジェット級の質感を作成する。
"""

import os
import wave
import numpy as np
from scipy.signal import butter, sosfilt, fftconvolve

SR = 44100
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "public", "sfx")


def bandpass(x: np.ndarray, low: float, high: float, order: int = 3) -> np.ndarray:
    nyq = SR * 0.5
    sos = butter(order, [max(20.0, low) / nyq, min(nyq * 0.96, high) / nyq], btype="band", output="sos")
    return sosfilt(sos, x)


def lowpass(x: np.ndarray, cutoff: float, order: int = 3) -> np.ndarray:
    nyq = SR * 0.5
    sos = butter(order, min(nyq * 0.96, cutoff) / nyq, btype="low", output="sos")
    return sosfilt(sos, x)


def highpass(x: np.ndarray, cutoff: float, order: int = 2) -> np.ndarray:
    nyq = SR * 0.5
    sos = butter(order, max(20.0, cutoff) / nyq, btype="high", output="sos")
    return sosfilt(sos, x)


def make_stereo_reverb_ir(decay_sec: float, damping_hz: float = 4800.0, seed: int = 42) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    n = int(SR * decay_sec)
    t = np.arange(n) / SR
    env = np.exp(-t * (6.2 / max(0.08, decay_sec)))
    # 初期反射をわずかにずらして自然な空間感を作る
    ir_l = rng.standard_normal(n) * env
    ir_r = rng.standard_normal(n) * env
    # 初期反射スパイク
    for ms, amp_l, amp_r in [(7, 0.55, 0.25), (13, 0.22, 0.52), (21, 0.38, 0.31), (31, 0.24, 0.36)]:
        idx = int(SR * ms / 1000)
        if idx < n:
            ir_l[idx] += amp_l
            ir_r[idx] += amp_r
    ir_l = lowpass(ir_l, damping_hz, order=2)
    ir_r = lowpass(ir_r, damping_hz, order=2)
    # 先頭を滑らかに
    fade = min(int(SR * 0.004), n)
    ir_l[:fade] *= np.linspace(0, 1, fade)
    ir_r[:fade] *= np.linspace(0, 1, fade)
    norm = max(np.sqrt(np.sum(ir_l**2)), np.sqrt(np.sum(ir_r**2)), 1e-6)
    return ir_l / norm, ir_r / norm


def apply_reverb(stereo: np.ndarray, wet: float, decay_sec: float, damping_hz: float = 5200.0, seed: int = 42) -> np.ndarray:
    ir_l, ir_r = make_stereo_reverb_ir(decay_sec, damping_hz, seed)
    wet_l = fftconvolve(stereo[0], ir_l, mode="full")
    wet_r = fftconvolve(stereo[1], ir_r, mode="full")
    out_len = max(stereo.shape[1], len(wet_l))
    out = np.zeros((2, out_len), dtype=np.float64)
    out[:, : stereo.shape[1]] += stereo
    out[0, : len(wet_l)] += wet_l * wet
    out[1, : len(wet_r)] += wet_r * wet
    return out


def mix_at(canvas: np.ndarray, sig: np.ndarray, start_sec: float, pan: float = 0.0, gain: float = 1.0) -> None:
    """モノラルまたはステレオ信号を canvas (2, N) の start_sec 位置に加算"""
    idx = int(start_sec * SR)
    if idx < 0 or idx >= canvas.shape[1]:
        return
    if sig.ndim == 1:
        n = min(len(sig), canvas.shape[1] - idx)
        # 等パワーパン (-1=L, +1=R)
        angle = (pan + 1.0) * 0.25 * np.pi
        canvas[0, idx : idx + n] += sig[:n] * (np.cos(angle) * gain)
        canvas[1, idx : idx + n] += sig[:n] * (np.sin(angle) * gain)
    else:
        n = min(sig.shape[1], canvas.shape[1] - idx)
        canvas[0, idx : idx + n] += sig[0, :n] * gain
        canvas[1, idx : idx + n] += sig[1, :n] * gain


def sub_punch(f_start: float, f_end: float, dur: float, drive: float = 1.6) -> np.ndarray:
    n = int(SR * dur)
    t = np.arange(n) / SR
    # 指数ピッチドロップ
    freqs = f_end + (f_start - f_end) * np.exp(-t * 42.0)
    phase = 2.0 * np.pi * np.cumsum(freqs) / SR
    env = np.exp(-t * (5.5 / dur)) * np.minimum(1.0, t / 0.002)
    sig = np.sin(phase) * env
    # スマホスピーカーでも重みが出るようソフトサチュレーションで倍音付与
    return np.tanh(sig * drive) / np.tanh(drive)


def fm_bell(
    freq: float,
    dur: float,
    mod_ratio: float = 2.0,
    mod_index: float = 2.2,
    mod_decay: float = 14.0,
    amp_decay: float = 5.5,
    attack: float = 0.002,
    detune_cents: float = 0.0,
) -> np.ndarray:
    n = int(SR * dur)
    t = np.arange(n) / SR
    f = freq * (2.0 ** (detune_cents / 1200.0))
    mod_env = mod_index * np.exp(-t * mod_decay)
    carrier_phase = 2.0 * np.pi * f * t + mod_env * np.sin(2.0 * np.pi * f * mod_ratio * t)
    amp_env = np.exp(-t * (amp_decay / dur)) * np.minimum(1.0, t / max(0.0005, attack))
    return np.sin(carrier_phase) * amp_env


def stereo_fm_note(freq: float, dur: float, mod_ratio: float = 2.0, mod_index: float = 2.0, width_cents: float = 5.0, **kwargs) -> np.ndarray:
    l = fm_bell(freq, dur, mod_ratio=mod_ratio, mod_index=mod_index, detune_cents=-width_cents, **kwargs)
    r = fm_bell(freq, dur, mod_ratio=mod_ratio, mod_index=mod_index, detune_cents=+width_cents, **kwargs)
    return np.vstack([l, r])


def modal_glass(freq: float, dur: float, brightness: float = 1.0) -> np.ndarray:
    """ガラス・クリスタル・金属共鳴の非整数倍音モデル"""
    n = int(SR * dur)
    t = np.arange(n) / SR
    modes = [
        (1.000, 1.00, 4.2),
        (2.002, 0.38 * brightness, 7.5),
        (2.756, 0.24 * brightness, 11.0),
        (4.070, 0.14 * brightness, 16.0),
        (5.404, 0.08 * brightness, 22.0),
    ]
    out_l = np.zeros(n)
    out_r = np.zeros(n)
    atk = np.minimum(1.0, t / 0.0018)
    for idx, (ratio, amp, dec) in enumerate(modes):
        f = freq * ratio
        if f >= SR * 0.45:
            continue
        env = np.exp(-t * (dec / dur)) * atk
        det = (1.0 if idx % 2 == 0 else -1.0) * 0.0022
        out_l += np.sin(2.0 * np.pi * f * (1.0 - det) * t) * amp * env
        out_r += np.sin(2.0 * np.pi * f * (1.0 + det) * t) * amp * env
    return np.vstack([out_l, out_r])


def plucked_harp(freq: float, dur: float, seed: int = 1) -> np.ndarray:
    """Karplus-Strong風の澄んだ撥弦音"""
    rng = np.random.default_rng(seed)
    n = int(SR * dur)
    delay = max(2, int(round(SR / freq)))
    buf = lowpass(rng.standard_normal(delay), min(9000.0, freq * 8.0), order=2)
    out = np.zeros(n)
    decay = 0.9965 if freq < 600 else 0.9945
    for i in range(n):
        val = buf[i % delay]
        out[i] = val
        nxt = buf[(i + 1) % delay]
        buf[i % delay] = 0.5 * (val + nxt) * decay
    t = np.arange(n) / SR
    out *= np.exp(-t * (3.5 / dur))
    return highpass(out, 120.0)


def crisp_transient(dur: float, low_hz: float, high_hz: float, decay: float = 95.0, seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(SR * dur)
    t = np.arange(n) / SR
    noise = rng.standard_normal(n) * np.exp(-t * decay)
    return bandpass(noise, low_hz, high_hz, order=3)


def master_and_save(stereo: np.ndarray, filename: str, max_dur_sec: float | None = None) -> None:
    if max_dur_sec is not None:
        max_n = int(SR * max_dur_sec)
        if stereo.shape[1] > max_n:
            stereo = stereo[:, :max_n].copy()
            fade = int(SR * 0.04)
            stereo[:, -fade:] *= np.linspace(1.0, 0.0, fade)

    # DCカット
    stereo = np.vstack([highpass(stereo[0], 35.0, 2), highpass(stereo[1], 35.0, 2)])
    # 軽いマスタリングサチュレーション + -1.2dBノーマライズ
    peak = np.max(np.abs(stereo))
    if peak > 1e-6:
        stereo = stereo / peak
    stereo = np.tanh(stereo * 1.18) / np.tanh(1.18)
    stereo *= 0.88

    # 無音トリム（末尾）
    mag = np.max(np.abs(stereo), axis=0)
    nz = np.where(mag > 0.0015)[0]
    if len(nz) > 0:
        end = min(stereo.shape[1], int(nz[-1]) + int(SR * 0.02))
        stereo = stereo[:, :end]

    # 16bit PCM 書き出し
    pcm = np.clip(stereo.T * 32767.0, -32768, 32767).astype(np.int16)
    path = os.path.join(OUT_DIR, filename)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())


# ============================================================
# 1. FPS / 競技ゲーム達成音系 (鋭いキレ + 重厚サブ + 澄んだ確定音)
# ============================================================
def build_fps():
    # light: ヒット確認 + シャープな確定音
    c = np.zeros((2, int(SR * 0.45)))
    mix_at(c, crisp_transient(0.035, 3200, 9500, 140, seed=11), 0.0, 0.0, 0.95)
    mix_at(c, sub_punch(170, 62, 0.075, drive=1.9), 0.0, 0.0, 0.72)
    mix_at(c, stereo_fm_note(659.25, 0.22, mod_ratio=2.0, mod_index=2.8, width_cents=6, amp_decay=6.5), 0.008, 0.0, 0.55)
    mix_at(c, stereo_fm_note(987.77, 0.24, mod_ratio=3.0, mod_index=1.8, width_cents=8, amp_decay=6.0), 0.032, 0.0, 0.42)
    c = apply_reverb(c, wet=0.26, decay_sec=0.28, damping_hz=6800, seed=101)
    master_and_save(c, "fps_light.wav", 0.52)

    # heavy: シールド完了・大目標達成のズシッ＋シャキーン
    c = np.zeros((2, int(SR * 0.72)))
    mix_at(c, crisp_transient(0.045, 2800, 11000, 110, seed=12), 0.0, 0.0, 1.0)
    mix_at(c, sub_punch(185, 52, 0.13, drive=2.2), 0.0, 0.0, 0.9)
    mix_at(c, stereo_fm_note(554.37, 0.34, mod_ratio=2.0, mod_index=3.1, width_cents=7, amp_decay=5.2), 0.01, 0.0, 0.58)
    mix_at(c, stereo_fm_note(830.61, 0.38, mod_ratio=2.0, mod_index=2.4, width_cents=9, amp_decay=4.8), 0.058, 0.0, 0.55)
    mix_at(c, modal_glass(1108.73, 0.46, brightness=1.1), 0.068, 0.0, 0.38)
    c = apply_reverb(c, wet=0.38, decay_sec=0.45, damping_hz=7200, seed=102)
    master_and_save(c, "fps_heavy.wav", 0.85)

    # chain: 連動ロックオンの鋭い上昇コンボ音
    c = np.zeros((2, int(SR * 0.65)))
    mix_at(c, crisp_transient(0.03, 4000, 12000, 150, seed=13), 0.0, -0.2, 0.85)
    mix_at(c, sub_punch(190, 70, 0.09, drive=1.9), 0.0, 0.0, 0.65)
    for i, freq in enumerate([739.99, 1108.73, 1479.98]):
        mix_at(c, stereo_fm_note(freq, 0.32, mod_ratio=2.5, mod_index=2.2, width_cents=8, amp_decay=5.4), 0.008 + i * 0.042, 0.0, 0.48)
    c = apply_reverb(c, wet=0.36, decay_sec=0.42, damping_hz=7600, seed=103)
    master_and_save(c, "fps_chain.wav", 0.78)

    # levelup: ランクアップ的な重厚インパクト＋輝く展開
    c = np.zeros((2, int(SR * 1.15)))
    mix_at(c, sub_punch(160, 46, 0.22, drive=2.4), 0.0, 0.0, 0.95)
    mix_at(c, crisp_transient(0.06, 2500, 12000, 85, seed=14), 0.0, 0.0, 0.9)
    notes = [(554.37, 0.0), (659.25, 0.065), (830.61, 0.13), (1108.73, 0.205)]
    for freq, off in notes:
        mix_at(c, stereo_fm_note(freq, 0.58, mod_ratio=2.0, mod_index=2.6, width_cents=9, amp_decay=4.2), off, 0.0, 0.48)
        mix_at(c, modal_glass(freq * 2.0, 0.55, brightness=0.9), off + 0.01, 0.0, 0.22)
    c = apply_reverb(c, wet=0.46, decay_sec=0.68, damping_hz=7400, seed=104)
    master_and_save(c, "fps_levelup.wav", 1.35)


# ============================================================
# 2. 次世代機・高級ガジェット系 (PS5/Switch風の洗練ガラス＆空間)
# ============================================================
def build_console():
    # light: 精密アルミ＋クリスタルの一打
    c = np.zeros((2, int(SR * 0.48)))
    mix_at(c, sub_punch(240, 95, 0.055, drive=1.3), 0.0, 0.0, 0.58)
    mix_at(c, crisp_transient(0.02, 1800, 5200, 180, seed=21), 0.0, 0.0, 0.45)
    mix_at(c, modal_glass(587.33, 0.32, brightness=0.85), 0.005, 0.0, 0.65)
    c = apply_reverb(c, wet=0.35, decay_sec=0.36, damping_hz=5400, seed=201)
    master_and_save(c, "console_light.wav", 0.58)

    # heavy: 深みのある2重クリスタル確定音
    c = np.zeros((2, int(SR * 0.72)))
    mix_at(c, sub_punch(210, 75, 0.09, drive=1.45), 0.0, 0.0, 0.68)
    mix_at(c, modal_glass(440.0, 0.45, brightness=0.9), 0.005, 0.0, 0.6)
    mix_at(c, modal_glass(659.25, 0.5, brightness=1.0), 0.06, 0.0, 0.58)
    mix_at(c, stereo_fm_note(880.0, 0.42, mod_ratio=1.5, mod_index=1.1, width_cents=7, amp_decay=4.5), 0.075, 0.0, 0.3)
    c = apply_reverb(c, wet=0.45, decay_sec=0.52, damping_hz=5800, seed=202)
    master_and_save(c, "console_heavy.wav", 0.9)

    # chain: 澄み渡る透明なスライド和音
    c = np.zeros((2, int(SR * 0.65)))
    mix_at(c, sub_punch(250, 110, 0.06, drive=1.3), 0.0, 0.0, 0.45)
    for i, freq in enumerate([587.33, 880.0, 1174.66]):
        mix_at(c, modal_glass(freq, 0.42, brightness=0.95), i * 0.048, 0.0, 0.48)
    c = apply_reverb(c, wet=0.44, decay_sec=0.48, damping_hz=6200, seed=203)
    master_and_save(c, "console_chain.wav", 0.85)

    # levelup: 澄んだオーロラ風のコード展開
    c = np.zeros((2, int(SR * 1.15)))
    mix_at(c, sub_punch(180, 65, 0.14, drive=1.4), 0.0, 0.0, 0.65)
    for i, freq in enumerate([440.0, 554.37, 659.25, 880.0, 1108.73]):
        mix_at(c, modal_glass(freq, 0.62, brightness=0.9), i * 0.055, 0.0, 0.42)
    c = apply_reverb(c, wet=0.52, decay_sec=0.72, damping_hz=6000, seed=204)
    master_and_save(c, "console_levelup.wav", 1.38)


# ============================================================
# 3. RPG・報酬アンロック系 (撥弦ハープ + 輝くメジャー9th + シマー)
# ============================================================
def build_rpg():
    # light: 軽快なハープ＆スパークル
    c = np.zeros((2, int(SR * 0.52)))
    mix_at(c, plucked_harp(587.33, 0.36, seed=31), 0.0, -0.22, 0.72)
    mix_at(c, plucked_harp(880.0, 0.40, seed=32), 0.042, +0.22, 0.68)
    mix_at(c, modal_glass(1760.0, 0.28, brightness=0.8), 0.05, 0.0, 0.22)
    c = apply_reverb(c, wet=0.38, decay_sec=0.42, damping_hz=6600, seed=301)
    master_and_save(c, "rpg_light.wav", 0.62)

    # heavy: クエスト完了風の華やかなアルペジオ
    c = np.zeros((2, int(SR * 0.85)))
    mix_at(c, sub_punch(165, 73, 0.11, drive=1.5), 0.0, 0.0, 0.55)
    harp_notes = [(587.33, -0.35, 0.0), (739.99, -0.12, 0.045), (880.0, 0.12, 0.09), (1174.66, 0.35, 0.135)]
    for idx, (freq, pan, off) in enumerate(harp_notes):
        mix_at(c, plucked_harp(freq, 0.52, seed=40 + idx), off, pan, 0.65)
        mix_at(c, stereo_fm_note(freq * 2.0, 0.35, mod_ratio=2.0, mod_index=1.2, width_cents=8, amp_decay=5.0), off + 0.01, 0.0, 0.18)
    c = apply_reverb(c, wet=0.46, decay_sec=0.58, damping_hz=7200, seed=302)
    master_and_save(c, "rpg_heavy.wav", 1.05)

    # chain: キラッと跳ねる連動ボーナス音
    c = np.zeros((2, int(SR * 0.72)))
    for idx, (freq, pan, off) in enumerate([(739.99, -0.25, 0.0), (987.77, 0.0, 0.04), (1318.51, 0.25, 0.08)]):
        mix_at(c, plucked_harp(freq, 0.42, seed=50 + idx), off, pan, 0.62)
        mix_at(c, modal_glass(freq * 1.5, 0.36, brightness=1.0), off + 0.01, 0.0, 0.25)
    c = apply_reverb(c, wet=0.42, decay_sec=0.5, damping_hz=7400, seed=303)
    master_and_save(c, "rpg_chain.wav", 0.9)

    # levelup: 報酬アンロック・ファンファーレ
    c = np.zeros((2, int(SR * 1.25)))
    mix_at(c, sub_punch(146.83, 73.42, 0.18, drive=1.6), 0.0, 0.0, 0.65)
    seq = [587.33, 739.99, 880.0, 1174.66, 1318.51]
    for idx, freq in enumerate(seq):
        off = idx * 0.055
        mix_at(c, plucked_harp(freq, 0.65, seed=60 + idx), off, (idx - 2) * 0.22, 0.62)
        mix_at(c, stereo_fm_note(freq, 0.62, mod_ratio=2.0, mod_index=1.8, width_cents=9, amp_decay=3.8), off, 0.0, 0.28)
    c = apply_reverb(c, wet=0.52, decay_sec=0.78, damping_hz=7600, seed=304)
    master_and_save(c, "rpg_levelup.wav", 1.45)


# ============================================================
# 4. 極上メカニカル＆音叉系 (高級キーボードThock + 真鍮音叉)
# ============================================================
def build_tactile():
    def thock_switch(seed: int) -> np.ndarray:
        n = int(SR * 0.09)
        s = np.zeros((2, n))
        # 底打ちボディ（温かく太いコトッ）
        mix_at(s, sub_punch(195, 82, 0.055, drive=1.7), 0.0, 0.0, 0.85)
        # スイッチステムの硬質クリック
        mix_at(s, crisp_transient(0.022, 1600, 4800, 160, seed=seed), 0.0, -0.08, 0.8)
        # トップアウトの微小な返り音
        mix_at(s, crisp_transient(0.018, 2400, 6200, 190, seed=seed + 1), 0.026, +0.08, 0.38)
        return s

    # light: Thocky打鍵 + 控えめな真鍮チャイム
    c = np.zeros((2, int(SR * 0.42)))
    mix_at(c, thock_switch(71), 0.0, 0.0, 1.0)
    mix_at(c, stereo_fm_note(659.25, 0.28, mod_ratio=1.0, mod_index=0.5, width_cents=4, amp_decay=4.8), 0.016, 0.0, 0.45)
    c = apply_reverb(c, wet=0.2, decay_sec=0.24, damping_hz=4400, seed=401)
    master_and_save(c, "tactile_light.wav", 0.48)

    # heavy: 重厚な打鍵 + 澄んだ2音音叉和音
    c = np.zeros((2, int(SR * 0.65)))
    mix_at(c, thock_switch(73), 0.0, 0.0, 1.05)
    mix_at(c, stereo_fm_note(523.25, 0.48, mod_ratio=1.0, mod_index=0.6, width_cents=5, amp_decay=3.8), 0.015, 0.0, 0.52)
    mix_at(c, stereo_fm_note(783.99, 0.52, mod_ratio=2.0, mod_index=0.5, width_cents=6, amp_decay=3.8), 0.055, 0.0, 0.46)
    c = apply_reverb(c, wet=0.28, decay_sec=0.38, damping_hz=4800, seed=402)
    master_and_save(c, "tactile_heavy.wav", 0.78)

    # chain: カチッと噛み合う2段スイッチ + 抜けの良い和音
    c = np.zeros((2, int(SR * 0.58)))
    mix_at(c, thock_switch(75), 0.0, -0.1, 0.9)
    mix_at(c, thock_switch(77), 0.048, +0.1, 0.85)
    mix_at(c, stereo_fm_note(783.99, 0.42, mod_ratio=1.0, mod_index=0.6, width_cents=5, amp_decay=4.2), 0.052, 0.0, 0.5)
    mix_at(c, stereo_fm_note(1046.5, 0.44, mod_ratio=2.0, mod_index=0.4, width_cents=6, amp_decay=4.2), 0.088, 0.0, 0.42)
    c = apply_reverb(c, wet=0.28, decay_sec=0.35, damping_hz=5200, seed=403)
    master_and_save(c, "tactile_chain.wav", 0.72)

    # levelup: 心地よい真鍮チャイム和音
    c = np.zeros((2, int(SR * 1.05)))
    mix_at(c, thock_switch(79), 0.0, 0.0, 0.95)
    for i, freq in enumerate([523.25, 659.25, 783.99, 1046.5]):
        mix_at(c, stereo_fm_note(freq, 0.65, mod_ratio=1.0, mod_index=0.55, width_cents=6, amp_decay=3.5), 0.02 + i * 0.06, 0.0, 0.45)
    c = apply_reverb(c, wet=0.35, decay_sec=0.55, damping_hz=5200, seed=404)
    master_and_save(c, "tactile_levelup.wav", 1.25)


def build_undo():
    c = np.zeros((2, int(SR * 0.25)))
    mix_at(c, sub_punch(320, 180, 0.09, drive=1.2), 0.0, 0.0, 0.5)
    mix_at(c, crisp_transient(0.015, 1200, 3200, 180, seed=91), 0.0, 0.0, 0.35)
    c = apply_reverb(c, wet=0.15, decay_sec=0.16, damping_hz=3000, seed=901)
    master_and_save(c, "undo.wav", 0.26)


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    build_fps()
    build_console()
    build_rpg()
    build_tactile()
    build_undo()
    files = sorted(os.listdir(OUT_DIR))
    total_kb = sum(os.path.getsize(os.path.join(OUT_DIR, f)) for f in files) / 1024.0
    print(f"Generated {len(files)} WAV files ({total_kb:.1f} KiB) in {OUT_DIR}")
