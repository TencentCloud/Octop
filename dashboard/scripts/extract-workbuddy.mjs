import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";
import postcss from "postcss";
import prettier from "prettier";
import ts from "typescript";

// Extraction only: no recovered JavaScript is evaluated or shipped.
const dashboard = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const source = path.resolve(
  process.argv[2] ??
    path.join(dashboard, "../../WorkBuddy-Analysis/recovered/app"),
);
const assets = path.join(source, "renderer/assets");
const out = path.join(dashboard, "src/workbuddy/generated");
const publicOut = path.join(dashboard, "public/workbuddy");
const docs = path.join(dashboard, "../docs/workbuddy-migration");
const version = JSON.parse(
  fs.readFileSync(path.join(source, "package.json"), "utf8"),
).version;
if (version !== "5.5.6")
  throw new Error(`Expected WorkBuddy 5.5.6, found ${version}`);
for (const p of [out, publicOut, docs]) fs.mkdirSync(p, { recursive: true });
const hash = (data) => crypto.createHash("sha256").update(data).digest("hex");
function listFiles(dir, prefix = "") {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const relative = path.posix.join(prefix, entry.name);
    return entry.isDirectory()
      ? listFiles(path.join(dir, entry.name), relative)
      : [relative];
  });
}
const names = listFiles(assets).sort();
const inventory = [];
const modules = [];
const cssModules = {};
const chatCssSources = new Set([
  "../packages/cb-chat-ui/src/components/message-timeline.module.scss",
  "../packages/cb-chat-ui/src/components/message-timeline/user-bubble.module.scss",
  "../packages/cb-chat-ui/src/components/message-actions/message-actions.module.scss",
]);
for (const name of names) {
  const data = fs.readFileSync(path.join(assets, name));
  inventory.push({ file: name, bytes: data.length, sha256: hash(data) });
  if (!name.endsWith(".js")) continue;
  const text = data.toString();
  const regions = [...text.matchAll(/^\/\/#region (.+)$/gm)];
  let cursor = 0;
  let line = 1;
  for (const region of regions) {
    for (; cursor < region.index; cursor++) if (text[cursor] === "\n") line++;
    const original = region[1].replace(/^\.\.\//g, "");
    if (
      !original.includes("packages/agent-ui/") &&
      !chatCssSources.has(original)
    )
      continue;
    modules.push({ original, bundle: name, line });
    if (!original.endsWith(".module.scss")) continue;
    const end = text.indexOf("//#endregion", region.index);
    const body = text.slice(region.index, end);
    const mapping = {};
    for (const pair of body.matchAll(
      /([\w$]+)\s*(?:=|:)\s*["'](_[^"']+)["']/g,
    )) {
      mapping[pair[1].replace(/\$\d+$/, "")] = pair[2];
    }
    if (Object.keys(mapping).length) cssModules[original] = mapping;
  }
}

const sourceFingerprint = hash(JSON.stringify(inventory));
const manifestFile = path.join(docs, "source-manifest.json");
if (fs.existsSync(manifestFile)) {
  const previous = JSON.parse(fs.readFileSync(manifestFile, "utf8"));
  if (
    previous.sourceFingerprint &&
    previous.sourceFingerprint !== sourceFingerprint
  )
    throw new Error(
      "Frozen 5.5.6 source assets changed; review the baseline before regenerating",
    );
}

const groups = {
  automation: {
    files: ["automation-DeNQ8Czg.css"],
    prefixes: [
      "atm-task",
      "atm-row",
      "atm-records-group-chevron",
      "atm-toolbar",
      "atm-empty",
      "automation-workspace__name-button",
    ],
  },
  shell: {
    files: [
      "lib-chat-ui-BAr_UrVe.css",
      "ui-docs-viewer-CXp0RDLt.css",
      "claw-DTILIPXp.css",
    ],
    prefixes: [
      "workbuddy-topbar",
      "claw-workspace",
      "claw-secondary-sidebar",
      "claw-assistant-list",
      "claw-workspace-title",
      "conversation-sidebar",
      "sidebar-next",
      "cb-sidebar-nav",
      "user-menu",
      "settings-modal",
      "settings-navigation",
      "login-view",
      "welcome-header",
      "wb-home",
      "wb-related-playbooks",
      "wb-scene-tabs",
      "quick-actions",
      "cloud-welcome",
      "claw-welcome",
    ],
  },
  market: {
    files: [
      "ui-docs-viewer-CXp0RDLt.css",
      "skills-BQ1ey5LG.css",
      "skills-market-DTB5imXM.css",
      "skills-panel-CFiZRP16.css",
    ],
    prefixes: [
      "ec-",
      "um-",
      "skills-",
      "skill-card",
      "skill-status",
      "skill-add-btn",
      "skills-market",
      "skill-market",
      "sm-card",
      "sm-grid",
      "sm-status",
      "sm-add-btn",
      "connector-panel",
      "connector-card",
      "connector-grid",
      "connector-connect-btn",
      "plugin-card",
      "cb-plugin-detail",
    ],
  },
  deferred: {
    files: ["collab-Dy8ICrja.css", "space-panel-Da9oqezb.css"],
    prefixes: [
      "project-list",
      "project-grid",
      "project-card",
      "projects-page",
      "templates-grid",
      "create-project",
      "space-panel",
      "workbuddy-collab",
      "landing",
    ],
  },
  chat: {
    files: ["lib-chat-ui-BAr_UrVe.css"],
    prefixes: [
      "cr-input-toolbar",
      "cr-tool-call",
      "cr-code-block",
      "cr-model-selector",
      "cr-markdown",
      "cr-table-block",
      "add-menu",
      "wb-cr-streaming-footer",
      "_chatMessage",
      "_userMessage",
      "_assistantMessage",
      "_messageActions",
      "_actionButton",
      "_container_pf",
      "_mainArea_pf",
    ],
  },
};
const copied = new Set();
// Explicit JSX image dependencies; copy bytes unchanged and audit against the source hash.
for (const filename of ["landing-hero-B6659kdy.png"]) {
  fs.copyFileSync(path.join(assets, filename), path.join(publicOut, filename));
  copied.add(filename);
}
const generated = [];
// Read only the three original scene SVG definitions, without evaluating JS.
const iconBundle = "ui-docs-viewer-CiEFzU38.js";
const iconText = fs.readFileSync(path.join(assets, iconBundle), "utf8");
const iconStart = iconText.indexOf("var init_ModeIcons =");
const iconEnd = iconText.indexOf("//#endregion", iconStart);
if (iconStart < 0 || iconEnd < 0)
  throw new Error("Missing 5.5.6 scene icon definitions");
const iconAst = ts.createSourceFile(
  iconBundle,
  iconText.slice(iconStart, iconEnd),
  ts.ScriptTarget.Latest,
  true,
  ts.ScriptKind.JS,
);
const iconNames = {
  DocumentIcon: "work",
  CodeIcon: "code",
  PaletteIcon$1: "creative",
};
const sceneIcons = {};
function stringProps(object) {
  return Object.fromEntries(
    object.properties
      .filter(
        (p) => ts.isPropertyAssignment(p) && ts.isStringLiteral(p.initializer),
      )
      .map((p) => [
        p.name.getText(iconAst).replace(/["']/g, ""),
        p.initializer.text,
      ]),
  );
}
function readIcons(node) {
  if (
    ts.isBinaryExpression(node) &&
    ts.isIdentifier(node.left) &&
    node.left.text in iconNames &&
    ts.isArrowFunction(node.right)
  ) {
    const svg = node.right.body;
    if (
      !ts.isCallExpression(svg) ||
      !ts.isObjectLiteralExpression(svg.arguments[1])
    )
      throw new Error("Unexpected source scene SVG structure");
    const props = svg.arguments[1];
    const child = props.properties.find(
      (p) => p.name?.getText(iconAst) === "children",
    );
    if (
      !child ||
      !ts.isPropertyAssignment(child) ||
      !ts.isCallExpression(child.initializer) ||
      !ts.isObjectLiteralExpression(child.initializer.arguments[1])
    )
      throw new Error("Unexpected source scene SVG path");
    const attributes = stringProps(child.initializer.arguments[1]);
    if (!attributes.d) throw new Error("Missing source scene SVG path");
    sceneIcons[iconNames[node.left.text]] = {
      viewBox: stringProps(props).viewBox,
      path: attributes,
      source: {
        bundle: iconBundle,
        line:
          iconText.slice(0, iconStart).split("\n").length +
          iconAst.getLineAndCharacterOfPosition(node.getStart()).line,
      },
    };
  }
  ts.forEachChild(node, readIcons);
}
readIcons(iconAst);
if (Object.keys(sceneIcons).length !== 3)
  throw new Error("Incomplete source scene icons");
const iconsJson = JSON.stringify(sceneIcons, null, 2) + "\n";
fs.writeFileSync(path.join(out, "scene-icons.json"), iconsJson);
generated.push({
  file: "scene-icons.json",
  bytes: Buffer.byteLength(iconsJson),
  sha256: hash(iconsJson),
  sources: [iconBundle],
});
const scope = ':where(html[data-ui="workbuddy"])';
function copyReferences(css) {
  return css.replace(
    /url\(\s*(["']?)([^)'"\s]+)\1\s*\)/g,
    (whole, quote, ref) => {
      if (/^(data:|https?:|#|\/)/.test(ref)) return whole;
      const basename = path.basename(ref.split(/[?#]/)[0]);
      const file = path.join(assets, basename);
      if (!fs.existsSync(file)) throw new Error(`Missing resource ${ref}`);
      fs.copyFileSync(file, path.join(publicOut, basename));
      copied.add(basename);
      return `url("/workbuddy/${basename}")`;
    },
  );
}
function scopedSelector(selector) {
  return postcss.list
    .comma(selector)
    .map((part) => {
      const s = part.trim();
      const dark =
        /(?:\.dark|\.cb-dark|expert-center-dark|vscode-dark|IDE Night|data-theme=["']?dark)/.test(
          s,
        );
      const light =
        /(?:\.light|\.cb-light|expert-center-light|vscode-light|IDE Day|data-theme=["']?light)/.test(
          s,
        );
      const prefix = dark
        ? ':where(html[data-ui="workbuddy"][data-theme="dark"])'
        : light
        ? ':where(html[data-ui="workbuddy"][data-theme="light"])'
        : scope;
      const cleaned = s
        .replace(/:root(?:\.(?:dark|cb-dark|light|cb-light))?/g, "")
        .replace(/\[data-theme=["']?(?:dark|light)["']?\]/g, "")
        .replace(/\.expert-center-(?:dark|light)(?=\s|$)/g, "")
        .replace(
          /\b(?:html|body)(?:\[data-(?:theme|vscode-theme-name)=[^\]]+\])?/g,
          "",
        )
        .replace(
          /\.(?:vscode-dark|vscode-light|vscode-high-contrast|dark|cb-dark|light|cb-light)(?=\s|$)/g,
          "",
        )
        .trim();
      return cleaned ? `${prefix} ${cleaned}` : prefix;
    })
    .join(",\n");
}
async function extract(name, files, prefixes, tokens = false) {
  const result = postcss.root();
  const animations = new Map();
  const usedAnimations = new Set();
  function visit(node, parent) {
    if (node.type === "rule") {
      const vars = node.nodes.filter(
        (n) => n.type === "decl" && /^(--wb-|--cb-|--cr-|--ec-)/.test(n.prop),
      );
      const tokenRule =
        tokens &&
        vars.length &&
        /(:root|(?:^|,)\s*(?:\[data-theme|html|body|\.(?:expert-center-(?:dark|light)|dark|light|cb-dark|cb-light)))/.test(
          node.selector,
        );
      const matches = prefixes.some((p) => node.selector.includes(`.${p}`));
      if (!tokenRule && !matches) return;
      const clone = node.clone({ selector: scopedSelector(node.selector) });
      if (tokenRule) clone.removeAll().append(vars.map((n) => n.clone()));
      clone.walkComments((n) => n.remove());
      clone.walkDecls((d) => {
        if (/^animation/.test(d.prop))
          for (const word of d.value.split(/[\s,]+/)) usedAnimations.add(word);
      });
      parent.append(clone);
    } else if (node.type === "atrule" && /keyframes$/.test(node.name)) {
      animations.set(node.params, node);
    } else if (node.type === "atrule" && node.nodes) {
      const clone = node.clone().removeAll();
      node.nodes.forEach((n) => visit(n, clone));
      if (clone.nodes.length) parent.append(clone);
    }
  }
  for (const file of files)
    postcss
      .parse(fs.readFileSync(path.join(assets, file), "utf8"))
      .nodes.forEach((n) => visit(n, result));
  for (const [animation, node] of animations)
    if (usedAnimations.has(animation)) result.append(node.clone());
  result.walkComments((n) => n.remove());
  const css = copyReferences(result.toString());
  const filename = `${name}.css`;
  const finalCss = await prettier.format(
    `/* Extracted from WorkBuddy ${version}; regenerate with npm run workbuddy:extract. */\n${css}\n`,
    { parser: "css" },
  );
  fs.writeFileSync(path.join(out, filename), finalCss);
  generated.push({
    file: filename,
    bytes: Buffer.byteLength(finalCss),
    sha256: hash(finalCss),
    sources: files,
  });
}

// Read original unified-market SVGs as literal data; no recovered JavaScript executes.
const marketIcons = {};
for (const [name, id] of [
  ["ExpertIconRaw", "experts"],
  ["SkillToolIconRaw", "skills"],
  ["ConnectorTabIconRaw", "connectors"],
]) {
  const start = iconText.indexOf(`${name} =`);
  const end = iconText.indexOf(`${name}.displayName`, start);
  if (start < 0 || end < 0) throw new Error(`Missing market icon ${name}`);
  const definition = iconText.slice(start, end);
  const literal = (key) =>
    definition.match(new RegExp(`\\b${key}: "([^"\\n]+)"`))?.[1];
  const d = literal("d");
  if (!d) throw new Error(`Missing market SVG path ${name}`);
  marketIcons[id] = {
    viewBox: literal("viewBox"),
    path: {
      d,
      fill: "currentColor",
      fillRule: literal("fillRule"),
      transform: literal("transform"),
    },
    source: {
      bundle: iconBundle,
      line: iconText.slice(0, start).split("\n").length,
    },
  };
}
const marketIconJson = JSON.stringify(marketIcons, null, 2) + "\n";
fs.writeFileSync(path.join(out, "market-icons.json"), marketIconJson);
generated.push({
  file: "market-icons.json",
  bytes: Buffer.byteLength(marketIconJson),
  sha256: hash(marketIconJson),
  sources: [iconBundle],
});

await extract(
  "tokens",
  ["safe-delete-events-Cb4BnJzK.css", "lib-chat-ui-BAr_UrVe.css"],
  [],
  true,
);
for (const [name, group] of Object.entries(groups))
  await extract(name, group.files, group.prefixes);
await extract("market-tokens", ["ui-docs-viewer-CXp0RDLt.css"], [], true);
const moduleMap = JSON.stringify(cssModules, null, 2) + "\n";
fs.writeFileSync(path.join(out, "cssModules.json"), moduleMap);
generated.push({
  file: "cssModules.json",
  bytes: Buffer.byteLength(moduleMap),
  sha256: hash(moduleMap),
  sources: [
    ...new Set(
      modules
        .filter((m) => m.original.endsWith(".module.scss"))
        .map((m) => m.bundle),
    ),
  ],
});
fs.writeFileSync(
  manifestFile,
  JSON.stringify(
    {
      version,
      sourceFingerprint,
      packageSha256: hash(fs.readFileSync(path.join(source, "package.json"))),
      assets: inventory,
      modules,
      generated,
      copied: [...copied],
    },
    null,
    2,
  ) + "\n",
);
console.log(
  JSON.stringify({
    version,
    sourceAssets: inventory.length,
    sourceModules: modules.length,
    cssModules: Object.keys(cssModules).length,
    generated: generated.map(({ file, bytes }) => ({ file, bytes })),
    copied: copied.size,
  }),
);
