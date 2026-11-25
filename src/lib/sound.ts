import type { SfxSlot, SoundProfile } from '../types';
import { deleteCustomAudio, loadCustomAudio, saveCustomAudio } from './customAudioDb';

export interface SoundProfileInfo {
  value: SoundProfile;
  label: string;
  desc: string;
}

export const SOUND_PROFILES: SoundProfileInfo[] = [
  { value: 'handheld_rpg', label: '携帯機RPG', desc: 'キレ重視・道具ゲット＆LvUP風' },
  { value: 'rpg_poke', label: '王道RPG', desc: '回復・達成風の温かい和音解決' },
  { value: 'dq_fanfare', label: 'オーケストラ改', desc: 'ホルン・弦・ティンパニのファンファーレ' },
];

export const SFX_SLOTS: { key: SfxSlot; label: string }[] = [
  { key: 'light', label: '軽 (+3〜5)' },
  { key: 'heavy', label: '重 (+10〜)' },
  { key: 'chain', label: '連動ボーナス' },
  { key: 'levelup', label: 'レベルアップ' },
];

let sharedCtx: AudioContext | null = null;
const bufferCache = new Map<string, AudioBuffer>();
const customBufferCache = new Map<SfxSlot, AudioBuffer>();
const inflightLoads = new Map<string, Promise<AudioBuffer | null>>();

function getAudioContext(): AudioContext | null {
  if (typeof window === 'undefined') return null;
  const AudioCtx =
    window.AudioContext ||
    (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AudioCtx) return null;
  if (!sharedCtx) {
    sharedCtx = new AudioCtx();
  }
  if (sharedCtx.state === 'suspended') {
    sharedCtx.resume().catch(() => {});
  }
  return sharedCtx;
}

async function loadSfxBuffer(ctx: AudioContext, filename: string): Promise<AudioBuffer | null> {
  const cached = bufferCache.get(filename);
  if (cached) return cached;

  const existing = inflightLoads.get(filename);
  if (existing) return existing;

  const promise = (async () => {
    try {
      const res = await fetch(`./sfx/${filename}`);
      if (!res.ok) return null;
      const arr = await res.arrayBuffer();
      const decoded = await ctx.decodeAudioData(arr);
      bufferCache.set(filename, decoded);
      return decoded;
    } catch {
      return null;
    } finally {
      inflightLoads.delete(filename);
    }
  })();

  inflightLoads.set(filename, promise);
  return promise;
}

async function resolveSlotBuffer(
  ctx: AudioContext,
  profile: SoundProfile,
  slot: SfxSlot,
  hasCustom: boolean
): Promise<AudioBuffer | null> {
  if (hasCustom) {
    const cached = customBufferCache.get(slot);
    if (cached) return cached;
    const raw = await loadCustomAudio(slot);
    if (raw) {
      try {
        const decoded = await ctx.decodeAudioData(raw);
        customBufferCache.set(slot, decoded);
        return decoded;
      } catch {
        // デコード失敗時は標準音にフォールバック
      }
    }
  }
  return loadSfxBuffer(ctx, `${profile}_${slot}.wav`);
}

export async function registerCustomSlotAudio(slot: SfxSlot, file: File): Promise<void> {
  const arr = await file.arrayBuffer();
  await saveCustomAudio(slot, arr);
  const ctx = getAudioContext();
  if (ctx) {
    try {
      const decoded = await ctx.decodeAudioData(arr.slice(0));
      customBufferCache.set(slot, decoded);
    } catch {
      customBufferCache.delete(slot);
    }
  }
}

export async function clearCustomSlotAudio(slot: SfxSlot): Promise<void> {
  await deleteCustomAudio(slot);
  customBufferCache.delete(slot);
}

