/** Run through the Browser skill's persistent Node runtime, with its selected tab. */
export async function checkHomeFixture({
  tab,
  viewport,
  fs,
  baseUrl,
  outputDir,
  width,
  height,
  theme = "light",
  language = "zh",
}) {
  await viewport.set({ width, height });
  await tab.goto(`${baseUrl}/dev/workbuddy.html`);
  await tab.playwright
    .getByRole("heading", { name: "Octop，我帮你", exact: true })
    .waitFor({ state: "visible" });
  if (theme === "dark") {
    await tab.playwright
      .getByRole("button", { name: "Dark theme", exact: true })
      .click();
  }
  if (language === "en") {
    await tab.playwright
      .getByRole("button", { name: "English", exact: true })
      .click();
  }
  const input = tab.playwright.getByRole("textbox", {
    name:
      language === "zh"
        ? "和 AI 小助手说点什么吧～"
        : "Say something to your AI Assistant...",
    exact: true,
  });
  // The actual production composer owns this draft; the fixture never sends it.
  await input.fill("Round 2 visual draft");
  const geometry = await tab.playwright.evaluate(() => {
    const rect = (selector) => {
      const node = document.querySelector(selector);
      if (!node) return null;
      const r = node.getBoundingClientRect();
      return { x: r.x, y: r.y, width: r.width, height: r.height };
    };
    return {
      viewport: { width: innerWidth, height: innerHeight },
      overflow: document.documentElement.scrollWidth - innerWidth,
      theme: document.documentElement.dataset.theme,
      primaryCount: document.querySelectorAll(
        ".wb-navigation > a, .wb-navigation > button",
      ).length,
      primaryNavigationCount:
        document.querySelectorAll(".wb-navigation").length,
      assistantPanels: document.querySelectorAll(".wb-assistants").length,
      sidebar: rect(".wb-shell-sidebar"),
      topbar: rect(".workbuddy-topbar"),
      home: rect(".wb-home-page"),
      composer: rect(".wb-composer"),
      recommendations: rect(".wb-home-page__related-playbooks-slot"),
      draft: document.querySelector(".wb-composer__textarea")?.value,
    };
  });
  const check = (condition, description) => {
    if (!condition)
      throw new Error(
        `${width}×${height} ${theme}/${language}: ${description}`,
      );
  };
  check(
    geometry.viewport.width === width && geometry.viewport.height === height,
    "viewport not applied to the selected tab",
  );
  check(geometry.overflow === 0, "horizontal page overflow");
  check(
    geometry.primaryNavigationCount === 1 && geometry.primaryCount === 7,
    "mixed or duplicate primary navigation",
  );
  check(geometry.assistantPanels === 0, "assistant column appears on home");
  check(geometry.theme === theme, "theme mismatch");
  check(
    geometry.draft === "Round 2 visual draft",
    "production composer did not retain its draft",
  );
  check(geometry.composer.width <= width, "composer extends beyond viewport");
  if (width >= 1024) {
    check(
      geometry.sidebar.width === 240,
      "expanded sidebar width differs from source",
    );
    check(
      geometry.topbar.height === 56,
      "desktop topbar height differs from source",
    );
    check(
      geometry.home.width === (width >= 1681 ? 1008 : 848),
      "home width differs from source",
    );
    check(
      geometry.composer.width === (width >= 1681 ? 960 : 800),
      "composer width differs from source",
    );
  }
  const name = `fixture-home-${theme}-${language}-${width}x${height}`;
  await fs.mkdir(outputDir, { recursive: true });
  await fs.writeFile(
    `${outputDir}/${name}.jpg`,
    await tab.screenshot({ fullPage: false }),
  );
  const result = { case: name, status: "passed", ...geometry };
  await fs.writeFile(
    `${outputDir}/${name}.json`,
    `${JSON.stringify(result, null, 2)}\n`,
  );
  return result;
}

