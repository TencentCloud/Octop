import assert from "node:assert/strict";
import { execFile, spawn } from "node:child_process";
import { EventEmitter } from "node:events";
import { mkdtemp, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import { trackTree } from "./dev-process.mjs";

const execFileAsync = promisify(execFile);
const supervisorUrl = new URL("./dev-process.mjs", import.meta.url).href;
const supervisorPath = fileURLToPath(supervisorUrl);
const shellPath = fileURLToPath(new URL("./run-dev.sh", import.meta.url));
// The supervisor needs a readable process table. Sandboxes and hardened hosts
// block `ps` outright (sometimes by throwing synchronously); skip those cases
// instead of reporting false failures.
const psBlocked = await (async () => {
  try {
    await execFileAsync("ps", ["-A", "-o", "pid="], { timeout: 2_000 });
    return false;
  } catch {
    return true;
  }
})();
const skipReason = process.platform === "win32" ? "POSIX only" : psBlocked ? "ps unavailable on this host" : false;
const posix = { skip: skipReason, timeout: 15_000 };
const prefix = "DEV_PROCESS_FIXTURE ";

const fixtureSource = String.raw`
import { spawn } from "node:child_process";
import { createInterface } from "node:readline";
const [role, mode, ...extraArgs] = process.argv.slice(2);
const emit = (type, extra = {}) => process.stdout.write("DEV_PROCESS_FIXTURE " + JSON.stringify({ type, role, pid: process.pid, ...extra }) + "\n");
const ready = (tree) => {
  if (process.send) process.send({ tree });
  else emit("ready", { tree });
};
let child;
let terms = 0;
setInterval(() => {}, 1000);
process.on("SIGTERM", () => {
  emit("term", { count: ++terms });
  if (mode === "hang") return;
  if (role === "root" && child) {
    setTimeout(() => child.kill("SIGTERM"), 180);
  } else if (role === "middle" && mode === "graceful") {
    child.kill("SIGTERM");
  } else {
    setTimeout(() => process.exit(0), 50);
  }
});
for (const signal of ["SIGINT", "SIGHUP"]) {
  process.on(signal, () => { emit("unexpected-signal", { signal }); process.exit(91); });
}
emit("started");
if (role === "grandchild" || mode === "stdio") {
  ready([{ role, pid: process.pid }]);
} else {
  const nextRole = role === "root" ? "middle" : "grandchild";
  child = spawn(process.execPath, [process.argv[1], nextRole, mode], {
    detached: nextRole === "grandchild",
    stdio: ["ignore", "inherit", "inherit", "ipc"],
  });
  child.on("error", (error) => { emit("spawn-error", { message: error.message }); process.exit(92); });
  child.on("message", ({ tree }) => ready([{ role, pid: process.pid }, ...tree]));
  child.on("exit", (code, signal) => {
    emit("child-exit", { childPid: child.pid, code, signal });
    if (mode === "graceful") process.exit(0);
  });
}
if (role === "root") {
  const lines = createInterface({ input: process.stdin });
  lines.on("line", (line) => {
    if (line.startsWith("EXIT:")) process.exit(Number(line.slice(5)));
    if (mode === "stdio") {
      emit("echo", { line, args: extraArgs, env: process.env.DEV_PROCESS_TEST_VALUE });
      process.stderr.write("fixture inherited stderr\n");
      process.exit(0);
    }
  });
}
`;

// 不替换 ps 的结果；仅把真实快照经 IPC 回传，避免靠固定延时猜测后代是否已被观察。
const runnerSource = String.raw`
import childProcess from "node:child_process";
import { syncBuiltinESMExports } from "node:module";
const originalSpawn = childProcess.spawn;
childProcess.spawn = function (file, args, options) {
  const child = originalSpawn.call(this, file, args, options);
  if (file === "ps" && child.stdout) {
    let stdout = "";
    child.stdout.on("data", (chunk) => { stdout += chunk.toString("utf8"); });
    child.once("exit", (code) => {
      if (code !== 0) return;
      const table = stdout.trim().split("\n").filter(Boolean).map(line => line.trim().split(/\s+/).slice(0, 3).map(Number));
      process.send({ type: "snapshot", pids: table.map(row => row[0]), table });
    });
  }
  return child;
};
syncBuiltinESMExports();
const { moduleUrl, command, args, options } = JSON.parse(process.argv[2]);
const { runDev } = await import(moduleUrl);
process.exitCode = await runDev(command, args, options);
process.disconnect();
`;

async function processTable() {
  const { stdout } = await execFileAsync("ps", ["-A", "-o", "pid=,ppid=,pgid=,stat=,lstart=,args="], {
    timeout: 2_000,
    maxBuffer: 8 * 1024 * 1024,
    env: { ...process.env, LC_ALL: "C" },
  });
  return stdout.trim().split("\n").filter(Boolean).map((line) => {
    const [pid, ppid, pgid, state, ...rest] = line.trim().split(/\s+/);
    return {
      pid: Number(pid), ppid: Number(ppid), pgid: Number(pgid), state,
      started: rest.slice(0, 5).join(" "), command: rest.slice(5).join(" "),
    };
  });
}

async function spawnCase(t, buildCommand) {
  const directory = await mkdtemp(join(tmpdir(), "dev process test-"));
  const fixture = join(directory, "fixture with spaces.mjs");
  const runner = join(directory, "runner.mjs");
  let run;
  t.after(async () => {
    try {
      if (!run) return;
      if (!psBlocked) {
        // 只回收本用例明确记录且命令行仍属于该临时目录的 PID，绝不按进程名或进程组清理。
        const rows = await processTable();
        for (const row of rows.reverse()) {
          if (run.pids.has(row.pid) && row.command.includes(directory) && !row.state.startsWith("Z")) {
            try { process.kill(row.pid, "SIGKILL"); } catch (error) {
              if (error.code !== "ESRCH") throw error;
            }
          }
        }
      }
      if (!run.done) run.child.kill("SIGKILL");
      await run.waitFor(() => run.done, "测试监督器退出", 2_000);
      if (psBlocked) return;
      const deadline = Date.now() + 2_000;
      let remaining;
      do {
        remaining = (await processTable()).filter((row) =>
          run.pids.has(row.pid) && row.command.includes(directory) && !row.state.startsWith("Z"));
        if (!remaining.length) break;
        await delay(20);
      } while (Date.now() < deadline);
      assert.deepEqual(remaining, [], "测试清理不得留下自己创建的进程");
    } finally {
      await rm(directory, { recursive: true, force: true });
    }
  });
  await Promise.all([writeFile(fixture, fixtureSource), writeFile(runner, runnerSource)]);
  const { command, args, env = {}, detached = false } = buildCommand({ directory, fixture, runner });
  const child = spawn(command, args, {
    env: { ...process.env, ...env },
    detached,
    stdio: ["pipe", "pipe", "pipe", "ipc"],
  });
  const changes = new EventEmitter();
  run = { child, directory, events: [], snapshots: [], inspections: [], pids: new Set([child.pid]), stdout: "", stderr: "", done: null };
  let partial = "";
  child.stdout.setEncoding("utf8");
  child.stderr.setEncoding("utf8");
  child.stdout.on("data", (text) => {
    run.stdout += text;
    partial += text;
    const lines = partial.split("\n");
    partial = lines.pop();
    for (const line of lines) {
      if (!line.startsWith(prefix)) continue;
      const event = JSON.parse(line.slice(prefix.length));
      run.events.push(event);
      run.pids.add(event.pid);
      for (const row of event.tree ?? []) run.pids.add(row.pid);
    }
    changes.emit("change");
  });
  child.stderr.on("data", (text) => { run.stderr += text; changes.emit("change"); });
  child.on("message", (message) => {
    if (message.type === "snapshot") {
      run.snapshots.push(message.pids);
      run.inspections.push(message.table);
    }
    changes.emit("change");
  });
  child.on("error", (error) => { run.done = { error }; changes.emit("change"); });
  child.on("exit", (code, signal) => { run.done = { code, signal }; changes.emit("change"); });
  run.waitFor = (predicate, description, timeoutMs = 5_000) => {
    const current = predicate();
    if (current) return Promise.resolve(current);
    return new Promise((resolve, reject) => {
      const finish = (error, value) => {
        clearTimeout(timer);
        changes.off("change", check);
        if (error) reject(error);
        else resolve(value);
      };
      const check = () => {
        const value = predicate();
        if (value) finish(null, value);
        else if (run.done) finish(new Error(`${description}之前进程已退出：${JSON.stringify(run.done)}\n${run.stdout}\n${run.stderr}`));
      };
      const timer = setTimeout(() => finish(new Error(`等待${description}超时\n${run.stdout}\n${run.stderr}`)), timeoutMs);
      changes.on("change", check);
      check();
    });
  };
  return run;
}

async function managed(t, mode, { options = {}, extraArgs = [], env = {}, missing = false, detached = false } = {}) {
  return spawnCase(t, ({ directory, fixture, runner }) => ({
    command: process.execPath,
    args: [runner, JSON.stringify({
      moduleUrl: supervisorUrl,
      command: missing ? join(directory, "不存在的命令") : process.execPath,
      args: missing ? [] : [fixture, "root", mode, ...extraArgs],
      options: { graceMs: 700, forceMs: 700, pollMs: 25, ...options },
    })],
    env,
    detached,
  }));
}

async function observedTree(run) {
  const ready = await run.waitFor(() => run.events.find((event) => event.type === "ready"), "fixture ready");
  await run.waitFor(() => run.snapshots.some((pids) => ready.tree.every((row) => pids.includes(row.pid))), "监督器观察到完整进程树");
  const table = await processTable();
  const root = ready.tree.find((row) => row.role === "root");
  const middle = ready.tree.find((row) => row.role === "middle");
  const grandchild = ready.tree.find((row) => row.role === "grandchild");
  assert.equal(table.find((row) => row.pid === root.pid).pgid, root.pid, "根进程必须独占进程组");
  if (grandchild) {
    assert.equal(table.find((row) => row.pid === middle.pid).ppid, root.pid);
    assert.equal(table.find((row) => row.pid === grandchild.pid).ppid, middle.pid);
    assert.equal(table.find((row) => row.pid === grandchild.pid).pgid, grandchild.pid, "孙进程必须确实 detached");
  }
  return { root, middle, grandchild };
}

async function exited(run, expectedCode) {
  const result = await run.waitFor(() => run.done, "监督器退出");
  assert.deepEqual(result, { code: expectedCode, signal: null }, run.stderr);
}

async function finished(run, expectedCode) {
  await exited(run, expectedCode);
  const alive = (await processTable()).filter((row) =>
    run.pids.has(row.pid) && row.command.includes(run.directory) && !row.state.startsWith("Z"));
  assert.deepEqual(alive, [], "监督器退出前应清理所有已观察到的后代，包括 detached 孙进程");
}

for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"]) {
  test(`${signal} 经监督器转换成一次 TERM，并等待完整优雅退出`, posix, async (t) => {
    const run = await managed(t, "graceful");
    await observedTree(run);
    run.child.kill(signal);
    await finished(run, 0);
    for (const role of ["root", "middle", "grandchild"]) {
      assert.equal(run.events.filter((event) => event.type === "term" && event.role === role).length, 1, `${role} 只能收到一次 TERM`);
    }
    assert.equal(run.events.filter((event) => event.type === "unexpected-signal").length, 0);
    assert.equal((run.stderr.match(/stopping development processes/g) ?? []).length, 1);
    assert.doesNotMatch(run.stderr, /forcing|cleanup failed/);
  });
}