export function preloadSoundPack(
  profile: SoundProfile,
  customNames?: Partial<Record<SfxSlot, string>>
): void {
  const ctx = getAudioContext();
  if (!ctx) return;
  const slots: SfxSlot[] = ['light', 'heavy', 'chain', 'levelup'];
  for (const slot of slots) {
    void resolveSlotBuffer(ctx, profile, slot, Boolean(customNames?.[slot]));
  }
  void loadSfxBuffer(ctx, 'exp_tick.wav');
  void loadSfxBuffer(ctx, 'undo.ogg');
}

function playBuffer(
  ctx: AudioContext,
  buffer: AudioBuffer,
  volume: number,
  playbackRate = 1.0,
  delaySec = 0
): void {
  const src = ctx.createBufferSource();
  src.buffer = buffer;
  src.playbackRate.value = playbackRate;

  const gain = ctx.createGain();
  gain.gain.value = Math.min(1, Math.max(0, volume));

  src.connect(gain);
  gain.connect(ctx.destination);
  src.start(ctx.currentTime + delaySec);
}

export function playActionSound(params: {
  enabled: boolean;
  volume: number;
  profile: SoundProfile;
  points: number;
  isChain: boolean;
  leveledUp: boolean;
  customNames?: Partial<Record<SfxSlot, string>>;
}): void {
  if (!params.enabled || params.volume <= 0) return;
  const ctx = getAudioContext();
  if (!ctx) return;

  if (params.leveledUp) {
    void loadSfxBuffer(ctx, 'exp_tick.wav').then((buf) => {
      if (buf) playBuffer(ctx, buf, params.volume * 0.72, 1.0, 0);
    });
    void resolveSlotBuffer(
      ctx,
      params.profile,
      'levelup',
      Boolean(params.customNames?.levelup)
    ).then((buf) => {
      if (buf) playBuffer(ctx, buf, Math.min(1, params.volume * 1.05), 1.0, 0.30);
    });
    return;
  }

  const slot: SfxSlot = params.isChain
    ? 'chain'
    : params.points >= 10
      ? 'heavy'
      : 'light';

  void resolveSlotBuffer(ctx, params.profile, slot, Boolean(params.customNames?.[slot])).then(
    (buf) => {
      if (buf) playBuffer(ctx, buf, params.volume, 1.0, 0);
    }
  );
}

export function playSampleSlot(
  profile: SoundProfile,
  slot: SfxSlot,
  volume: number,
  hasCustom = false
): void {
  const ctx = getAudioContext();
  if (!ctx) return;
  if (slot === 'levelup') {
    void loadSfxBuffer(ctx, 'exp_tick.wav').then((buf) => {
      if (buf) playBuffer(ctx, buf, Math.max(0.25, volume * 0.7), 1.0, 0);
    });
    void resolveSlotBuffer(ctx, profile, 'levelup', hasCustom).then((buf) => {
      if (buf) playBuffer(ctx, buf, Math.max(0.3, volume), 1.0, 0.30);
    });
    return;
  }
  void resolveSlotBuffer(ctx, profile, slot, hasCustom).then((buf) => {
    if (buf) playBuffer(ctx, buf, Math.max(0.3, volume), 1.0, 0);
  });
}

export function playUndoSound(enabled: boolean, volume: number): void {
  if (!enabled || volume <= 0) return;
  const ctx = getAudioContext();
  if (!ctx) return;
  void loadSfxBuffer(ctx, 'undo.ogg').then((buf) => {
    if (buf) playBuffer(ctx, buf, volume * 0.7, 1.0, 0);
  });
}

export function triggerHaptics(params: {
  enabled: boolean;
  points: number;
  isChain: boolean;
  leveledUp: boolean;
}): void {
  if (!params.enabled) return;
  if (typeof navigator === 'undefined' || typeof navigator.vibrate !== 'function') return;

  try {
    if (params.leveledUp) {
      navigator.vibrate([16, 40, 16, 40, 22, 60, 45]);
    } else if (params.points >= 10 || params.isChain) {
      navigator.vibrate([16, 28, 20]);
    } else {
      navigator.vibrate(14);
    }
  } catch {
    // 非対応環境では無視
  }
}
