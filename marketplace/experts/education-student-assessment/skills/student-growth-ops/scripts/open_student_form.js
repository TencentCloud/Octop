#!/usr/bin/env node
const http = require('node:http');
const path = require('node:path');
const { spawn } = require('node:child_process');

const host = '127.0.0.1';
const port = Number(process.env.STUDENT_GROWTH_PORT || 8766);
const serverEntry = path.resolve(__dirname, '..', 'server', 'index.js');

function requestHealth() {
  return new Promise((resolve, reject) => {
    const req = http.get(
      {
        host,
        port,
        path: '/api/health',
        timeout: 1200,
      },
      (res) => {
        let body = '';
        res.on('data', (chunk) => {
          body += chunk;
        });
        res.on('end', () => {
          if (res.statusCode === 200) {
            resolve(body);
            return;
          }
          reject(new Error(`Health check failed with status ${res.statusCode}`));
        });
      }
    );

    req.on('error', reject);
    req.on('timeout', () => {
      req.destroy(new Error('Health check timeout'));
    });
  });
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function buildFormUrl() {
  const params = new URLSearchParams();
  for (const arg of process.argv.slice(2)) {
    const match = arg.match(/^--([^=]+)=(.*)$/);
    if (match) {
      params.set(match[1], match[2]);
    }
  }

  const query = params.toString();
  return `http://${host}:${port}/student-form${query ? `?${query}` : ''}`;
}

function openUrl(url) {
  if (process.platform === 'darwin') {
    spawn('open', [url], { detached: true, stdio: 'ignore' }).unref();
    return;
  }
  if (process.platform === 'win32') {
    spawn('cmd', ['/c', 'start', '', url], { detached: true, stdio: 'ignore' }).unref();
    return;
  }
  spawn('xdg-open', [url], { detached: true, stdio: 'ignore' }).unref();
}

async function ensureServerRunning() {
  try {
    await requestHealth();
    return;
  } catch (_) {
    const child = spawn(process.execPath, [serverEntry], {
      detached: true,
      stdio: 'ignore',
      env: process.env,
    });
    child.unref();
  }

  for (let attempt = 0; attempt < 10; attempt += 1) {
    await sleep(500);
    try {
      await requestHealth();
      return;
    } catch (_) {
      // retry
    }
  }

  throw new Error(
    'student-growth-ops 页面服务启动失败。若端口被占用，可先执行：lsof -nP -iTCP:8766 -sTCP:LISTEN'
  );
}

async function main() {
  await ensureServerRunning();
  const url = buildFormUrl();
  openUrl(url);
  process.stdout.write(`${url}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error.message}\n`);
  process.exit(1);
});
