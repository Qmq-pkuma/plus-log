import { useEffect, useMemo, useRef, useState } from 'react';
import { CloudOff, CornerDownRight, RefreshCw, RotateCcw, Volume2, VolumeX } from 'lucide-react';
import { ActionButton } from './components/ActionButton';
import { ConfigSection } from './components/ConfigSection';
import {
  loadSyncConfig,
  saveSyncConfig,
  syncWithGist,
  type GistSyncConfig,
} from './lib/gistSync';
import {
  buildSystemNote,
  computeFrictionIndex,
  computeLevelProgress,
  formatShortTime,
  isTaskChainReady,
} from './lib/progression';
import {
  playActionSound,
  playUndoSound,
  preloadSoundPack,
  triggerHaptics,
} from './lib/sound';
import { loadAppData, saveAppData } from './lib/storage';
import type { AppData, AppSettings, LogEntry, TaskItem } from './types';

function localDateHeading(timestamp: number): string {
  const d = new Date(timestamp);
  const y = d.getFullYear();
  const m = d.getMonth() + 1;
  const day = d.getDate();
  const weekdays = ['日', '月', '火', '水', '木', '金', '土'];
  const wd = weekdays[d.getDay()];
  return `${y}/${String(m).padStart(2, '0')}/${String(day).padStart(2, '0')} (${wd})`;
}

function notifyNativeTaskLogged(taskId: string, timestamp: number): void {
  try {
    (
      window as unknown as {
        PlusLogNative?: { recordTaskLogged?: (id: string, ts: number) => void };
      }
    ).PlusLogNative?.recordTaskLogged?.(taskId, timestamp);
  } catch {
    // Webブラウザ単体などネイティブブリッジ未接続時は何もしない
  }
}

function syncLatestLogsToNative(logs: LogEntry[]): void {
  const latestByTask = new Map<string, number>();
  for (const log of logs) {
    const prev = latestByTask.get(log.taskId);
    if (prev === undefined || log.timestamp > prev) {
      latestByTask.set(log.taskId, log.timestamp);
    }
  }
  for (const [taskId, ts] of latestByTask.entries()) {
    notifyNativeTaskLogged(taskId, ts);
  }
}

