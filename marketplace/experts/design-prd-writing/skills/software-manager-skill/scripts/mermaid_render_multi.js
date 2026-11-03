/**
 * mermaid_render_multi.js
 * 跨平台 Mermaid → PNG 渲染器
 * 自动检测: Chrome → Edge → Firefox → Chromium
 * 支持: Windows / macOS / Linux (含 WSL 环境)
 *
 * 用法: node mermaid_render_multi.js <input.mmd> <output.png> [theme]
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// ============== 平台检测 ==============
function getPlatform() {
  const platform = process.platform;
  if (platform === 'win32') return 'windows';
  if (platform === 'darwin') return 'macos';
  // Linux: 检测是否为 WSL（WSL 中 process.platform 是 linux，但能访问 /mnt/c）
  if (fs.existsSync('/mnt/c/Windows/System32')) return 'wsl';
  return 'linux';
}

// ============== 浏览器路径检测 ==============

// Windows 原生 registry 查询
function queryWinBrowser(key, name) {
  try {
    const out = execSync(`reg query "${key}" /v Path`, { encoding: 'utf8', timeout: 5000 }).trim();
    const match = out.match(/Path\s+REG_SZ\s+(.+)/i);
    if (match && fs.existsSync(match[1].trim())) {
      return { name, path: match[1].trim(), type: name.toLowerCase() };
    }
  } catch (e) {}
  return null;
}

function findWindowsBrowser() {
  const candidates = [];
  const isWsl = getPlatform() === 'wsl';

  // 1. Chrome — registry 查询（Windows 原生）
  const chrome = queryWinBrowser(
    'HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\chrome.exe',
    'Chrome'
  );
  if (chrome) candidates.push(chrome);

  // 2. Edge — registry
  const edge = queryWinBrowser(
    'HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\msedge.exe',
    'Edge'
  );
  if (edge) candidates.push(edge);

  // 3. Firefox — registry
  const firefox = queryWinBrowser(
    'HKLM\\SOFTWARE\\Mozilla\\Mozilla Firefox',
    'Firefox'
  );
  if (firefox) candidates.push(firefox);

  // 4. 常见安装路径（WSL 使用 /mnt/c/ 前缀，原生使用 C:\）
  const prefixes = isWsl ? ['/mnt/c'] : [''];
  for (const prefix of prefixes) {
    const winPaths = [
      [`${prefix}/Program Files/Google/Chrome/Application/chrome.exe`, 'Chrome'],
      [`${prefix}/Program Files (x86)/Google/Chrome/Application/chrome.exe`, 'Chrome'],
      [`${prefix}/Program Files/Microsoft/Edge/Application/msedge.exe`, 'Edge'],
      [`${prefix}/Program Files (x86)/Microsoft/Edge/Application/msedge.exe`, 'Edge'],
      [`${prefix}/Program Files/Mozilla Firefox/firefox.exe`, 'Firefox'],
      [`${prefix}/Program Files (x86)/Mozilla Firefox/firefox.exe`, 'Firefox'],
    ];
    for (const [p, n] of winPaths) {
      if (fs.existsSync(p)) {
        candidates.push({ name: n, path: p, type: n.toLowerCase() });
      }
    }
  }

  // 优先级: Chrome > Edge > Firefox
  const priority = ['chrome', 'edge', 'firefox'];
  for (const t of priority) {
    const found = candidates.find(b => b.type === t);
    if (found) return found;
  }
  return candidates[0] || null;
}

function findMacOSBrowser() {
  const candidates = [];
  const macPaths = [
    ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', 'Chrome'],
    ['/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge', 'Edge'],
    ['/Applications/Firefox.app/Contents/MacOS/firefox', 'Firefox'],
    ['/Applications/Chromium.app/Contents/MacOS/Chromium', 'Chromium'],
  ];
  for (const [p, n] of macPaths) {
    if (fs.existsSync(p)) {
      candidates.push({ name: n, path: p, type: n.toLowerCase() });
    }
  }

  const priority = ['chrome', 'edge', 'firefox'];
  for (const t of priority) {
    const found = candidates.find(b => b.type === t);
    if (found) return found;
  }
  return candidates[0] || null;
}

function findLinuxBrowser() {
  const candidates = [];
  const tools = [
    ['google-chrome', 'Chrome'],
    ['chromium-browser', 'Chromium'],
    ['chromium', 'Chromium'],
    ['msedge', 'Edge'],
    ['firefox', 'Firefox'],
  ];
  for (const [cmd, name] of tools) {
    try {
      const result = execSync(`which ${cmd}`, { encoding: 'utf8', timeout: 5000 }).trim();
      if (result && fs.existsSync(result)) {
        candidates.push({ name, path: result, type: name.toLowerCase() });
      }
    } catch (e) {}
  }

  const priority = ['chrome', 'edge', 'firefox'];
  for (const t of priority) {
    const found = candidates.find(b => b.type === t);
    if (found) return found;
  }
  return candidates[0] || null;
}

function findBrowser() {
  const platform = getPlatform();
  if (platform === 'windows') return findWindowsBrowser();
  if (platform === 'macos') return findMacOSBrowser();
  // WSL 使用 Windows 浏览器（通过 /mnt/c/ 路径）
  if (platform === 'wsl') return findWindowsBrowser();
  return findLinuxBrowser(); // 纯 Linux
}

// ============== Windows 用户名获取（WSL 专用） ==============
function getWindowsUser() {
  // 方法1: 从 /mnt/c/Users 目录扫描，找有 AppData/Roaming/npm 的用户
  try {
    const entries = fs.readdirSync('/mnt/c/Users');
    for (const u of entries) {
      const npmPath = path.join('/mnt/c/Users', u, 'AppData', 'Roaming', 'npm');
      if (fs.existsSync(npmPath)) {
        return u;
      }
    }
  } catch (e) {}

  // 方法2: 从 whoami 获取
  try {
    const whoamiOut = execSync(
      '/mnt/c/Windows/System32/whoami.exe', { encoding: 'utf8', timeout: 5000 }
    ).trim();
    return whoamiOut.split('\\').pop();
  } catch (e) {}

  return null;
}

// ============== puppeteer-core 查找 ==============
function findPuppeteerCore() {
  // 方法1: 从脚本所在目录向上搜索 node_modules
  const scriptDir = path.dirname(process.argv[1] || __filename);
  let dir = scriptDir;
  for (let i = 0; i < 6; i++) {
    const pp = path.join(dir, 'node_modules', 'puppeteer-core');
    if (fs.existsSync(path.join(pp, 'package.json'))) {
      return pp;
    }
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }

  // 方法2: npm root -g
  try {
    const npmRoot = execSync('npm root -g', { encoding: 'utf8', timeout: 5000 }).trim();
    const pp = path.join(npmRoot, 'puppeteer-core');
    if (fs.existsSync(path.join(pp, 'package.json'))) {
      return pp;
    }
    // 也检查 @mermaid-js/mermaid-cli 的 bundled puppeteer-core
    const mmdc = path.join(npmRoot, '@mermaid-js', 'mermaid-cli', 'node_modules', 'puppeteer-core');
    if (fs.existsSync(path.join(mmdc, 'package.json'))) {
      return mmdc;
    }
  } catch (e) {}

  // 方法3: WSL 下从 /mnt/c 找用户 npm 全局路径
  if (fs.existsSync('/mnt/c/Users')) {
    try {
      const entries = fs.readdirSync('/mnt/c/Users');
      for (const u of entries) {
        const npmPaths = [
          `/mnt/c/Users/${u}/AppData/Roaming/npm/node_modules/@mermaid-js/mermaid-cli/node_modules/puppeteer-core`,
          `/mnt/c/Users/${u}/AppData/Roaming/npm/node_modules/puppeteer-core`,
        ];
        for (const p of npmPaths) {
          if (fs.existsSync(path.join(p, 'package.json'))) {
            return p;
          }
        }
      }
    } catch (e) {}
  }

  return null;
}

// ============== mermaid.min.js 查找（本地文件，无 CDN） ==============
function findMermaidMinJs(tmpDir) {
  // 优先：tmpDir 目录（已预置的 mermaid.min.js）
  const tmpPath = path.join(tmpDir, 'mermaid.min.js');
  if (fs.existsSync(tmpPath)) return tmpPath;

  // 标准路径搜索
  const searchPaths = [
    // WSL 共享目录
    '/home/yhongm/.share/hermes-assets/mermaid/mermaid.min.js',
    // Windows npm 全局
    'C:\\Users\\yhong\\AppData\\Roaming\\npm\\node_modules\\@mermaid-js\\mermaid-cli\\node_modules\\mermaid\\dist\\mermaid.min.js',
    'C:\\Users\\yhongm\\AppData\\Roaming\\npm\\node_modules\\@mermaid-js\\mermaid-cli\\node_modules\\mermaid\\dist\\mermaid.min.js',
    // Windows 用户目录
    'C:\\Users\\yhong\\AppData\\Local\\Temp\\mermaid.min.js',
    // WSL npm 全局
    '/home/yhongm/.hermes/node/lib/node_modules/@mermaid-js/mermaid-cli/node_modules/mermaid/dist/mermaid.min.js',
  ];

  for (const p of searchPaths) {
    if (fs.existsSync(p)) return p;
  }

  // 动态搜索：向上查 node_modules
  const scriptDir = path.dirname(process.argv[1] || __filename);
  let dir = scriptDir;
  for (let i = 0; i < 6; i++) {
    const mmPath = path.join(dir, 'node_modules', 'mermaid', 'dist', 'mermaid.min.js');
    if (fs.existsSync(mmPath)) return mmPath;
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }

  return null;
}

// ============== 临时目录 ==============
function getTempDir() {
  const platform = getPlatform();

  if (platform === 'windows') {
    return process.env.TEMP || process.env.TMP || 'C:\\Temp';
  }
  if (platform === 'macos') {
    return process.env.TMPDIR || '/tmp';
  }
  if (platform === 'wsl') {
    // WSL: 必须写入 Windows Temp 目录（/mnt/c/Users/{user}/AppData/Local/Temp）
    // Windows Chrome 无法访问 WSL 的 /tmp
    const winUser = getWindowsUser();
    if (winUser) {
      return `/mnt/c/Users/${winUser}/AppData/Local/Temp`;
    }
  }
  return '/tmp';
}

// ============== 浏览器启动 ==============
async function launchBrowser(executablePath, type) {
  const puppeteerCorePath = findPuppeteerCore();
  if (!puppeteerCorePath) {
    throw new Error('puppeteer-core not found. Please run: npm install -g @mermaid-js/mermaid-cli');
  }
  const puppeteer = require(puppeteerCorePath);

  const args = ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'];
  // Chrome/Edge 需要允许 file:// 访问
  if (type !== 'firefox') {
    args.push('--allow-file-access-from-files');
  }

  return puppeteer.launch({
    executablePath,
    headless: true,
    args,
  });
}

// ============== Mermaid 渲染 ==============
async function renderMermaid(mmdContent, outputPath, theme = 'default') {
  const browserInfo = findBrowser();
  if (!browserInfo) {
    throw new Error('No supported browser found. Please install Chrome, Edge, or Firefox.');
  }
  console.error(`Using browser: ${browserInfo.name} (${browserInfo.path})`);

  // 优先使用本地 mermaid.min.js（WSL 环境下 CDN 不可用）
  const tmpDir = getTempDir();
  const mmScriptPath = findMermaidMinJs(tmpDir);
  if (!mmScriptPath) {
    throw new Error('mermaid.min.js not found. Please ensure the render script is properly installed.');
  }
  const mmScriptContent = fs.readFileSync(mmScriptPath, 'utf8');

  const htmlContent = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <script>
${mmScriptContent}
  </script>
  <script>
    window.renderMermaid = async function(mmd) {
      try {
        await mermaid.initialize({ startOnLoad: false, theme: '${theme}', securityLevel: 'loose' });
        const id = 'graph-' + Math.random().toString(36).substr(2, 9);
        const { svg } = await mermaid.render(id, mmd);
        document.getElementById('container').innerHTML = svg;
        window.renderSuccess = true;
      } catch (e) {
        window.renderError = e.message;
      }
    };
    window.mermaidReady = true;
  </script>
  <style>
    body { margin: 0; padding: 0; background: white; }
    #container { display: inline-block; }
  </style>
</head>
<body>
  <div id="container"></div>
</body>
</html>`;

  const htmlPath = path.join(tmpDir, `mermaid_render_${Date.now()}.html`);
  fs.writeFileSync(htmlPath, htmlContent);

  // file:// URL 跨平台处理
  let fileUrl;
  const platform = getPlatform();
  if (platform === 'windows') {
    // Windows: C:\path\to\file -> file:///C:/path/to/file
    fileUrl = 'file:///' + htmlPath.replace(/\\/g, '/');
  } else if (platform === 'wsl') {
    // WSL: /mnt/c/Users/... -> file:///C:/Users/...
    fileUrl = 'file://' + htmlPath.replace('/mnt/c/', '/C:/').replace(/\\/g, '/');
  } else {
    // macOS / Linux
    fileUrl = 'file://' + htmlPath;
  }

  let browser;
  try {
    browser = await launchBrowser(browserInfo.path, browserInfo.type);
    const page = await browser.newPage();

    await page.goto(fileUrl, { waitUntil: 'networkidle0', timeout: 15000 });
    await page.waitForFunction(() => window.mermaidReady === true, { timeout: 10000 });

    await page.evaluate((m) => window.renderMermaid(m), mmdContent);

    await page.waitForFunction(
      () => window.renderSuccess === true || window.renderError !== undefined,
      { timeout: 15000 }
    );

    const error = await page.evaluate(() => window.renderError);
    if (error) throw new Error('Mermaid: ' + error);

    const element = await page.$('#container');
    if (!element) throw new Error('Container element not found');

    const buf = await element.screenshot({ type: 'png' });
    fs.writeFileSync(outputPath, buf);
    console.error(`Saved: ${outputPath}`);

  } finally {
    if (browser) await browser.close();
    try { fs.unlinkSync(htmlPath); } catch (e) {}
  }
}

// ============== 主函数 ==============
const inputFile = process.argv[2];
const outputFile = process.argv[3];
const theme = process.argv[4] || 'default';

if (!inputFile || !outputFile) {
  console.error('Usage: node mermaid_render_multi.js <input.mmd> <output.png> [theme]');
  process.exit(1);
}
if (!fs.existsSync(inputFile)) {
  console.error(`Input file not found: ${inputFile}`);
  process.exit(1);
}

const mmdContent = fs.readFileSync(inputFile, 'utf8');
renderMermaid(mmdContent, outputFile, theme)
  .then(() => console.log('SUCCESS'))
  .catch(err => { console.error('ERROR:', err.message); process.exit(1); });
