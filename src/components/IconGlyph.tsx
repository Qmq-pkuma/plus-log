import {
  Activity,
  Bath,
  Bed,
  BookOpen,
  Check,
  Coffee,
  Droplets,
  Dumbbell,
  FlaskConical,
  Moon,
  Pill,
  Shield,
  Sparkles,
  Sun,
  Zap,
} from 'lucide-react';
import type { IconKey } from '../types';

export const ICON_OPTIONS: { key: IconKey; label: string }[] = [
  { key: 'sun', label: '朝・太陽' },
  { key: 'moon', label: '夜・月' },
  { key: 'pill', label: '薬' },
  { key: 'bath', label: '風呂' },
  { key: 'droplets', label: '保湿・水' },
  { key: 'flask', label: '塗り薬' },
  { key: 'sparkles', label: '歯磨き・ケア' },
  { key: 'check', label: 'チェック' },
  { key: 'zap', label: 'クイック' },
  { key: 'activity', label: '運動・体調' },
  { key: 'coffee', label: '飲食' },
  { key: 'book', label: '読書・作業' },
  { key: 'dumbbell', label: 'トレーニング' },
  { key: 'bed', label: '休息' },
  { key: 'shield', label: '防御・メンテ' },
];

export function IconGlyph({
  icon,
  size = 20,
  className,
}: {
  icon: IconKey;
  size?: number;
  className?: string;
}) {
  const props = { size, strokeWidth: 1.8, className, 'aria-hidden': true as const };
  switch (icon) {
    case 'pill':
      return <Pill {...props} />;
    case 'moon':
      return <Moon {...props} />;
    case 'bath':
      return <Bath {...props} />;
    case 'droplets':
      return <Droplets {...props} />;
    case 'flask':
      return <FlaskConical {...props} />;
    case 'sparkles':
      return <Sparkles {...props} />;
    case 'sun':
      return <Sun {...props} />;
    case 'check':
      return <Check {...props} />;
    case 'zap':
      return <Zap {...props} />;
    case 'activity':
      return <Activity {...props} />;
    case 'coffee':
      return <Coffee {...props} />;
    case 'book':
      return <BookOpen {...props} />;
    case 'dumbbell':
      return <Dumbbell {...props} />;
    case 'bed':
      return <Bed {...props} />;
    case 'shield':
      return <Shield {...props} />;
    default:
      return <Check {...props} />;
  }
}