/** Fixed market/settings data, with the same header, cards, theme and window as production. */
export async function checkMarketSettingsFixture({
  tab,
  viewport,
  fs,
  baseUrl,
  outputDir,
  width,
  height,
  theme = "light",
  language = "zh",
}) {
  await viewport.set({ width, height });
  await tab.goto(`${baseUrl}/dev/workbuddy.html`);
  await tab.playwright
    .getByRole("heading", { name: "Octop，我帮你", exact: true })
    .waitFor({ state: "visible" });
  if (width < 768)
    await tab.playwright
      .getByRole("button", { name: "展开", exact: true })
      .click();
  await tab.playwright
    .getByRole("button", { name: "专家·技能·连接器", exact: true })
    .click();
  if (width < 768)
    await tab.playwright
      .getByRole("menuitem", { name: "专家", exact: true })
      .click();
  await tab.playwright.getByRole("tab", { name: "专家", exact: true }).click();
  if (theme === "dark")
    await tab.playwright
      .getByRole("button", { name: "Dark theme", exact: true })
      .click();
  if (language === "en")
    await tab.playwright
      .getByRole("button", { name: "English", exact: true })
      .click();
  const labels =
    language === "zh"
      ? ["专家", "技能", "连接器"]
      : ["Experts", "Skills", "Connectors"];
  const ids = ["experts", "skills", "connectors"];
  const results = [];
  const capture = async (surface) => {
    const geometry = await tab.playwright.evaluate(() => {
      const frame = document.querySelector(".wb-settings-center");
      const r = frame?.getBoundingClientRect();
      return {
        viewport: { width: innerWidth, height: innerHeight },
        overflow: document.documentElement.scrollWidth - innerWidth,
        theme: document.documentElement.dataset.theme,
        language: document.documentElement.lang,
        tabs: [...document.querySelectorAll(".um-tab")].map((node) => ({
          height: node.getBoundingClientRect().height,
          font: getComputedStyle(node).fontSize,
          selected: node.getAttribute("aria-selected"),
        })),
        settings: r
          ? {
              width: r.width,
              height: r.height,
              nav: document
                .querySelector(".settings-modal__nav")
                ?.getBoundingClientRect().width,
            }
          : null,
      };
    });
    if (geometry.overflow !== 0 || geometry.theme !== theme)
      throw new Error(`Invalid fixture layout: ${surface}/${width}/${theme}`);
    if (
      surface !== "settings" &&
      (!geometry.tabs.some((tab) => tab.selected === "true") ||
        geometry.tabs.some((tab) => tab.height !== 28 || tab.font !== "14px"))
    )
      throw new Error("Market tab geometry differs from source");
    if (
      surface === "settings" &&
      width >= 1024 &&
      (geometry.settings?.width !== 880 || geometry.settings?.nav !== 200)
    )
      throw new Error("Settings window geometry differs from source");
    const name = `fixture-${surface}-${width}x${height}-${theme}-${language}`;
    await fs.mkdir(outputDir, { recursive: true });
    // The Browser SDK returns JPEG; these are review captures, not lossless pixel goldens.
    await fs.writeFile(
      `${outputDir}/${name}.jpg`,
      await tab.screenshot({ fullPage: false }),
    );
    const result = { name, status: "passed", ...geometry };
    await fs.writeFile(
      `${outputDir}/${name}.json`,
      JSON.stringify(result, null, 2) + "\n",
    );
    results.push(result);
  };
  for (let i = 0; i < ids.length; i++) {
    await tab.playwright
      .getByRole("tab", { name: labels[i], exact: true })
      .click();
    await capture(ids[i]);
  }
  await tab.playwright
    .getByRole("button", { name: "Settings", exact: true })
    .click();
  await tab.playwright
    .getByRole("heading", {
      name: language === "zh" ? "账户" : "Account",
      level: 2,
      exact: true,
    })
    .waitFor({ state: "visible" });
  await tab.playwright
    .locator(
      '[class*="zoom-appear"], [class*="zoom-enter"], [class*="move-up-appear"], [class*="move-up-enter"]',
    )
    .waitFor({ state: "hidden" });
  await capture("settings");
  return results;
}

/** Requires an already authenticated, disposable Octop instance with the test model. */
export async function beginChatQueueAcrossPages({
  tab,
  fs,
  baseUrl,
  outputDir,
  runId,
}) {
  const origin = new URL(baseUrl);
  if (!["127.0.0.1", "localhost"].includes(origin.hostname)) {
    throw new Error(
      "This write test is restricted to a disposable local instance",
    );
  }
  const first = `队列自动验收 ${runId}`;
  const queued = `跨页队列复核 ${runId}`;
  await tab.goto(`${baseUrl}/home`);
  const input = tab.playwright.getByRole("textbox", {
    name: "和 AI 小助手说点什么吧～",
    exact: true,
  });
  await input.fill(first);
  await tab.playwright
    .getByRole("button", { name: "发送", exact: true })
    .click();
  await tab.playwright
    .getByRole("button", { name: "停止", exact: true })
    .waitFor({ state: "visible" });
  await input.fill(queued);
  await tab.playwright
    .getByRole("button", { name: "排队", exact: true })
    .click();
  await tab.playwright
    .getByRole("link", { name: "自动化", exact: true })
    .click();
  await tab.playwright
    .getByRole("heading", { name: "自动化", exact: true })
    .waitFor({ state: "visible" });
  return { runId, first, queued, status: "streaming-in-background" };
}

/** Run after the controlled model has finished, without keeping the chat page mounted. */
export async function checkStoredChatQueue({ tab, fs, outputDir, scenario }) {
  const { runId, first, queued } = scenario;
  await tab.playwright
    .getByRole("button", { name: `${first} 更多`, exact: true })
    .click();
  await tab.playwright
    .getByRole("button", { name: "朗读", exact: true })
    .nth(1)
    .waitFor({ state: "visible", timeoutMs: 45000 });
  await tab.playwright
    .getByRole("button", { name: "停止", exact: true })
    .waitFor({ state: "hidden" });
  await tab.reload();
  await tab.playwright
    .getByRole("button", { name: "朗读", exact: true })
    .nth(1)
    .waitFor({ state: "visible" });
  const snapshot = await tab.playwright.domSnapshot();
  if (!snapshot.includes(first) || !snapshot.includes(queued)) {
    throw new Error("Queued messages were lost after page change or refresh");
  }
  const paragraphs = await tab.playwright.locator("main p").allTextContents({});
  const replies = paragraphs.filter(
    (text) => text === "这是隔离实例中的聊天验收固定模型回复。",
  ).length;
  if (replies !== 2)
    throw new Error(`Expected two stored replies, received ${replies}`);
  await fs.mkdir(outputDir, { recursive: true });
  await fs.writeFile(
    `${outputDir}/real-queue-${runId}.jpg`,
    await tab.screenshot({ fullPage: false }),
  );
  const result = {
    status: "passed",
    scenario: "queue across route changes and refresh",
    runId,
    storedMessages: 2,
    storedReplies: replies,
  };
  await fs.writeFile(
    `${outputDir}/real-queue-${runId}.json`,
    `${JSON.stringify(result, null, 2)}\n`,
  );
  return result;
}
