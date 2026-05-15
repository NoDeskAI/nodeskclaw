import type { GeneAdapter } from '@nodeskai/genehub-types';
import { GenericAdapter } from './generic.js';
import { NanobotAdapter } from './nanobot.js';
import { OpenClawAdapter } from './openclaw.js';

const ADAPTERS: (() => GeneAdapter)[] = [
  () => new OpenClawAdapter(),
  () => new NanobotAdapter(),
  () => new GenericAdapter(),
];

export async function detectAdapter(): Promise<GeneAdapter> {
  for (const create of ADAPTERS) {
    const adapter = create();
    if (await adapter.detect()) {
      return adapter;
    }
  }
  return new GenericAdapter();
}

export function getAdapter(product: string): GeneAdapter {
  switch (product) {
    case 'openclaw':
      return new OpenClawAdapter();
    case 'nanobot':
      return new NanobotAdapter();
    default:
      return new GenericAdapter();
  }
}
