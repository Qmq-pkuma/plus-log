import type { LevelProgress, LogEntry, TaskItem } from '../types';

/**
 * 1レベル上がるのに必要なポイント（単調増加・序盤はサクサク上がる）
 * Lv1->2: 30, Lv2->3: 45, Lv3->4: 60 ...
 */
export function pointsRequiredForLevel(level: number): number {
  return 30 + (level - 1) * 15;
}

export function computeLevelProgress(totalPoints: number): LevelProgress {
  const safeTotal = Math.max(0, Math.floor(totalPoints));
  let level = 1;
  let remaining = safeTotal;

  while (true) {
    const req = pointsRequiredForLevel(level);
    if (remaining < req) {
      return {
        level,
        totalPoints: safeTotal,
        currentLevelPoints: remaining,
        nextLevelRequired: req,
        ratio: req > 0 ? Math.min(1, remaining / req) : 0,
      };
    }
    remaining -= req;
    level += 1;
  }
}

/**
 * 累計行動数に応じた仮想「摩擦係数」（1.000から行動するたびに減り続ける・増えない）
 */
export function computeFrictionIndex(totalActions: number): number {
  const n = Math.max(0, totalActions);
  return 1 / (1 + n * 0.015);
}

/**
 * ドライな日本語ログ文言を生成
 */
export function buildSystemNote(params: {
  taskTotalCount: number;
  points: number;
  chainBonus: number;
  leveledUpTo?: number;
  frictionDelta: number;
}): string {
  const { taskTotalCount, chainBonus, leveledUpTo, frictionDelta } = params;
  const deltaStr = frictionDelta.toFixed(3);
  if (leveledUpTo !== undefined) {
    return `レベル${leveledUpTo}に到達 / 累計${taskTotalCount}回`;
  }
  if (chainBonus > 0) {
    return `連動 +${chainBonus}pt / 摩擦係数 -${deltaStr} / 累計${taskTotalCount}回`;
  }
  return `摩擦係数 -${deltaStr} / 累計${taskTotalCount}回`;
}

/**
 * 子タスクが現在「連動ハイライト状態」かどうかを判定
 * 条件: 親タスクが直近 chainWindowMinutes 分以内に実行されており、
 *       その親実行以降にこの子タスクがまだ実行されていないこと
 */
export function isTaskChainReady(
  task: TaskItem,
  logs: LogEntry[],
  nowMs: number
): boolean {
  if (!task.parentId) return false;
  const windowMs = (task.chainWindowMinutes ?? 120) * 60 * 1000;

  let latestParentTs = -1;
  let latestSelfTs = -1;

  for (const log of logs) {
    if (latestParentTs < 0 && log.taskId === task.parentId) {
      latestParentTs = log.timestamp;
    }
    if (latestSelfTs < 0 && log.taskId === task.id) {
      latestSelfTs = log.timestamp;
    }
    if (latestParentTs >= 0 && latestSelfTs >= 0) break;
  }

  if (latestParentTs < 0) return false;
  if (nowMs - latestParentTs > windowMs) return false;
  if (latestSelfTs >= latestParentTs) return false;
  return true;
}

/**
 * 直近実行からの経過時間を自然な日本語で表示（未実行なら空文字）
 */
export function formatElapsed(timestamp: number | undefined, nowMs: number): string {
  if (!timestamp) return '';
  const diffSec = Math.max(0, Math.floor((nowMs - timestamp) / 1000));
  if (diffSec < 60) return 'たった今';
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}分前`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 48) return `${diffHour}時間前`;
  const diffDay = Math.floor(diffHour / 24);
  return `${diffDay}日前`;
}

export function formatLogTimestamp(timestamp: number): string {
  const d = new Date(timestamp);
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  const hh = String(d.getHours()).padStart(2, '0');
  const min = String(d.getMinutes()).padStart(2, '0');
  return `${mm}/${dd} ${hh}:${min}`;
}

export function formatShortTime(timestamp: number): string {
  const d = new Date(timestamp);
  const hh = String(d.getHours()).padStart(2, '0');
  const min = String(d.getMinutes()).padStart(2, '0');
  return `${hh}:${min}`;
}
