import { readFileSync, realpathSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { Command } from 'commander';
import { authCommand } from './commands/auth.js';
import { configCommand } from './commands/config.js';
import { genomeCommand } from './commands/genome.js';
import { infoCommand } from './commands/info.js';
import { initCommand } from './commands/init.js';
import { installCommand } from './commands/install.js';
import { learnCommand } from './commands/learn.js';
import { listCommand } from './commands/list.js';
import { publishCommand } from './commands/publish.js';
import { searchCommand } from './commands/search.js';
import { templateCommand } from './commands/template.js';
import { uninstallCommand } from './commands/uninstall.js';

export const program = new Command();

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

function loadVersion(): string {
  try {
    const pkg = JSON.parse(readFileSync(join(__dirname, '..', 'package.json'), 'utf-8'));
    return pkg.version ?? '0.0.0';
  } catch {
    return '0.0.0';
  }
}

program.name('genehub').description('GeneHub CLI - AI 员工基因管理工具').version(loadVersion());

program.addCommand(authCommand);
program.addCommand(installCommand);
program.addCommand(uninstallCommand);
program.addCommand(searchCommand);
program.addCommand(infoCommand);
program.addCommand(listCommand);
program.addCommand(publishCommand);
program.addCommand(initCommand);
program.addCommand(configCommand);
program.addCommand(learnCommand);
program.addCommand(genomeCommand);
program.addCommand(templateCommand);

function isDirectRun(): boolean {
  try {
    return realpathSync(process.argv[1]) === realpathSync(__filename);
  } catch {
    return false;
  }
}

if (isDirectRun()) {
  program.parse();
}
