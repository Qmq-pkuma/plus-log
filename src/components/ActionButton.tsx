import { useState, type MouseEvent } from 'react';
import { Check } from 'lucide-react';
import { formatElapsed } from '../lib/progression';
import type { TaskItem } from '../types';
import { IconGlyph } from './IconGlyph';

interface PopBadge {
  id: number;
  x: number;
  y: number;
  label: string;
  isChain: boolean;
}

interface ActionButtonProps {
  task: TaskItem;
  count: number;
  lastTimestamp?: number;
  nowMs: number;
  chainReady: boolean;
  isChild?: boolean;
  onTrigger: (task: TaskItem, chainReady: boolean) => void;
}

let popSeq = 0;

export function ActionButton({
  task,
  count,
  lastTimestamp,
  nowMs,
  chainReady,
  isChild = false,
  onTrigger,
}: ActionButtonProps) {
  const [pops, setPops] = useState<PopBadge[]>([]);
  const [justPressed, setJustPressed] = useState(false);

  const elapsed = formatElapsed(lastTimestamp, nowMs);
  const bonus = chainReady ? (task.chainBonus ?? 0) : 0;
  const displayPoints = task.points + bonus;

  const handleClick = (e: MouseEvent<HTMLButtonElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const hasCoords = e.clientX !== 0 || e.clientY !== 0;
    const x = hasCoords ? e.clientX - rect.left : rect.width / 2;
    const y = hasCoords ? e.clientY - rect.top : rect.height / 2;

    const id = ++popSeq;
    const label = bonus > 0 ? `+${task.points} (+${bonus})` : `+${task.points} pt`;
    setPops((prev) => [...prev.slice(-3), { id, x, y, label, isChain: chainReady }]);
    setJustPressed(true);

    window.setTimeout(() => setJustPressed(false), 480);
    window.setTimeout(() => {
      setPops((prev) => prev.filter((p) => p.id !== id));
    }, 760);

    onTrigger(task, chainReady);
  };

  const classes = [
    'task-btn',
    task.span === 'full' && !isChild ? 'is-full' : '',
    isChild ? 'is-child' : '',
    chainReady ? 'is-chain-ready' : '',
    justPressed ? 'is-pressed-ok' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <button type="button" className={classes} onClick={handleClick}>
      <div className="task-btn__top">
        <span className={`task-btn__icon ${justPressed ? 'is-ok' : ''}`}>
          {justPressed ? (
            <Check size={20} strokeWidth={2.6} />
          ) : (
            <IconGlyph icon={task.icon} size={isChild ? 18 : 20} />
          )}
        </span>
        <span className={`task-btn__pt num ${chainReady ? 'is-chain' : ''}`}>
          +{displayPoints}
          <span className="task-btn__pt-unit">pt</span>
        </span>
      </div>

      <div className="task-btn__name">
        {task.name}
        {chainReady && <span className="task-btn__chain-pill">連動 +{bonus}</span>}
      </div>

      <div className="task-btn__meta">
        <span className="num">累計 {count}回</span>
        {elapsed && <span className="task-btn__elapsed">{elapsed}</span>}
      </div>

      <div className="task-btn__fx" aria-hidden="true">
        {pops.map((pop) => (
          <div
            key={pop.id}
            className={`pop-origin ${pop.isChain ? 'is-chain' : ''}`}
            style={{ left: `${pop.x}px`, top: `${pop.y}px` }}
          >
            <span className="pop-ring" />
            <span className="pop-badge num">{pop.label}</span>
          </div>
        ))}
      </div>
    </button>
  );
}
