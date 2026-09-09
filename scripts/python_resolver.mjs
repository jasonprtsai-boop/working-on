import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export const PROJECT_ROOT = path.resolve(__dirname, '..');

function isWindows() {
  return process.platform === 'win32';
}

function isPathLike(command) {
  return path.isAbsolute(command) || command.includes('/') || command.includes('\\');
}

function existingPath(command) {
  return !isPathLike(command) || fs.existsSync(command);
}

function pythonCandidate(label, command, argsPrefix = []) {
  return { label, command, argsPrefix };
}

export function pythonCandidates(root = PROJECT_ROOT) {
  const candidates = [];
  const envPython = process.env.SMART_CHESS_PYTHON || process.env.PYTHON_EXE;
  if (envPython) {
    candidates.push(pythonCandidate('environment override', envPython));
  }

  candidates.push(
    pythonCandidate(
      'project virtualenv',
      isWindows()
        ? path.join(root, '.venv', 'Scripts', 'python.exe')
        : path.join(root, '.venv', 'bin', 'python'),
    ),
  );

  if (isWindows()) {
    for (const version of ['3.11', '3.12', '3.10', '3.9']) {
      candidates.push(pythonCandidate(`Python launcher ${version}`, 'py.exe', [`-${version}`]));
    }
    candidates.push(pythonCandidate('python on PATH', 'python.exe'));
  } else {
    candidates.push(pythonCandidate('python3 on PATH', 'python3'));
    candidates.push(pythonCandidate('python on PATH', 'python'));
  }

  return candidates;
}

export function testPythonCandidate(candidate, root = PROJECT_ROOT) {
  if (!existingPath(candidate.command)) {
    return { ...candidate, ok: false, detail: 'not found' };
  }

  const result = spawnSync(candidate.command, [...candidate.argsPrefix, '--version'], {
    cwd: root,
    encoding: 'utf8',
    windowsHide: true,
  });
  const output = `${result.stdout || ''}${result.stderr || ''}`.trim();
  if (result.error) {
    return { ...candidate, ok: false, detail: result.error.message || 'not executable' };
  }
  if (result.status !== 0) {
    return { ...candidate, ok: false, detail: output || `exit ${result.status}` };
  }

  return { ...candidate, ok: true, detail: output || 'Python detected' };
}

export function resolvePythonCommand(root = PROJECT_ROOT) {
  const attempts = pythonCandidates(root).map((candidate) => testPythonCandidate(candidate, root));
  const match = attempts.find((attempt) => attempt.ok);
  if (match) {
    return {
      command: match.command,
      argsPrefix: match.argsPrefix,
      label: match.label,
      version: match.detail,
      attempts,
    };
  }

  const error = new Error('No usable Python runtime was found for this project.');
  error.attempts = attempts;
  throw error;
}

export function formatPythonResolutionFailure(error) {
  const attempts = Array.isArray(error?.attempts) ? error.attempts : [];
  const lines = [
    'No usable Python runtime was found for this project.',
    '',
    'Checked:',
    ...attempts.map((attempt) => `- ${attempt.label}: ${attempt.detail}`),
    '',
    'Fix: run setup_env.ps1 after installing Python 3.11, or set SMART_CHESS_PYTHON to a working python.exe.',
  ];
  return lines.join('\n');
}