test("终端进程组 SIGINT 不会中断独立进程组中的 ps 检查", posix, async (t) => {
  const run = await managed(t, "graceful", { detached: true });
  const { root } = await observedTree(run);
  const supervisor = (await processTable()).find((row) => row.pid === run.child.pid);
  assert.equal(supervisor.pgid, run.child.pid, "仅向本测试创建的独立进程组发送信号");
  const inspections = run.inspections.flat().filter(([pid, ppid]) => ppid === run.child.pid && pid !== root.pid);
  assert.ok(inspections.length > 0, "必须实际观察到监督器运行的 ps");
  for (const [pid, , pgid] of inspections) assert.equal(pgid, pid, "ps 必须脱离监督器的终端进程组");
  process.kill(-run.child.pid, "SIGINT");
  await finished(run, 0);
  assert.equal(run.events.filter((event) => event.type === "term" && event.role === "root").length, 1);
  assert.doesNotMatch(run.stderr, /forcing|cleanup failed/);
});

test("挂起根进程与 detached 孙进程在宽限期后被强制清理", posix, async (t) => {
  const graceMs = 600;
  const run = await managed(t, "hang", { options: { graceMs } });
  await observedTree(run);
  const started = performance.now();
  run.child.kill("SIGINT");
  await finished(run, 0);
  assert.ok(performance.now() - started >= graceMs - 75, "第一次信号不能跳过宽限期");
  assert.equal(run.events.filter((event) => event.type === "term" && event.role === "root").length, 1);
  assert.match(run.stderr, /forcing remaining development processes/);
  assert.doesNotMatch(run.stderr, /cleanup failed/);
});

