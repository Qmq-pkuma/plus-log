import type { AppData, LogEntry } from '../types';
import { normalizeAppData } from './storage';

const SYNC_CONFIG_KEY = 'pluslog.gist_sync.v1';
const GIST_FILENAME = 'pluslog-data.json';

export interface GistSyncConfig {
  token: string;
  gistId: string;
  enabled: boolean;
  lastSyncedAt?: number;
}

export interface GistSyncResult {
  merged: AppData;
  gistId: string;
  syncedAt: number;
  pulledCount: number;
}

export function loadSyncConfig(): GistSyncConfig {
  try {
    const raw = localStorage.getItem(SYNC_CONFIG_KEY);
    if (!raw) return { token: '', gistId: '', enabled: false };
    const parsed = JSON.parse(raw) as Partial<GistSyncConfig>;
    return {
      token: typeof parsed.token === 'string' ? parsed.token.trim() : '',
      gistId: typeof parsed.gistId === 'string' ? parsed.gistId.trim() : '',
      enabled: Boolean(parsed.enabled && parsed.token),
      lastSyncedAt: typeof parsed.lastSyncedAt === 'number' ? parsed.lastSyncedAt : undefined,
    };
  } catch {
    return { token: '', gistId: '', enabled: false };
  }
}

export function saveSyncConfig(config: GistSyncConfig): void {
  try {
    localStorage.setItem(SYNC_CONFIG_KEY, JSON.stringify(config));
  } catch {
    // 無視
  }
}

function authHeaders(token: string): Record<string, string> {
  return {
    Authorization: `Bearer ${token}`,
    Accept: 'application/vnd.github+json',
    'Content-Type': 'application/json',
  };
}

/**
 * ローカルとリモートのログをIDベースで和集合マージ（取り消し済みIDは除外）
 * データ消失を防ぎつつ複数端末の記録を統合する
 */
export function mergeAppData(
  local: AppData,
  remote: AppData,
  deletedLogIds: Set<string>
): { merged: AppData; addedFromRemote: number } {
  const byId = new Map<string, LogEntry>();
  for (const log of remote.logs) {
    if (!deletedLogIds.has(log.id)) {
      byId.set(log.id, log);
    }
  }
  let addedFromRemote = 0;
  const localIds = new Set(local.logs.map((l) => l.id));
  for (const id of byId.keys()) {
    if (!localIds.has(id)) addedFromRemote += 1;
  }
  for (const log of local.logs) {
    if (!deletedLogIds.has(log.id)) {
      byId.set(log.id, log);
    }
  }

  const mergedLogs = Array.from(byId.values()).sort((a, b) => b.timestamp - a.timestamp);

  // タスク定義・設定は操作中のローカルを優先（ローカルが初期ログ0件でリモートにタスクがある場合はリモート優先）
  const useRemoteTasks = local.logs.length === 0 && remote.logs.length > 0 && remote.tasks.length > 0;

  return {
    merged: {
      version: 1,
      tasks: useRemoteTasks ? remote.tasks : local.tasks,
      logs: mergedLogs,
      settings: local.settings,
    },
    addedFromRemote,
  };
}

/** Gistから最新データを取得（存在しない場合はnull） */
async function fetchRemoteGist(token: string, gistId: string): Promise<AppData | null> {
  const res = await fetch(`https://api.github.com/gists/${encodeURIComponent(gistId)}`, {
    headers: authHeaders(token),
    cache: 'no-store',
  });
  if (res.status === 404) return null;
  if (!res.ok) {
    throw new Error(`Gist読み込み失敗 (HTTP ${res.status})`);
  }
  const json = (await res.json()) as {
    files?: Record<string, { content?: string }>;
  };
  const file = json.files?.[GIST_FILENAME] ?? Object.values(json.files ?? {})[0];
  if (!file?.content) return null;
  const parsed = JSON.parse(file.content) as Partial<AppData>;
  return normalizeAppData(parsed);
}

/** 新規の非公開(Secret) Gistを作成 */
async function createSecretGist(token: string, data: AppData): Promise<string> {
  const res = await fetch('https://api.github.com/gists', {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify({
      description: 'PLUSLOG 自動バックアップ・同期データ（非公開）',
      public: false,
      files: {
        [GIST_FILENAME]: {
          content: JSON.stringify(data, null, 2),
        },
      },
    }),
  });
  if (!res.ok) {
    throw new Error(`非公開Gistの作成に失敗 (HTTP ${res.status})`);
  }
  const json = (await res.json()) as { id?: string };
  if (!json.id) throw new Error('Gist IDの取得に失敗しました');
  return json.id;
}

/** 既存の非公開Gistを更新 */
async function updateSecretGist(token: string, gistId: string, data: AppData): Promise<void> {
  const res = await fetch(`https://api.github.com/gists/${encodeURIComponent(gistId)}`, {
    method: 'PATCH',
    headers: authHeaders(token),
    body: JSON.stringify({
      files: {
        [GIST_FILENAME]: {
          content: JSON.stringify(data, null, 2),
        },
      },
    }),
  });
  if (!res.ok) {
    throw new Error(`Gist更新に失敗 (HTTP ${res.status})`);
  }
}

/**
 * Pull -> Merge -> Push の安全な双方向同期
 * gistId が未設定なら自動で新規 Secret Gist を作成する
 */
export async function syncWithGist(params: {
  config: GistSyncConfig;
  localData: AppData;
  deletedLogIds?: Set<string>;
}): Promise<GistSyncResult> {
  const token = params.config.token.trim();
  if (!token) throw new Error('GitHubトークンが未設定です');

  // セキュリティ上、Gist本文にはトークンや不要な秘密情報を絶対に含めない
  const cleanLocal: AppData = {
    version: params.localData.version,
    tasks: params.localData.tasks,
    logs: params.localData.logs,
    settings: params.localData.settings,
  };

  const deleted = params.deletedLogIds ?? new Set<string>();
  let gistId = params.config.gistId.trim();

  if (!gistId) {
    gistId = await createSecretGist(token, cleanLocal);
    return {
      merged: cleanLocal,
      gistId,
      syncedAt: Date.now(),
      pulledCount: 0,
    };
  }

  const remote = await fetchRemoteGist(token, gistId);
  if (!remote) {
    await updateSecretGist(token, gistId, cleanLocal);
    return {
      merged: cleanLocal,
      gistId,
      syncedAt: Date.now(),
      pulledCount: 0,
    };
  }

  const { merged, addedFromRemote } = mergeAppData(cleanLocal, remote, deleted);
  await updateSecretGist(token, gistId, merged);

  return {
    merged,
    gistId,
    syncedAt: Date.now(),
    pulledCount: addedFromRemote,
  };
}
