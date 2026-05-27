import LucideIcon from '@/components/LucideIcon';

const CATEGORIES = [
  { id: 'development', label: '开发', icon: 'Code2' },
  { id: 'efficiency', label: '效率', icon: 'Zap' },
  { id: 'data', label: '数据', icon: 'BarChart2' },
  { id: 'communication', label: '沟通', icon: 'MessageCircle' },
  { id: 'creative', label: '创意', icon: 'Palette' },
  { id: 'security', label: '安全', icon: 'Shield' },
  { id: 'operations', label: '运维', icon: 'Wrench' },
  { id: 'network', label: '网络', icon: 'Globe' },
] as const;

export default function CategoryNav({
  active,
  onChange,
}: {
  active: string;
  onChange: (cat: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      <button
        type="button"
        onClick={() => onChange('')}
        className={`px-3 py-1.5 rounded-lg text-sm font-medium transition ${
          active === ''
            ? 'bg-primary text-white'
            : 'bg-surface border border-border text-muted hover:text-gray-900 hover:border-gray-300'
        }`}
      >
        全部
      </button>
      {CATEGORIES.map((cat) => (
        <button
          type="button"
          key={cat.id}
          onClick={() => onChange(cat.id)}
          className={`px-3 py-1.5 rounded-lg text-sm font-medium transition ${
            active === cat.id
              ? 'bg-primary text-white'
              : 'bg-surface border border-border text-muted hover:text-gray-900 hover:border-gray-300'
          }`}
        >
          <span className="inline-flex items-center gap-1.5">
            <LucideIcon name={cat.icon} className="w-3.5 h-3.5 shrink-0" />
            {cat.label}
          </span>
        </button>
      ))}
    </div>
  );
}
