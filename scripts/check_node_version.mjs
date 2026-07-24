import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const pkg = JSON.parse(readFileSync(resolve(root, 'package.json'), 'utf8'));
const nodeMajor = Number(process.versions.node.split('.')[0]);
const nodeRange = pkg.engines?.node || '';
const expectedNodeMajor = Number(nodeRange.match(/>=\s*(\d+)\./)?.[1]);
const npmRange = pkg.engines?.npm || '';
const expectedNpmMajor = Number(npmRange.match(/>=\s*(\d+)/)?.[1]);
const npmVersion = process.env.npm_config_user_agent?.match(/npm\/([\d.]+)/)?.[1] || '';
const npmMajor = npmVersion ? Number(npmVersion.split('.')[0]) : null;

const failures = [];
if (!Number.isFinite(expectedNodeMajor) || nodeMajor !== expectedNodeMajor) {
  failures.push(`Node ${nodeRange || '24.x'} is required; current is ${process.version}.`);
}
if (npmMajor !== null && Number.isFinite(expectedNpmMajor) && npmMajor < expectedNpmMajor) {
  failures.push(`npm ${npmRange} is required; current is ${npmVersion}.`);
}

if (failures.length) {
  console.error('Version check failed:');
  for (const failure of failures) {
    console.error(`- ${failure}`);
  }
  console.error('Use scripts\\npm24.cmd for this project on Windows.');
  process.exit(1);
}

console.log(`Version check OK: node ${process.version}${npmVersion ? `, npm ${npmVersion}` : ''}.`);
