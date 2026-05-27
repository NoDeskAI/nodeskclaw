import { Dna } from 'lucide-react';
import { DynamicIcon, type IconName } from 'lucide-react/dynamic';
import type { ComponentProps } from 'react';

type LucideIconProps = {
  name: string | null | undefined;
  fallback?: IconName;
} & Omit<ComponentProps<typeof DynamicIcon>, 'name'>;

export default function LucideIcon({ name, fallback, ...props }: LucideIconProps) {
  if (!name) {
    return <Dna {...props} />;
  }

  return <DynamicIcon name={name as IconName} fallback={() => <Dna {...props} />} {...props} />;
}
