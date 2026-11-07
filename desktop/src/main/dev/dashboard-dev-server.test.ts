import assert from "node:assert/strict";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { test } from "node:test";

import {
  dashboardDevOrigin,
  readDashboardDev,
  viteCommand,
  viteLaunch,
  waitForDevServer,
} from "./dashboard-dev-server";

test("开发模式没打开时不启动 Vite", () => {
  assert.equal(readDashboardDev({}), null);
  assert.equal(readDashboardDev({ OCTOP_DASHBOARD_DEV: "0" }), null);
});

test("开发模式要求仪表盘源码目录和合法端口", () => {
  assert.throws(
    () => readDashboardDev({ OCTOP_DASHBOARD_DEV: "1" }),
    /OCTOP_DASHBOARD_SOURCE/,
  );
  assert.deepEqual(
    readDashboardDev({
      OCTOP_DASHBOARD_DEV: "1",
      OCTOP_DASHBOARD_SOURCE: "/repo/dashboard",
    }),
    { sourceDir: "/repo/dashboard", port: 5173 },
  );
  assert.equal(
    readDashboardDev({
      OCTOP_DASHBOARD_DEV: "1",
      OCTOP_DASHBOARD_SOURCE: "/repo/dashboard",
      OCTOP_DASHBOARD_DEV_PORT: "5174",
    })?.port,
    5174,
  );
  assert.throws(
    () =>
      readDashboardDev({
        OCTOP_DASHBOARD_DEV: "1",
        OCTOP_DASHBOARD_SOURCE: "/repo/dashboard",
        OCTOP_DASHBOARD_DEV_PORT: "nope",
      }),
    /OCTOP_DASHBOARD_DEV_PORT/,
  );
});

test("Vite 只监听本机，并把接口代理到 sidecar 端口", () => {
  const launch = viteLaunch({
    sourceDir: "/repo/dashboard",
    port: 5173,
    apiPort: 59999,
    baseEnv: { PATH: "/usr/bin" },
  });
  assert.equal(launch.cwd, "/repo/dashboard");
  assert.deepEqual(launch.args, ["--host", "127.0.0.1", "--port", "5173", "--strictPort"]);
  assert.equal(launch.env.VITE_API_PORT, "59999");
  assert.equal(launch.env.VITE_DEV_PORT, "5173");
  assert.equal(launch.env.VITE_HMR_CLIENT_PORT, "5173");
  assert.equal(launch.env.PATH, "/usr/bin");
  assert.equal(dashboardDevOrigin(5173), "http://127.0.0.1:5173");
  const child = viteCommand(launch);
  if (process.platform === "win32") {
    assert.match(child.command, /cmd\.exe$/i);
    assert.deepEqual(child.args.slice(0, 3), ["/d", "/s", "/c"]);
    assert.equal(child.args[3], launch.command);
    assert.deepEqual(child.args.slice(4), launch.args);
  } else {
    assert.equal(child.command, launch.command);
    assert.deepEqual(child.args, launch.args);
  }
});

test("开发服务器一有响应就继续启动", async () => {
  const server = createServer((_req, res) => {
    res.writeHead(200).end("ok");
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", () => resolve()));
  const address = server.address() as AddressInfo;
  try {
    await waitForDevServer(`http://127.0.0.1:${address.port}`, 2_000);
  } finally {
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});
