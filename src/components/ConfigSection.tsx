import { useRef, useState, type ChangeEvent, type FormEvent } from 'react';
import {
  ChevronDown,
  ChevronRight,
  Download,
  Music,
  Play,
  Plus,
  Settings,
  Trash2,
  Upload,
  Vibrate,
  Volume2,
  X,
} from 'lucide-react';
import {
  clearCustomSlotAudio,
  playSampleSlot,
  preloadSoundPack,
  registerCustomSlotAudio,
  SFX_SLOTS,
  SOUND_PROFILES,
} from '../lib/sound';
import { exportAppDataJson, parseImportedJson } from '../lib/storage';
import type { AppData, AppSettings, IconKey, SfxSlot, SoundProfile, TaskItem } from '../types';
import { ICON_OPTIONS, IconGlyph } from './IconGlyph';

interface ConfigSectionProps {
  data: AppData;
  onUpdateSettings: (patch: Partial<AppSettings>) => void;
  onAddTask: (task: TaskItem) => void;
  onUpdateTask: (id: string, patch: Partial<TaskItem>) => void;
  onDeleteTask: (id: string) => void;
  onImportData: (next: AppData) => void;
}

export function ConfigSection({
  data,
  onUpdateSettings,
  onAddTask,
  onUpdateTask,
  onDeleteTask,
  onImportData,
}: ConfigSectionProps) {
  const [open, setOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [newPoints, setNewPoints] = useState(5);
  const [newIcon, setNewIcon] = useState<IconKey>('check');
  const [newSpan, setNewSpan] = useState<'half' | 'full'>('half');
  const [newParentId, setNewParentId] = useState('');
  const [newChainBonus, setNewChainBonus] = useState(2);
  const [importMessage, setImportMessage] = useState<string | null>(null);
  const [soundMessage, setSoundMessage] = useState<string | null>(null);
  const [pendingSlot, setPendingSlot] = useState<SfxSlot>('light');
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const audioInputRef = useRef<HTMLInputElement | null>(null);

  const rootCandidates = data.tasks.filter((t) => !t.parentId);
  const customNames = data.settings.customSoundNames ?? {};

  const handleSelectProfile = (profile: SoundProfile) => {
    preloadSoundPack(profile, customNames);
    onUpdateSettings({ soundProfile: profile, soundEnabled: true });
    playSampleSlot(profile, 'heavy', data.settings.volume, Boolean(customNames.heavy));
  };

  const handleTriggerSlotUpload = (slot: SfxSlot) => {
    setPendingSlot(slot);
    audioInputRef.current?.click();
  };

  const handleUploadCustomSound = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      if (file.size > 5_000_000) {
        setSoundMessage('5MB以下の効果音ファイルを選んでください');
        return;
      }
      await registerCustomSlotAudio(pendingSlot, file);
      const nextNames = { ...customNames, [pendingSlot]: file.name };
      onUpdateSettings({ customSoundNames: nextNames, soundEnabled: true });
      setSoundMessage(`登録完了：${file.name}`);
      playSampleSlot(data.settings.soundProfile, pendingSlot, data.settings.volume, true);
    } catch {
      setSoundMessage('音声ファイルの読み込みに失敗しました');
    } finally {
      e.target.value = '';
    }
  };

  const handleClearSlot = async (slot: SfxSlot) => {
    await clearCustomSlotAudio(slot);
    const nextNames = { ...customNames };
    delete nextNames[slot];
    onUpdateSettings({ customSoundNames: nextNames });
  };

  const handleCreateTask = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = newName.trim();
    if (!trimmed) return;
    const safePoints = Math.max(1, Math.min(999, Math.round(Number(newPoints) || 1)));
    const id = `task-${Date.now().toString(36)}`;

    const task: TaskItem = {
      id,
      name: trimmed,
      code: trimmed,
      points: safePoints,
      icon: newIcon,
      span: newParentId ? 'half' : newSpan,
      ...(newParentId
        ? {
            parentId: newParentId,
            chainWindowMinutes: 120,
            chainBonus: Math.max(0, Math.min(99, Math.round(Number(newChainBonus) || 0))),
          }
        : {}),
    };

    onAddTask(task);
    setNewName('');
    setNewPoints(5);
    setNewParentId('');
  };

  const handleImportFile = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const parsed = parseImportedJson(text);
      onImportData(parsed);
      setImportMessage(`読み込み完了：項目 ${parsed.tasks.length}件 / 履歴 ${parsed.logs.length}件`);
    } catch (err) {
      setImportMessage(err instanceof Error ? err.message : 'ファイルの読み込みに失敗しました');
    } finally {
      e.target.value = '';
    }
  };

  return (
    <section className="card config-card">
      <button
        type="button"
        className="config-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="config-toggle__title">
          <Settings size={16} strokeWidth={1.9} />
          設定・効果音・項目編集
        </span>
        <span className="config-toggle__caret">
          {open ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
        </span>
      </button>

      {open && (
        <div className="config-body">
          {/* 効果音パック・個別カスタム */}
          <div className="config-group">
            <div className="config-group__title">標準の効果音パック</div>

            <div className="sound-grid">
              {SOUND_PROFILES.map((p) => {
                const active = data.settings.soundProfile === p.value;
                return (
                  <button
                    key={p.value}
                    type="button"
                    className={`sound-card ${active ? 'is-active' : ''}`}
                    onClick={() => handleSelectProfile(p.value)}
                  >
                    <span className="sound-card__name">{p.label}</span>
                    <span className="sound-card__desc">{p.desc}</span>
                  </button>
                );
              })}
            </div>

            <div className="config-group__title" style={{ marginTop: 6 }}>
              枠ごとの試聴・手持ち音源の差し替え（MP3 / WAV / OGG）
            </div>
            <div className="slot-list">
              {SFX_SLOTS.map((slot) => {
                const customFile = customNames[slot.key];
                return (
                  <div key={slot.key} className="slot-row">
                    <div className="slot-row__info">
                      <span className="slot-row__label">{slot.label}</span>
                      <span className="slot-row__name">
                        {customFile ? customFile : '標準パックを使用'}
                      </span>
                    </div>
                    <div className="slot-row__actions">
                      <button
                        type="button"
                        className="icon-btn"
                        title="試聴"
                        onClick={() =>
                          playSampleSlot(
                            data.settings.soundProfile,
                            slot.key,
                            data.settings.volume,
                            Boolean(customFile)
                          )
                        }
                      >
                        <Play size={13} />
                      </button>
                      <button
                        type="button"
                        className="mini-btn"
                        onClick={() => handleTriggerSlotUpload(slot.key)}
                      >
                        <Music size={12} />
                        変更
                      </button>
                      {customFile && (
                        <button
                          type="button"
                          className="icon-btn"
                          title="標準に戻す"
                          onClick={() => void handleClearSlot(slot.key)}
                        >
                          <X size={13} />
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
            <input
              ref={audioInputRef}
              type="file"
              accept="audio/*"
              className="sr-only"
              onChange={(e) => void handleUploadCustomSound(e)}
            />
            {soundMessage && <div className="config-note">{soundMessage}</div>}

            <div className="config-row">
              <label className="config-label">
                <Volume2 size={14} />
                音量 <span className="num">{Math.round(data.settings.volume * 100)}%</span>
              </label>
              <div className="config-slider-wrap">
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={5}
                  value={Math.round(data.settings.volume * 100)}
                  onChange={(e) => onUpdateSettings({ volume: Number(e.target.value) / 100 })}
                />
              </div>
            </div>

            <div className="config-row">
              <label className="config-label">
                <Vibrate size={14} />
                タップ時の振動（Android）
              </label>
              <button
                type="button"
                className={`toggle-pill ${data.settings.hapticsEnabled ? 'is-on' : ''}`}
                onClick={() =>
                  onUpdateSettings({ hapticsEnabled: !data.settings.hapticsEnabled })
                }
              >
                {data.settings.hapticsEnabled ? 'オン' : 'オフ'}
              </button>
            </div>
          </div>

          {/* 既存項目編集 */}
          <div className="config-group">
            <div className="config-group__title">項目の編集・配点</div>
            <div className="task-edit-list">
              {data.tasks.map((task) => {
                const parent = task.parentId
                  ? data.tasks.find((t) => t.id === task.parentId)
                  : undefined;
                return (
                  <div key={task.id} className="task-edit-item">
                    <div className="task-edit-item__head">
                      <span className="task-edit-item__icon">
                        <IconGlyph icon={task.icon} size={15} />
                      </span>
                      <input
                        type="text"
                        className="config-input config-input--inline"
                        value={task.name}
                        onChange={(e) => onUpdateTask(task.id, { name: e.target.value })}
                        aria-label="項目名"
                      />
                      <label className="task-edit-item__pt num">
                        +
                        <input
                          type="number"
                          min={1}
                          max={999}
                          className="config-input config-input--num num"
                          value={task.points}
                          onChange={(e) =>
                            onUpdateTask(task.id, {
                              points: Math.max(1, Math.min(999, Number(e.target.value) || 1)),
                            })
                          }
                        />
                        pt
                      </label>
                      <button
                        type="button"
                        className="icon-btn"
                        onClick={() => onDeleteTask(task.id)}
                        title="削除"
                        aria-label={`${task.name}を削除`}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                    {parent && (
                      <div className="task-edit-item__sub">
                        {parent.name}のあとに連動（+{task.chainBonus ?? 0}pt / {task.chainWindowMinutes ?? 120}分以内）
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* 新規項目追加 */}
          <form className="config-group" onSubmit={handleCreateTask}>
            <div className="config-group__title">項目を追加</div>
            <div className="add-grid">
              <input
                type="text"
                className="config-input"
                placeholder="項目名（例：ストレッチ）"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
              />
              <div className="add-row">
                <label className="add-field">
                  <span>配点</span>
                  <input
                    type="number"
                    min={1}
                    max={999}
                    className="config-input num"
                    value={newPoints}
                    onChange={(e) => setNewPoints(Number(e.target.value))}
                  />
                </label>
                <label className="add-field">
                  <span>アイコン</span>
                  <select
                    className="config-input"
                    value={newIcon}
                    onChange={(e) => setNewIcon(e.target.value as IconKey)}
                  >
                    {ICON_OPTIONS.map((opt) => (
                      <option key={opt.key} value={opt.key}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="add-row">
                <label className="add-field">
                  <span>連動元（任意）</span>
                  <select
                    className="config-input"
                    value={newParentId}
                    onChange={(e) => setNewParentId(e.target.value)}
                  >
                    <option value="">なし（単独ボタン）</option>
                    {rootCandidates.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name}のあと
                      </option>
                    ))}
                  </select>
                </label>
                {newParentId ? (
                  <label className="add-field">
                    <span>連動ボーナス</span>
                    <input
                      type="number"
                      min={0}
                      max={99}
                      className="config-input num"
                      value={newChainBonus}
                      onChange={(e) => setNewChainBonus(Number(e.target.value))}
                    />
                  </label>
                ) : (
                  <label className="add-field">
                    <span>ボタンの大きさ</span>
                    <select
                      className="config-input"
                      value={newSpan}
                      onChange={(e) => setNewSpan(e.target.value as 'half' | 'full')}
                    >
                      <option value="half">標準（2列）</option>
                      <option value="full">大きめ（全幅）</option>
                    </select>
                  </label>
                )}
              </div>
              <button type="submit" className="primary-btn">
                <Plus size={15} />
                この項目を追加
              </button>
            </div>
          </form>

          {/* バックアップ */}
          <div className="config-group">
            <div className="config-group__title">データのバックアップ</div>
            <div className="backup-actions">
              <button
                type="button"
                className="secondary-btn"
                onClick={() => exportAppDataJson(data)}
              >
                <Download size={14} />
                ファイルに保存
              </button>
              <button
                type="button"
                className="secondary-btn"
                onClick={() => fileInputRef.current?.click()}
              >
                <Upload size={14} />
                ファイルから復元
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept="application/json,.json"
                className="sr-only"
                onChange={handleImportFile}
              />
            </div>
            {importMessage && <div className="config-note">{importMessage}</div>}
          </div>
        </div>
      )}
    </section>
  );
}