test("第二次终止信号缩短宽限期且不重复发送 TERM", posix, async (t) => {
  const graceMs = 1_000;
  const run = await managed(t, "hang", { options: { graceMs } });
  await observedTree(run);
  run.child.kill("SIGINT");
  await run.waitFor(() => run.events.find((event) => event.type === "term" && event.role === "root"), "第一次 TERM");
  const started = performance.now();
  run.child.kill("SIGHUP");
  await run.waitFor(() => run.stderr.includes("forcing remaining development processes"), "第二次信号触发强制清理");
  assert.ok(performance.now() - started < graceMs * 0.75, "第二次信号不应继续等待完整宽限期");
  await finished(run, 0);
  assert.equal(run.events.filter((event) => event.type === "term" && event.role === "root").length, 1);
  assert.equal((run.stderr.match(/stopping development processes/g) ?? []).length, 1);
});

for (const code of [17, 0]) {
  test(`根进程主动退出 ${code} 后保留退出码并清理已观察 detached 后代`, posix, async (t) => {
    const run = await managed(t, "orphan");
    await observedTree(run);
    run.child.stdin.write(`EXIT:${code}\n`);
    await finished(run, code);
    assert.equal(run.events.filter((event) => event.type === "term" && event.role === "root").length, 0);
    for (const role of ["middle", "grandchild"]) {
      assert.equal(run.events.filter((event) => event.type === "term" && event.role === role).length, 1);
    }
    assert.doesNotMatch(run.stderr, /forcing|cleanup failed/);
  });
}