export function App() {
  const [data, setData] = useState<AppData>(() => loadAppData());
  const [syncConfig, setSyncConfig] = useState<GistSyncConfig>(() => loadSyncConfig());
  const [syncState, setSyncState] = useState<'idle' | 'syncing' | 'ok' | 'error'>('idle');
  const [syncError, setSyncError] = useState<string | null>(null);
  const [syncBanner, setSyncBanner] = useState<string | null>(null);

  const [nowMs, setNowMs] = useState(() => Date.now());
  const [levelUpBanner, setLevelUpBanner] = useState<number | null>(null);
  const [barOverridePercent, setBarOverridePercent] = useState<number | null>(null);
  const [barGoldFlash, setBarGoldFlash] = useState(false);
  const [pointBump, setPointBump] = useState(false);
  const [displayPoints, setDisplayPoints] = useState(0);
  const [showAllLogs, setShowAllLogs] = useState(false);

  const dataRef = useRef(data);
  const syncConfigRef = useRef(syncConfig);
  const deletedLogIdsRef = useRef<Set<string>>(new Set());
  const deletedTaskIdsRef = useRef<Set<string>>(new Set());
  const syncTimerRef = useRef<number | null>(null);
  const bannerTimerRef = useRef<number | null>(null);

  dataRef.current = data;
  syncConfigRef.current = syncConfig;

  const showSyncBanner = (message: string) => {
    setSyncBanner(message);
    if (bannerTimerRef.current !== null) {
      window.clearTimeout(bannerTimerRef.current);
    }
    bannerTimerRef.current = window.setTimeout(() => {
      bannerTimerRef.current = null;
      setSyncBanner(null);
    }, 3600);
  };

  useEffect(() => {
    saveAppData(data);
  }, [data]);

  useEffect(() => {
    saveSyncConfig(syncConfig);
  }, [syncConfig]);

  useEffect(() => {
    preloadSoundPack(data.settings.soundProfile, data.settings.customSoundNames);
  }, [data.settings.soundProfile, data.settings.customSoundNames]);

  const runSync = async (
    overrideConfig?: GistSyncConfig,
    options?: { preferRemoteTasks?: boolean; showFeedback?: boolean }
  ) => {
    const cfg = overrideConfig ?? syncConfigRef.current;
    if (!cfg.enabled || !cfg.token) {
      if (options?.showFeedback) {
        if (typeof navigator !== 'undefined' && 'serviceWorker' in navigator) {
          void navigator.serviceWorker.getRegistration().then((reg) => reg?.update());
        }
        showSyncBanner('Gist同期が未設定です（下の「設定 → 自動バックアップ・PC同期」から接続できます）');
      }
      return;
    }
    if (typeof navigator !== 'undefined' && navigator.onLine === false) {
      if (options?.showFeedback) {
        showSyncBanner('オフラインのためGistから取得できませんでした');
      }
      return;
    }

    setSyncState('syncing');
    setSyncError(null);
    try {
      const res = await syncWithGist({
        config: cfg,
        localData: dataRef.current,
        deletedLogIds: deletedLogIdsRef.current,
        deletedTaskIds: deletedTaskIdsRef.current,
        preferRemoteTasks: options?.preferRemoteTasks,
      });
      deletedLogIdsRef.current.clear();
      deletedTaskIdsRef.current.clear();
      setData(res.merged);
      syncLatestLogsToNative(res.merged.logs);
      setNowMs(Date.now());
      setSyncConfig((prev) => ({
        ...prev,
        ...cfg,
        gistId: res.gistId,
        lastSyncedAt: res.syncedAt,
      }));
      setSyncState('ok');
      if (options?.showFeedback) {
        if (res.pulledTaskCount > 0 || res.pulledCount > 0) {
          showSyncBanner(
            `Gistから最新を取得しました（項目 +${res.pulledTaskCount}件 / 履歴 +${res.pulledCount}件）`
          );
        } else {
          showSyncBanner(
            `最新データを確認しました（項目 ${res.merged.tasks.length}件 / 履歴 ${res.merged.logs.length}件）`
          );
        }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : '同期に失敗しました';
      setSyncState('error');
      setSyncError(msg);
      if (options?.showFeedback) {
        showSyncBanner(`取得失敗: ${msg}`);
      }
    }
  };

  const scheduleAutoSync = () => {
    const cfg = syncConfigRef.current;
    if (!cfg.enabled || !cfg.token) return;
    if (syncTimerRef.current !== null) {
      window.clearTimeout(syncTimerRef.current);
    }
    syncTimerRef.current = window.setTimeout(() => {
      syncTimerRef.current = null;
      void runSync();
    }, 1500);
  };

  // 初回起動時とアプリ復帰時に自動同期
  useEffect(() => {
    syncLatestLogsToNative(dataRef.current.logs);
    if (syncConfigRef.current.enabled && syncConfigRef.current.token) {
      void runSync();
    }
    const tick = () => setNowMs(Date.now());
    const id = window.setInterval(tick, 30_000);
    const onVis = () => {
      if (document.visibilityState === 'visible') {
        tick();
        if (syncConfigRef.current.enabled && syncConfigRef.current.token) {
          void runSync();
        }
      }
    };
    const onOnline = () => {
      if (syncConfigRef.current.enabled && syncConfigRef.current.token) {
        void runSync();
      }
    };
    document.addEventListener('visibilitychange', onVis);
    window.addEventListener('online', onOnline);
    return () => {
      window.clearInterval(id);
      document.removeEventListener('visibilitychange', onVis);
      window.removeEventListener('online', onOnline);
    };
  }, []);

  const stats = useMemo(() => {
    const countMap = new Map<string, number>();
    const lastTsMap = new Map<string, number>();
    let totalPoints = 0;

    for (const log of data.logs) {
      totalPoints += log.points;
      countMap.set(log.taskId, (countMap.get(log.taskId) ?? 0) + 1);
      const prev = lastTsMap.get(log.taskId);
      if (prev === undefined || log.timestamp > prev) {
        lastTsMap.set(log.taskId, log.timestamp);
      }
    }

    return {
      countMap,
      lastTsMap,
      totalPoints,
      totalActions: data.logs.length,
    };
  }, [data.logs]);

  const progress = useMemo(() => computeLevelProgress(stats.totalPoints), [stats.totalPoints]);
  const frictionIndex = useMemo(
    () => computeFrictionIndex(stats.totalActions),
    [stats.totalActions]
  );

  // 累計ポイントの滑らかなカウントアップ演出
  useEffect(() => {
    const target = stats.totalPoints;
    if (displayPoints === target) return;
    const startVal = displayPoints;
    const diff = target - startVal;
    const duration = Math.min(340, Math.max(140, Math.abs(diff) * 20));
    const t0 = performance.now();
    let raf = 0;

    const step = (now: number) => {
      const p = Math.min(1, (now - t0) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      setDisplayPoints(Math.round(startVal + diff * eased));
      if (p < 1) {
        raf = requestAnimationFrame(step);
      }
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [stats.totalPoints]);

  const boardGroups = useMemo(() => {
    const childrenByParent = new Map<string, TaskItem[]>();
    const taskIdSet = new Set(data.tasks.map((t) => t.id));

    for (const t of data.tasks) {
      if (t.parentId && taskIdSet.has(t.parentId)) {
        const list = childrenByParent.get(t.parentId) ?? [];
        list.push(t);
        childrenByParent.set(t.parentId, list);
      }
    }

    const roots = data.tasks.filter((t) => !t.parentId || !taskIdSet.has(t.parentId));
    return roots.map((root) => ({
      root,
      children: childrenByParent.get(root.id) ?? [],
    }));
  }, [data.tasks]);

  const handleTriggerTask = (task: TaskItem, chainReady: boolean) => {
    const ts = Date.now();
    const chainBonus = chainReady ? (task.chainBonus ?? 0) : 0;
    const earnedPoints = task.points + chainBonus;

    const prevPoints = stats.totalPoints;
    const nextPoints = prevPoints + earnedPoints;
    const prevLevel = computeLevelProgress(prevPoints).level;
    const nextLevel = computeLevelProgress(nextPoints).level;
    const leveledUpTo = nextLevel > prevLevel ? nextLevel : undefined;

    const prevFriction = computeFrictionIndex(stats.totalActions);
    const nextFriction = computeFrictionIndex(stats.totalActions + 1);
    const frictionDelta = Math.max(0.001, prevFriction - nextFriction);
    const nextTaskCount = (stats.countMap.get(task.id) ?? 0) + 1;

    const entry: LogEntry = {
      id: `${ts.toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      taskId: task.id,
      taskName: task.name,
      taskCode: task.code,
      points: earnedPoints,
      basePoints: task.points,
      chainBonus,
      timestamp: ts,
      taskTotalCount: nextTaskCount,
      totalPointsAfter: nextPoints,
      leveledUpTo,
      systemNote: buildSystemNote({
        taskTotalCount: nextTaskCount,
        points: earnedPoints,
        chainBonus,
        leveledUpTo,
        frictionDelta,
      }),
    };

    playActionSound({
      enabled: data.settings.soundEnabled,
      volume: data.settings.volume,
      profile: data.settings.soundProfile,
      points: earnedPoints,
      isChain: chainReady,
      leveledUp: leveledUpTo !== undefined,
      customNames: data.settings.customSoundNames,
    });

    triggerHaptics({
      enabled: data.settings.hapticsEnabled,
      points: earnedPoints,
      isChain: chainReady,
      leveledUp: leveledUpTo !== undefined,
    });

    setPointBump(true);
    window.setTimeout(() => setPointBump(false), 320);

    if (leveledUpTo !== undefined) {
      setBarOverridePercent(100);
      window.setTimeout(() => {
        setBarGoldFlash(true);
        setLevelUpBanner(leveledUpTo);
      }, 300);
      window.setTimeout(() => {
        setBarOverridePercent(0);
        requestAnimationFrame(() => {
          setBarOverridePercent(null);
        });
      }, 620);
      window.setTimeout(() => {
        setBarGoldFlash(false);
      }, 1450);
      window.setTimeout(() => {
        setLevelUpBanner(null);
      }, 2200);
    }

    setNowMs(ts);
    setData((prev) => ({
      ...prev,
      logs: [entry, ...prev.logs],
    }));
    notifyNativeTaskLogged(task.id, ts);
    scheduleAutoSync();
  };

  const handleUndoLatest = () => {
    if (data.logs.length === 0) return;
    const removed = data.logs[0];
    deletedLogIdsRef.current.add(removed.id);
    playUndoSound(data.settings.soundEnabled, data.settings.volume);
    setData((prev) => ({
      ...prev,
      logs: prev.logs.slice(1),
    }));
    scheduleAutoSync();
  };

  const handleUpdateSettings = (patch: Partial<AppSettings>) => {
    setData((prev) => ({
      ...prev,
      settings: { ...prev.settings, ...patch },
    }));
  };

  const handleAddTask = (task: TaskItem) => {
    setData((prev) => ({ ...prev, tasks: [...prev.tasks, task] }));
    scheduleAutoSync();
  };

  const handleUpdateTask = (id: string, patch: Partial<TaskItem>) => {
    setData((prev) => ({
      ...prev,
      tasks: prev.tasks.map((t) => (t.id === id ? { ...t, ...patch } : t)),
    }));
    scheduleAutoSync();
  };

  const handleDeleteTask = (id: string) => {
    deletedTaskIdsRef.current.add(id);
    setData((prev) => ({
      ...prev,
      tasks: prev.tasks
        .filter((t) => t.id !== id)
        .map((t) => (t.parentId === id ? { ...t, parentId: undefined } : t)),
    }));
    scheduleAutoSync();
  };

  const handleImportData = (next: AppData) => {
    setData(next);
    setNowMs(Date.now());
    scheduleAutoSync();
  };

  const handleConnectGist = async (nextConfig: GistSyncConfig) => {
    setSyncConfig(nextConfig);
    if (nextConfig.enabled && nextConfig.token) {
      await runSync(nextConfig);
    }
  };

  const latestLog = data.logs[0];
  const visibleLogs = showAllLogs ? data.logs : data.logs.slice(0, 20);
  const remainingToNext = Math.max(0, progress.nextLevelRequired - progress.currentLevelPoints);

  // BaseFlow風の縦レールタイムライン用に日付ごとへグループ化（記録がある日だけ並ぶ）
  const timelineDays = useMemo(() => {
    const groups: { dayLabel: string; items: LogEntry[] }[] = [];
    for (const entry of visibleLogs) {
      const label = localDateHeading(entry.timestamp);
      const last = groups[groups.length - 1];
      if (!last || last.dayLabel !== label) {
        groups.push({ dayLabel: label, items: [entry] });
      } else {
        last.items.push(entry);
      }
    }
    return groups;
  }, [visibleLogs]);

  return (
    <div className="app-shell">
      <main className="app-main">
        {/* 上部ステータスカード */}
        <section className={`card status-card ${barGoldFlash ? 'is-levelup' : ''}`}>
          {levelUpBanner !== null && (
            <div className="levelup-banner num">
              LEVEL UP — Lv.{levelUpBanner} に到達
            </div>
          )}
          <div className="status-top">
            <div className="status-lv-wrap">
              <span className={`lv-badge num ${barGoldFlash ? 'is-pop' : ''}`}>
                Lv.{progress.level}
              </span>
              <span className={`total-pt num ${pointBump ? 'is-bump' : ''}`}>
                {displayPoints.toLocaleString()}
                <span className="total-pt__unit">pt</span>
              </span>
            </div>

            <div className="status-actions">
              <button
                type="button"
                className={`top-btn sync-indicator ${syncState === 'error' ? 'is-err' : ''}`}
                onClick={() => void runSync(undefined, { preferRemoteTasks: true, showFeedback: true })}
                disabled={syncState === 'syncing'}
                title={
                  syncState === 'error'
                    ? `同期エラー: ${syncError ?? ''}`
                    : syncConfig.enabled && syncConfig.lastSyncedAt
                      ? `最終同期 ${formatShortTime(syncConfig.lastSyncedAt)}（タップでGistから最新を取得）`
                      : 'Gistから最新データを取得'
                }
                aria-label="Gistから最新を取得"
              >
                {syncState === 'error' ? (
                  <CloudOff size={14} />
                ) : (
                  <RefreshCw size={14} className={syncState === 'syncing' ? 'spin' : ''} />
                )}
                <span>更新</span>
              </button>
              <button
                type="button"
                className="top-btn"
                onClick={() => handleUpdateSettings({ soundEnabled: !data.settings.soundEnabled })}
                title={data.settings.soundEnabled ? '消音にする' : '音をオンにする'}
                aria-label="効果音の切り替え"
              >
                {data.settings.soundEnabled ? <Volume2 size={15} /> : <VolumeX size={15} />}
              </button>
              <button
                type="button"
                className="top-btn"
                onClick={handleUndoLatest}
                disabled={data.logs.length === 0}
                title="直前の1件を戻す"
              >
                <RotateCcw size={14} />
                <span>戻す</span>
              </button>
            </div>
          </div>

          {syncBanner && (
            <div className={`sync-banner ${syncState === 'error' ? 'is-err' : ''}`}>
              {syncBanner}
            </div>
          )}

          <div className="progress-area">
            <div className="progress-track">
              <div
                className={`progress-fill ${barGoldFlash ? 'is-gold' : ''}`}
                style={{
                  width: `${
                    barOverridePercent !== null
                      ? barOverridePercent
                      : Math.round(progress.ratio * 100)
                  }%`,
                }}
              />
            </div>
            <div className="progress-meta">
              <span className="num">
                あと {remainingToNext}pt で Lv.{progress.level + 1}
              </span>
              <span className="num">
                計 {stats.totalActions}回 ・ 摩擦係数 {frictionIndex.toFixed(3)}
              </span>
            </div>
          </div>

          <div className="latest-strip">
            {latestLog ? (
              <span className="latest-strip__text">
                <span className="num latest-strip__time">
                  {formatShortTime(latestLog.timestamp)}
                </span>{' '}
                <strong>{latestLog.taskName}</strong>{' '}
                <span className="num latest-strip__pt">+{latestLog.points}pt</span>{' '}
                <span className="latest-strip__note">{latestLog.systemNote}</span>
              </span>
            ) : (
              <span className="latest-strip__idle">
                0点が基準です。ボタンをタップすると記録とポイントが加算されます。
              </span>
            )}
          </div>
        </section>

        {/* 行動ボタンボード */}
        <section className="board-section">
          <div className="section-label">行動を記録</div>
          <div className="task-grid">
            {boardGroups.map(({ root, children }) => {
              if (children.length === 0) {
                return (
                  <ActionButton
                    key={root.id}
                    task={root}
                    count={stats.countMap.get(root.id) ?? 0}
                    lastTimestamp={stats.lastTsMap.get(root.id)}
                    nowMs={nowMs}
                    chainReady={false}
                    onTrigger={handleTriggerTask}
                  />
                );
              }

              const anyChildReady = children.some((child) =>
                isTaskChainReady(child, data.logs, nowMs)
              );

              return (
                <div
                  key={root.id}
                  className={`chain-block ${anyChildReady ? 'is-active' : ''}`}
                >
                  <ActionButton
                    task={{ ...root, span: 'full' }}
                    count={stats.countMap.get(root.id) ?? 0}
                    lastTimestamp={stats.lastTsMap.get(root.id)}
                    nowMs={nowMs}
                    chainReady={false}
                    onTrigger={handleTriggerTask}
                  />
                  <div className="chain-children">
                    <div className="chain-children__label">
                      <CornerDownRight size={14} />
                      <span>
                        {anyChildReady
                          ? `${root.name}のあと（今なら連動ボーナス）`
                          : `${root.name}のあと`}
                      </span>
                    </div>
                    <div className="chain-children__grid">
                      {children.map((child) => (
                        <ActionButton
                          key={child.id}
                          task={child}
                          count={stats.countMap.get(child.id) ?? 0}
                          lastTimestamp={stats.lastTsMap.get(child.id)}
                          nowMs={nowMs}
                          chainReady={isTaskChainReady(child, data.logs, nowMs)}
                          isChild
                          onTrigger={handleTriggerTask}
                        />
                      ))}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        {/* タイムライン（BaseFlow風の縦レール表示・記録のある日だけ並ぶ） */}
        <section className="card log-card">
          <div className="log-card__head">
            <span>タイムライン</span>
            <span className="num">{data.logs.length}件</span>
          </div>

          {data.logs.length === 0 ? (
            <div className="log-empty">まだ記録はありません</div>
          ) : (
            <>
              <div className="tl-root">
                {timelineDays.map((group) => (
                  <div key={group.dayLabel} className="tl-day-group">
                    <div className="tl-day-sep num">{group.dayLabel}</div>
                    {group.items.map((entry) => (
                      <div key={entry.id} className="tl-row">
                        <div className="tl-time num">{formatShortTime(entry.timestamp)}</div>
                        <div className="tl-rail">
                          <span
                            className={`tl-dot ${
                              entry.leveledUpTo
                                ? 'is-lv'
                                : entry.chainBonus > 0
                                  ? 'is-chain'
                                  : ''
                            }`}
                          />
                        </div>
                        <div
                          className={`tl-card ${
                            entry.leveledUpTo
                              ? 'is-lv'
                              : entry.chainBonus > 0
                                ? 'is-chain'
                                : ''
                          }`}
                        >
                          <div className="tl-card__top">
                            <span className="tl-card__name">{entry.taskName}</span>
                            <span
                              className={`tl-card__pt num ${
                                entry.chainBonus > 0 ? 'is-chain' : ''
                              }`}
                            >
                              +{entry.points}pt
                            </span>
                          </div>
                          <div className="tl-card__note">{entry.systemNote}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
              {data.logs.length > 20 && (
                <button
                  type="button"
                  className="log-more-btn"
                  onClick={() => setShowAllLogs((v) => !v)}
                >
                  {showAllLogs ? '直近20件に戻す' : `すべて表示（全${data.logs.length}件）`}
                </button>
              )}
            </>
          )}
        </section>

        {/* 設定・編集・自動同期・バックアップ */}
        <ConfigSection
          data={data}
          syncConfig={syncConfig}
          syncState={syncState}
          syncError={syncError}
          onConnectGist={handleConnectGist}
          onManualSync={() => void runSync(undefined, { preferRemoteTasks: true, showFeedback: true })}
          onUpdateSettings={handleUpdateSettings}
          onAddTask={handleAddTask}
          onUpdateTask={handleUpdateTask}
          onDeleteTask={handleDeleteTask}
          onImportData={handleImportData}
        />

        <footer className="app-version num">加点ログ v0.2.6</footer>
      </main>
    </div>
  );
}
