import chalk from 'chalk';
import Table from 'cli-table3';

export function info(msg: string) {
  console.log(chalk.blue('i'), msg);
}

export function ok(msg: string) {
  console.log(chalk.green('+'), msg);
}

export function warn(msg: string) {
  console.log(chalk.yellow('!'), msg);
}

export function fail(msg: string) {
  console.error(chalk.red('x'), msg);
}

export function table(headers: string[], rows: string[][]) {
  const t = new Table({
    head: headers.map((h) => chalk.cyan(h)),
    style: { head: [], border: [] },
  });
  for (const row of rows) {
    t.push(row);
  }
  console.log(t.toString());
}
