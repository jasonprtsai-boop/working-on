import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, extname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const cssRoot = join(root, 'frontend', 'static', 'css');
const files = collectCssFiles(cssRoot);
const failures = [];

for (const file of files) {
  failures.push(...checkCssFile(file));
}

if (failures.length) {
  console.error('CSS integrity check failed:');
  for (const failure of failures) {
    console.error(`- ${failure}`);
  }
  process.exit(1);
}

console.log(`CSS integrity OK: ${files.length} files checked.`);

function collectCssFiles(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    const stat = statSync(path);
    if (stat.isDirectory()) {
      out.push(...collectCssFiles(path));
    } else if (stat.isFile() && extname(path).toLowerCase() === '.css') {
      out.push(path);
    }
  }
  return out.sort();
}

function checkCssFile(file) {
  const text = readFileSync(file, 'utf8');
  const rel = relative(root, file).replace(/\\/g, '/');
  const issues = [];
  let depth = 0;
  let line = 1;
  let inComment = false;
  let quote = '';
  let escaped = false;
  let lineStartDepth = 0;
  let currentLine = '';

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const next = text[index + 1] || '';

    if (char === '\n') {
      checkTopLevelDeclaration(rel, line, currentLine, lineStartDepth, issues);
      line += 1;
      currentLine = '';
      lineStartDepth = depth;
      escaped = false;
      continue;
    }

    currentLine += char;

    if (inComment) {
      if (char === '*' && next === '/') {
        inComment = false;
        currentLine += next;
        index += 1;
      }
      continue;
    }

    if (quote) {
      if (escaped) {
        escaped = false;
      } else if (char === '\\') {
        escaped = true;
      } else if (char === quote) {
        quote = '';
      }
      continue;
    }

    if (char === '/' && next === '*') {
      inComment = true;
      currentLine += next;
      index += 1;
      continue;
    }

    if (char === '"' || char === "'") {
      quote = char;
      continue;
    }

    if (char === '{') {
      depth += 1;
    } else if (char === '}') {
      depth -= 1;
      if (depth < 0) {
        issues.push(`${rel}:${line}: unexpected closing brace`);
        depth = 0;
      }
    }
  }

  checkTopLevelDeclaration(rel, line, currentLine, lineStartDepth, issues);

  if (depth !== 0) {
    issues.push(`${rel}: unbalanced braces; final depth is ${depth}`);
  }
  if (inComment) {
    issues.push(`${rel}: unterminated block comment`);
  }
  if (quote) {
    issues.push(`${rel}: unterminated string literal`);
  }
  return issues;
}

function checkTopLevelDeclaration(rel, line, rawLine, depth, issues) {
  const lineText = rawLine.replace(/\/\*.*?\*\//g, '').trim();
  if (!lineText || depth !== 0) return;
  if (/^[a-z-]+\s*:[^;{}]+;\s*$/i.test(lineText)) {
    issues.push(`${rel}:${line}: declaration is outside a selector: ${lineText}`);
  }
}
