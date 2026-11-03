const http = require('node:http');
const os = require('node:os');
const fs = require('node:fs');
const fsp = require('node:fs/promises');
const path = require('node:path');
const { URL } = require('node:url');
const { spawn } = require('node:child_process');

const host = '127.0.0.1';
const port = Number(process.env.STUDENT_GROWTH_PORT || 8766);

/**
 * Resolve the student-growth-ops directory without relying on a fixed machine path.
 * Order: env override → sibling of server/ → cwd/student-growth-ops → cwd (when already inside skill root).
 */
function resolveSkillRoot() {
  const envRoot = process.env.STUDENT_GROWTH_OPS_ROOT;
  if (envRoot && envRoot.trim()) {
    return path.resolve(envRoot.trim());
  }

  const fromScript = path.resolve(__dirname, '..');
  const candidates = [
    fromScript,
    path.join(process.cwd(), 'student-growth-ops'),
    process.cwd(),
  ];

  for (const root of candidates) {
    const htmlPath = path.join(root, 'web', 'student-form.html');
    if (fs.existsSync(htmlPath)) {
      return path.resolve(root);
    }
  }

  return fromScript;
}

const skillRoot = resolveSkillRoot();
const questionBankPath = path.join(skillRoot, 'question-bank.json');
const formPagePath = path.join(skillRoot, 'web', 'student-form.html');

if (!fs.existsSync(formPagePath)) {
  console.warn(
    `[student-growth-ops] 未找到网页模板：${formPagePath}。skillRoot=${skillRoot} cwd=${process.cwd()}。可设置环境变量 STUDENT_GROWTH_OPS_ROOT 指向含 web/student-form.html 的目录。`
  );
}

const formSubmissionsDir = path.join(
  os.homedir(),
  '.openclaw',
  'Workspace',
  'student-growth-ops',
  'form-submissions'
);
const studentGrowthOpsRoot = path.join(os.homedir(), 'StudentGrowthOps');
const statusFolders = ['Leads', 'Active', 'RenewalWatch', 'Archived'];

const basicFieldLabels = {
  studentName: '名字',
  englishName: '英文名',
  grade: '年级',
  school: '学校',
  status: '学员状态',
};

function sendJson(res, statusCode, payload) {
  res.writeHead(statusCode, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
  });
  res.end(JSON.stringify(payload));
}

async function readQuestionBank() {
  const raw = await fsp.readFile(questionBankPath, 'utf8');
  return JSON.parse(raw);
}

async function readStudentNameFromProfile(studentDir) {
  const mergedPath = path.join(studentDir, '_data', 'student-record.json');
  try {
    const raw = await fsp.readFile(mergedPath, 'utf8');
    const parsed = JSON.parse(raw);
    const profile = parsed.studentProfile;
    if (!profile || typeof profile !== 'object') {
      return null;
    }
    const name = String(profile.studentName || '').trim();
    if (name) {
      return { studentName: name, profilePath: mergedPath };
    }
  } catch {
    return null;
  }
  return null;
}

async function lookupStudentByName(name) {
  const trimmed = String(name || '').trim();
  if (!trimmed) {
    return { ok: true, found: false, mode: 'unknown' };
  }

  for (const statusFolder of statusFolders) {
    const baseDir = path.join(studentGrowthOpsRoot, statusFolder);
    let entries;
    try {
      entries = await fsp.readdir(baseDir, { withFileTypes: true });
    } catch {
      continue;
    }

    for (const ent of entries) {
      if (!ent.isDirectory()) {
        continue;
      }
      const studentDir = path.join(baseDir, ent.name);
      const profile = await readStudentNameFromProfile(studentDir);
      if (!profile) {
        continue;
      }
      if (profile.studentName === trimmed) {
        return {
          ok: true,
          found: true,
          mode: 'update',
          studentDir,
          folderName: ent.name,
          statusFolder,
          profilePath: profile.profilePath,
        };
      }
    }
  }

  return { ok: true, found: false, mode: 'create' };
}

async function serveFormPage(res) {
  const html = await fsp.readFile(formPagePath, 'utf8');
  res.writeHead(200, {
    'Content-Type': 'text/html; charset=utf-8',
    'Cache-Control': 'no-store',
  });
  res.end(html);
}