test("根进程意外被 SIGKILL 时保留 137 并清理 detached 后代", posix, async (t) => {
  const run = await managed(t, "orphan");
  const { root } = await observedTree(run);
  process.kill(root.pid, "SIGKILL");
  await finished(run, 137);
  assert.equal(run.events.filter((event) => event.type === "term" && event.role === "grandchild").length, 1);
});

test("spawn 失败报告错误并退出 1，不遗留监督器", posix, async (t) => {
  const run = await managed(t, "stdio", { missing: true });
  await finished(run, 1);
  assert.match(run.stderr, /launch failed.*ENOENT/);
});

test("参数空格、空参数、环境变量与 stdin/stdout/stderr 原样继承", posix, async (t) => {
  const extraArgs = ["含 空格 的参数", "", "'引号保持原样'", "--literal=a b", "$(不可执行)"];
  const value = "环境 value 带空格";
  const run = await managed(t, "stdio", { extraArgs, env: { DEV_PROCESS_TEST_VALUE: value } });
  await observedTree(run);
  run.child.stdin.write("继承 stdin 的输入\n");
  await finished(run, 0);
  const echoed = run.events.find((event) => event.type === "echo");
  assert.deepEqual(echoed.args, extraArgs);
  assert.equal(echoed.env, value);
  assert.equal(echoed.line, "继承 stdin 的输入");
  assert.match(run.stderr, /fixture inherited stderr/);
});

test("直接 CLI 使用真实命令参数并继承 stdio", posix, async (t) => {
  const run = await spawnCase(t, ({ fixture }) => ({
    command: process.execPath,
    args: [supervisorPath, process.execPath, fixture, "root", "stdio", "CLI argument with spaces"],
  }));
  await run.waitFor(() => run.events.find((event) => event.type === "ready"), "CLI fixture ready");
  run.child.stdin.write("CLI stdin\n");
  await finished(run, 0);
  assert.deepEqual(run.events.find((event) => event.type === "echo").args, ["CLI argument with spaces"]);
  assert.match(run.stderr, /fixture inherited stderr/);
});

test("CLI 缺少命令时退出 1", async (t) => {
  const run = await spawnCase(t, () => ({ command: process.execPath, args: [supervisorPath] }));
  await exited(run, 1);
  assert.match(run.stderr, /development command is required/);
});

for (const [option, code, output] of [["--help", 0, /Usage:/], ["--not-a-valid-option", 2, /unknown option/]]) {
  // Option parsing happens before the supervisor is entered, so this must work
  // even where the process table is unreadable.
  test(`run-dev.sh ${option} 在进入监督器前就返回 ${code}`, async (t) => {
    const run = await spawnCase(t, () => ({ command: "bash", args: [shellPath, option] }));
    await exited(run, code);
    assert.match(run.stdout + run.stderr, output);
    assert.doesNotMatch(run.stderr, /stopping development processes|cannot inspect processes/);
  });
}

