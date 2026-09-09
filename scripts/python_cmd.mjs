import { spawnSync } from 'node:child_process';
import { formatPythonResolutionFailure, PROJECT_ROOT, resolvePythonCommand } from './python_resolver.mjs';

let python;
try {
  python = resolvePythonCommand(PROJECT_ROOT);
} catch (error) {
  console.error(formatPythonResolutionFailure(error));
  process.exit(1);
}

const args = process.argv.slice(2);
const result = spawnSync(
  python.command,
  [...python.argsPrefix, ...(args.length ? args : ['--version'])],
  {
    cwd: PROJECT_ROOT,
    env: process.env,
    stdio: 'inherit',
    windowsHide: true,
  },
);

if (result.error) {
  console.error(result.error.message || 'Python command failed.');
  process.exit(1);
}

if (result.signal) {
  console.error(`Python command stopped by signal ${result.signal}.`);
  process.exit(1);
}

process.exit(result.status ?? 1);