function openPath(targetPath) {
  if (process.platform === 'darwin') {
    return spawn('open', [targetPath], { detached: true, stdio: 'ignore' });
  }
  if (process.platform === 'win32') {
    return spawn('cmd', ['/c', 'start', '', targetPath], {
      detached: true,
      stdio: 'ignore',
    });
  }
  return spawn('xdg-open', [targetPath], { detached: true, stdio: 'ignore' });
}

function normalizeValue(value) {
  if (Array.isArray(value)) {
    const cleaned = value
      .map((item) => String(item || '').trim())
      .filter(Boolean);
    return cleaned.join(', ');
  }
  return String(value || '').trim();
}

function buildOutputLines(payload, questionBank) {
  const lines = [];
  const stage = questionBank.stages.find((item) => item.stageId === payload.stageId);
  if (payload.stageTitle) {
    lines.push(`阶段：${payload.stageTitle}`);
  } else if (stage?.title) {
    lines.push(`阶段：${stage.title}`);
  }

  const basics = payload.basics || {};
  for (const [key, label] of Object.entries(basicFieldLabels)) {
    const normalized = normalizeValue(basics[key]);
    if (normalized) {
      lines.push(`${label}：${normalized}`);
    }
  }

  const answers = payload.answers || {};
  for (const question of stage?.questions || []) {
    const normalized = normalizeValue(answers[question.id]);
    if (normalized) {
      lines.push(`${question.prompt}：${normalized}`);
    }
  }

  const extraNote = normalizeValue(payload.extraNote);
  if (extraNote) {
    lines.push(`补充说明：${extraNote}`);
  }

  return lines;
}

async function handleSubmit(req, res) {
  let body = '';
  req.on('data', (chunk) => {
    body += chunk;
    if (body.length > 1024 * 1024) {
      req.destroy(new Error('Payload too large'));
    }
  });

  req.on('end', async () => {
    try {
      const payload = JSON.parse(body || '{}');
      const questionBank = await readQuestionBank();
      const studentName = normalizeValue(payload?.basics?.studentName) || '未命名学生';
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
      const fileName = `${studentName}-${timestamp}.txt`;
      const outputLines = buildOutputLines(payload, questionBank);

      await fsp.mkdir(formSubmissionsDir, { recursive: true });
      const outputPath = path.join(formSubmissionsDir, fileName);
      await fsp.writeFile(outputPath, `${outputLines.join('\n')}\n`, 'utf8');

      sendJson(res, 200, {
        ok: true,
        fileName,
        filePath: outputPath,
      });
    } catch (error) {
      sendJson(res, 400, {
        ok: false,
        error: error instanceof Error ? error.message : '提交失败',
      });
    }
  });
}

const server = http.createServer(async (req, res) => {
  try {
    const requestUrl = new URL(req.url || '/', `http://${host}:${port}`);

    if (req.method === 'GET' && requestUrl.pathname === '/student-form') {
      await serveFormPage(res);
      return;
    }

    if (req.method === 'GET' && requestUrl.pathname === '/api/question-bank') {
      const questionBank = await readQuestionBank();
      sendJson(res, 200, questionBank);
      return;
    }

    if (req.method === 'GET' && requestUrl.pathname === '/api/health') {
      sendJson(res, 200, {
        ok: true,
        host,
        port,
        skillRoot,
        formPagePath,
        formSubmissionsDir,
        studentGrowthOpsRoot,
        studentFormUrl: `http://${host}:${port}/student-form`,
      });
      return;
    }

    if (req.method === 'GET' && requestUrl.pathname === '/api/lookup-student') {
      const name = requestUrl.searchParams.get('name') || '';
      const result = await lookupStudentByName(name);
      sendJson(res, 200, result);
      return;
    }

    if (req.method === 'POST' && requestUrl.pathname === '/api/open-submissions') {
      await fsp.mkdir(formSubmissionsDir, { recursive: true });
      const child = openPath(formSubmissionsDir);
      child.unref();
      sendJson(res, 200, {
        ok: true,
        formSubmissionsDir,
      });
      return;
    }

    if (req.method === 'POST' && requestUrl.pathname === '/api/submit') {
      await handleSubmit(req, res);
      return;
    }

    sendJson(res, 404, { ok: false, error: 'Not Found' });
  } catch (error) {
    sendJson(res, 500, {
      ok: false,
      error: error instanceof Error ? error.message : '服务器错误',
    });
  }
});

server.listen(port, host, () => {
  console.log(`Student growth form server running at http://${host}:${port}/student-form`);
});