test("run-dev.sh 无参数时仍进入监督器", { skip: process.platform === "win32" ? "POSIX only" : false }, async (t) => {
  // macOS /bin/bash 3.2 treats `"${arr[@]}"` of an *empty* array as unbound
  // under `set -u`, so a bare `pnpm dev` died on the re-exec line before
  // anything started. Linux shells expand it silently, hence the guard here.
  const bin = await mkdtemp(join(tmpdir(), "dev shell path-"));
  t.after(() => rm(bin, { recursive: true, force: true }));
  // A trimmed PATH keeps this from reaching a real build: pnpm is absent, so
  // the supervised shell exits right after argument parsing.
  await Promise.all([
    symlink(process.execPath, join(bin, "node")),
    symlink("/bin/bash", join(bin, "bash")),
    symlink("/usr/bin/dirname", join(bin, "dirname")),
    // Startup inspection must pass even on hosts that deny the real `ps`.
    writeFile(join(bin, "ps"), "#!/bin/sh\nexit 0\n", { mode: 0o755 }),
  ]);
  const run = await spawnCase(t, () => ({ command: "bash", args: [shellPath], env: { PATH: bin } }));
  await exited(run, 1);
  assert.doesNotMatch(run.stderr, /unbound variable|parameter not set/, "空参数数组必须安全展开");
  assert.match(run.stderr, /stopping development processes/, "无参数时也必须交给监督器");
  assert.match(run.stderr, /pnpm not found/);
});

test("trackTree 跟踪乱序多层后代、进程组孤儿并保留已观察 detached 孤儿", () => {
  const row = (pid, ppid, pgid, started = `start-${pid}`, state = "S") => ({ pid, ppid, pgid, started, state });
  const previous = new Map([[40, "start-40"], [60, "old-60"], [70, "start-70"], [80, "start-80"]]);
  const table = [
    row(31, 30, 31),
    row(30, 20, 30),
    row(20, 10, 10),
    row(10, 1, 10),
    row(40, 1, 40),
    row(41, 40, 41),
    row(50, 1, 10),
    row(60, 1, 60, "reused-60"),
    row(70, 1, 70, "start-70", "Z+"),
    row(90, 1, 90),
    row(91, 70, 91),
    row(92, 10, 10, "start-92", "Z"),
  ];
  const tracked = trackTree(table, 10, previous);
  assert.deepEqual([...tracked.keys()].sort((a, b) => a - b), [10, 20, 30, 31, 40, 41, 50]);
  assert.equal(tracked.get(40), "start-40");
  assert.deepEqual([...previous], [[40, "start-40"], [60, "old-60"], [70, "start-70"], [80, "start-80"]], "不得修改上一轮快照");
});

test("trackTree 在 root 消失后继续保留孤儿，且在其死亡或 PID 复用后移除", () => {
  const orphan = { pid: 42, ppid: 1, pgid: 42, state: "S", started: "original" };
  const previous = new Map([[10, "root"], [42, "original"]]);
  const retained = trackTree([orphan], 10, previous);
  assert.deepEqual([...retained], [[42, "original"]]);
  assert.equal(trackTree([{ ...orphan, started: "replacement" }], 10, retained).size, 0);
  assert.equal(trackTree([{ ...orphan, state: "Z" }], 10, retained).size, 0);
  assert.equal(trackTree([], 10, retained).size, 0);
});

test("trackTree 拒绝复用的根 PID 及进程组，但继续保留原先 detached 后代", () => {
  const replacementRoot = { pid: 10, ppid: 1, pgid: 10, state: "S", started: "replacement-root" };
  const replacementChild = { pid: 11, ppid: 10, pgid: 10, state: "S", started: "replacement-child" };
  const orphan = { pid: 42, ppid: 1, pgid: 42, state: "S", started: "original-orphan" };
  const previous = new Map([[10, "original-root"], [42, "original-orphan"]]);
  const table = [replacementRoot, replacementChild, orphan];
  assert.deepEqual([...trackTree(table, 10, previous)], [[42, "original-orphan"]]);
  assert.deepEqual([...trackTree(table, 10, new Map([[42, "original-orphan"]]), "original-root")], [[42, "original-orphan"]]);
  assert.deepEqual([...trackTree([replacementChild, orphan], 10, previous, "original-root")], [[42, "original-orphan"]]);
});

test("trackTree 能找回首次快照前退出的根所遗留同组进程，不认领新占用根 PID", () => {
  const orphan = { pid: 11, ppid: 1, pgid: 10, state: "S", started: "original-child" };
  assert.deepEqual([...trackTree([orphan], 10, new Map(), null)], [[11, "original-child"]]);
  const replacementRoot = { pid: 10, ppid: 1, pgid: 10, state: "S", started: "replacement-root" };
  assert.equal(trackTree([replacementRoot, orphan], 10, new Map(), null).size, 0);
});
