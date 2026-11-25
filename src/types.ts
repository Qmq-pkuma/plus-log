export type IconKey =
  | 'pill'
  | 'moon'
  | 'bath'
  | 'droplets'
  | 'flask'
  | 'sparkles'
  | 'sun'
  | 'check'
  | 'zap'
  | 'activity'
  | 'coffee'
  | 'book'
  | 'dumbbell'
  | 'bed'
  | 'shield';

export type SoundProfile = 'handheld_rpg' | 'rpg_poke' | 'dq_fanfare';

export type SfxSlot = 'light' | 'heavy' | 'chain' | 'levelup';

export interface TaskItem {
  id: string;
  name: string;
  code: string;
  points: number;
  icon: IconKey;
  span: 'half' | 'full';
  parentId?: string;
  chainWindowMinutes?: number;
  chainBonus?: number;
}

export interface LogEntry {
  id: string;
  taskId: string;
  taskName: string;
  taskCode: string;
  points: number;
  basePoints: number;
  chainBonus: number;
  timestamp: number;
  taskTotalCount: number;
  totalPointsAfter: number;
  leveledUpTo?: number;
  systemNote: string;
}

export interface AppSettings {
  soundEnabled: boolean;
  volume: number; // 0.0 - 1.0
  soundProfile: SoundProfile;
  hapticsEnabled: boolean;
  customSoundNames?: Partial<Record<SfxSlot, string>>;
}

export interface AppData {
  version: number;
  tasks: TaskItem[];
  logs: LogEntry[];
  settings: AppSettings;
}

export interface LevelProgress {
  level: number;
  totalPoints: number;
  currentLevelPoints: number;
  nextLevelRequired: number;
  ratio: number; // 0 - 1
}
