import { useEffect, useMemo, useState } from 'react';
import { CornerDownRight, RotateCcw, Volume2, VolumeX } from 'lucide-react';
import { ActionButton } from './components/ActionButton';
import { ConfigSection } from './components/ConfigSection';
import {
  buildSystemNote,
  computeFrictionIndex,
  computeLevelProgress,
  formatLogTimestamp,
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

export function App() {
  const [data, setData] = useState<AppData>(() => loadAppData());
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [levelUpBanner, setLevelUpBanner] = useState<number | null>(null);
  const [barOverridePercent, setBarOverridePercent] = useState<number | null>(null);
  const [barGoldFlash, setBarGoldFlash] = useState(false);
  const [pointBump, setPointBump] = useState(false);
  const [displayPoints, setDisplayPoints] = useState(0);
  const [showAllLogs, setShowAllLogs] = useState(false);

  useEffect(() => {
    saveAppData(data);
  }, [data]);

  useEffect(() => {
    preloadSoundPack(data.settings.soundProfile, data.settings.customSoundNames);
  }, [data.settings.soundProfile, data.settings.customSoundNames]);

  useEffect(() => {
    const tick = () => setNowMs(Date.now());
    const id = window.setInterval(tick, 30_000);
    const onVis = () => {
      if (document.visibilityState === 'visible') tick();
    };
    document.addEventListener('visibilitychange', onVis);
    return () => {
      window.clearInterval(id);
      document.removeEventListener('visibilitychange', onVis);
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
      // 2段階レベルアップ演出：
      // 1) バーを100%満タンへ駆け上げ
      // 2) 300ms後に満タン閃光＋レベルアップバナー表示
      // 3) 620ms後に余剰ポイントのバー位置へスッと展開
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
  };

  const handleUndoLatest = () => {
    if (data.logs.length === 0) return;
    playUndoSound(data.settings.soundEnabled, data.settings.volume);
    setData((prev) => ({
      ...prev,
      logs: prev.logs.slice(1),
    }));
  };

  const handleUpdateSettings = (patch: Partial<AppSettings>) => {
    setData((prev) => ({
      ...prev,
      settings: { ...prev.settings, ...patch },
    }));
  };

  const handleAddTask = (task: TaskItem) => {
    setData((prev) => ({ ...prev, tasks: [...prev.tasks, task] }));
  };

  const handleUpdateTask = (id: string, patch: Partial<TaskItem>) => {
    setData((prev) => ({
      ...prev,
      tasks: prev.tasks.map((t) => (t.id === id ? { ...t, ...patch } : t)),
    }));
  };

  const handleDeleteTask = (id: string) => {
    setData((prev) => ({
      ...prev,
      tasks: prev.tasks
        .filter((t) => t.id !== id)
        .map((t) => (t.parentId === id ? { ...t, parentId: undefined } : t)),
    }));
  };

  const handleImportData = (next: AppData) => {
    setData(next);
    setNowMs(Date.now());
  };

  const latestLog = data.logs[0];
  const visibleLogs = showAllLogs ? data.logs : data.logs.slice(0, 15);
  const remainingToNext = Math.max(0, progress.nextLevelRequired - progress.currentLevelPoints);

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

        {/* 履歴 */}
        <section className="card log-card">
          <div className="log-card__head">
            <span>履歴</span>
            <span className="num">{data.logs.length}件</span>
          </div>

          {data.logs.length === 0 ? (
            <div className="log-empty">まだ記録はありません</div>
          ) : (
            <>
              <ul className="log-list">
                {visibleLogs.map((entry) => (
                  <li key={entry.id} className="log-row">
                    <span className="log-row__time num">
                      {formatLogTimestamp(entry.timestamp)}
                    </span>
                    <span className="log-row__main">
                      <span className="log-row__name">{entry.taskName}</span>
                      <span className="log-row__note">{entry.systemNote}</span>
                    </span>
                    <span
                      className={`log-row__pt num ${entry.chainBonus > 0 ? 'is-chain' : ''}`}
                    >
                      +{entry.points}
                    </span>
                  </li>
                ))}
              </ul>
              {data.logs.length > 15 && (
                <button
                  type="button"
                  className="log-more-btn"
                  onClick={() => setShowAllLogs((v) => !v)}
                >
                  {showAllLogs ? '直近15件に戻す' : `すべて表示（全${data.logs.length}件）`}
                </button>
              )}
            </>
          )}
        </section>

        {/* 設定・編集・バックアップ */}
        <ConfigSection
          data={data}
          onUpdateSettings={handleUpdateSettings}
          onAddTask={handleAddTask}
          onUpdateTask={handleUpdateTask}
          onDeleteTask={handleDeleteTask}
          onImportData={handleImportData}
        />
      </main>
    </div>
  );
}
