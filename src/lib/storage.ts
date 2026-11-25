import { DEFAULT_SETTINGS, DEFAULT_TASKS, INITIAL_APP_DATA } from '../data/presets';
import { SOUND_PROFILES } from './sound';
import type { AppData, LogEntry, SoundProfile, TaskItem } from '../types';

const STORAGE_KEY = 'pluslog.data.v1';
const VALID_PROFILES = new Set<string>(SOUND_PROFILES.map((p) => p.value));

export function loadAppData(): AppData {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return structuredClone(INITIAL_APP_DATA);
    const parsed = JSON.parse(raw) as Partial<AppData>;
    return normalizeAppData(parsed);
  } catch {
    return structuredClone(INITIAL_APP_DATA);
  }
}

export function saveAppData(data: AppData): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  } catch {
    // ストレージ容量超過などの例外は握りつぶす
  }
}

export function normalizeAppData(raw: Partial<AppData>): AppData {
  const tasks: TaskItem[] =
    Array.isArray(raw.tasks) && raw.tasks.length > 0
      ? raw.tasks.filter((t): t is TaskItem => Boolean(t && typeof t.id === 'string' && typeof t.name === 'string'))
      : structuredClone(DEFAULT_TASKS);

  const logs: LogEntry[] = Array.isArray(raw.logs)
    ? raw.logs
        .filter((l): l is LogEntry => Boolean(l && typeof l.id === 'string' && typeof l.timestamp === 'number'))
        .sort((a, b) => b.timestamp - a.timestamp)
    : [];

  const rawProfile = raw.settings?.soundProfile;
  const soundProfile: SoundProfile =
    typeof rawProfile === 'string' && VALID_PROFILES.has(rawProfile)
      ? (rawProfile as SoundProfile)
      : DEFAULT_SETTINGS.soundProfile;

  const settings = {
    ...DEFAULT_SETTINGS,
    ...(raw.settings ?? {}),
    soundProfile,
  };

  return {
    version: 1,
    tasks,
    logs,
    settings,
  };
}

export function exportAppDataJson(data: AppData): void {
  const payload = JSON.stringify(data, null, 2);
  const blob = new Blob([payload], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const stamp = new Date().toISOString().slice(0, 10);
  const a = document.createElement('a');
  a.href = url;
  a.download = `pluslog-backup-${stamp}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

export function parseImportedJson(text: string): AppData {
  const parsed = JSON.parse(text) as Partial<AppData>;
  if (!parsed || typeof parsed !== 'object' || !Array.isArray(parsed.tasks)) {
    throw new Error('有効なバックアップJSONではありません');
  }
  return normalizeAppData(parsed);
}
