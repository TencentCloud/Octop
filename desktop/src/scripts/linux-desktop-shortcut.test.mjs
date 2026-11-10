import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { chmodSync, mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = fileURLToPath(new URL(".", import.meta.url));
const buildDir = join(here, "../build");
const libPath = join(buildDir, "linux-desktop-shortcut.sh");
const afterInstallPath = join(buildDir, "linux-after-install.sh");
const afterRemovePath = join(buildDir, "linux-after-remove.sh");
const configPath = join(here, "../electron-builder.config.ts");
const allowedMacros = new Set(["${executable}", "${sanitizedProductName}"]);
const bashOk =
  process.platform !== "win32" && spawnSync("bash", ["-c", "echo ok"], { encoding: "utf8" }).status === 0;

// Git on Windows checks these scripts out as CRLF. The deb hooks stay LF.
function readLf(path) {
  return readFileSync(path, "utf8").replace(/\r\n/g, "\n");
}

test("deb maintainer scripts keep the stock fpm hooks and place a desktop icon", () => {
  const install = readLf(afterInstallPath);
  const remove = readLf(afterRemovePath);
  const library = readLf(libPath);
  const config = readLf(configPath);

  for (const [name, text] of [
    ["after-install", install],
    ["after-remove", remove],
  ]) {
    const macros = text.match(/\$\{[a-zA-Z]+\}/g) ?? [];
    for (const macro of macros) {
      assert.ok(allowedMacros.has(macro), `${name} has unsubstituted macro ${macro}`);
    }
  }
  assert.deepEqual(library.match(/\$\{[a-zA-Z]+\}/g), null);

  assert.match(install, /update-alternatives --install/);
  assert.match(install, /apparmor_parser --replace/);
  assert.match(install, /configure\|\[12\]\)/);
  assert.match(install, /resources\/linux-desktop-shortcut\.sh/);
  assert.match(install, /octop_sync_desktop_shortcut "\/usr\/share\/applications\/\$\{executable\}\.desktop"/);

  assert.match(remove, /update-alternatives --remove/);
  assert.match(remove, /apparmor_parser --remove/);
  assert.match(remove, /remove\|purge\|0\)/);
  assert.doesNotMatch(remove, /upgrade\)/);
  const start = remove.indexOf("# BEGIN linux-desktop-shortcut.sh\n");
  const end = remove.indexOf("# END linux-desktop-shortcut.sh\n");
  assert.ok(start >= 0 && end > start);
  assert.equal(remove.slice(start + "# BEGIN linux-desktop-shortcut.sh\n".length, end), library);
  assert.match(
    remove.slice(end),
    /octop_remove_desktop_shortcut '\$\{executable\}\.desktop'/,
  );

  assert.equal((config.match(/afterInstall:\s*"build\/linux-after-install\.sh"/g) ?? []).length, 2);
  assert.equal((config.match(/afterRemove:\s*"build\/linux-after-remove\.sh"/g) ?? []).length, 2);
  assert.match(config, /from:\s*"build\/linux-desktop-shortcut\.sh"/);
});

function writeExe(dir, name, body) {
  const path = join(dir, name);
  writeFileSync(path, body);
  chmodSync(path, 0o755);
  return path;
}

async function fixture() {
  const root = await mkdtemp(join(tmpdir(), "octop-desktop-shortcut-"));
  const bin = join(root, "bin");
  const homes = join(root, "homes");
  mkdirSync(bin);
  mkdirSync(homes);
  const passwd = join(root, "passwd");
  const gioLog = join(root, "gio.log");
  const entry = join(root, "octop.desktop");
  writeFileSync(gioLog, "");
  writeFileSync(entry, "[Desktop Entry]\nName=Octop\nExec=/usr/bin/octop %U\n");
  writeExe(
    bin,
    "getent",
    `#!/bin/sh
db="\${OCTOP_FAKE_PASSWD:?}"
[ "$1" = "passwd" ] || exit 1
if [ -n "$2" ]; then
  awk -F: -v name="$2" '$1 == name { print; found=1; exit } END { exit !found }' "$db"
  exit
fi
cat "$db"
`,
  );
  writeExe(
    bin,
    "id",
    `#!/bin/sh
mode=""
while [ $# -gt 0 ]; do
  case "$1" in
    -nu) mode=nu; shift ;;
    -u) mode=u; shift ;;
    -gn) mode=gn; shift ;;
    *) break ;;
  esac
done
awk -F: -v mode="$mode" -v key="$1" '
  function finish(v) { print v; found=1; exit }
  mode == "nu" && $3 == key { finish($1) }
  mode == "u" && $1 == key { finish($3) }
  mode == "gn" && $1 == key { finish($1) }
  END { exit found ? 0 : 1 }
' "$OCTOP_FAKE_PASSWD"
`,
  );
  writeExe(
    bin,
    "runuser",
    `#!/bin/sh
user=""
while [ $# -gt 0 ]; do
  case "$1" in
    -u) user="$2"; shift 2 ;;
    --) shift; break ;;
    *) break ;;
  esac
done
if [ -n "$user" ]; then
  HOME="$(getent passwd "$user" | awk -F: '{ print $6; exit }')"
  export HOME
fi
exec "$@"
`,
  );
  writeExe(
    bin,
    "logname",
    `#!/bin/sh
if [ -n "$OCTOP_FAKE_LOGNAME" ]; then
  printf '%s\\n' "$OCTOP_FAKE_LOGNAME"
  exit 0
fi
exit 1
`,
  );
  writeExe(
    bin,
    "gio",
    `#!/bin/sh
printf '%s\\n' "$*" >> "$OCTOP_FAKE_GIO_LOG"
exit 0
`,
  );
  return {
    root,
    bin,
    homes,
    passwd,
    gioLog,
    entry,
    async cleanup() {
      await rm(root, { recursive: true, force: true });
    },
  };
}

function account(home, name, uid) {
  return `${name}:x:${uid}:${uid}:${name}:${home}:/bin/bash\n`;
}

function desktopOf(home, leaf = "Desktop") {
  const dir = join(home, leaf);
  mkdirSync(dir, { recursive: true });
  return dir;
}

function run(fx, body, env = {}) {
  execFileSync("bash", ["-c", body], {
    env: {
      PATH: `${fx.bin}:${process.env.PATH}`,
      HOME: fx.root,
      TMPDIR: process.env.TMPDIR ?? "/tmp",
      LANG: "C.UTF-8",
      OCTOP_FAKE_PASSWD: fx.passwd,
      OCTOP_FAKE_GIO_LOG: fx.gioLog,
      OCTOP_SHORTCUT_LIB: libPath,
      OCTOP_ENTRY: fx.entry,
      ...env,
    },
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
}

const place = `
set -eu
. "$OCTOP_SHORTCUT_LIB"
octop_sync_desktop_shortcut "$OCTOP_ENTRY" octop.desktop
`;

const removeIcons = `
set -eu
. "$OCTOP_SHORTCUT_LIB"
octop_remove_desktop_shortcut octop.desktop
`;

test("sudo apt install puts the launcher on that user's desktop", { skip: !bashOk }, async () => {
  const fx = await fixture();
  try {
    const home = join(fx.homes, "alice");
    mkdirSync(home, { recursive: true });
    const desk = desktopOf(home);
    writeFileSync(fx.passwd, account(home, "alice", 1000) + account(join(fx.homes, "bob"), "bob", 1001));
    mkdirSync(join(fx.homes, "bob"), { recursive: true });
    desktopOf(join(fx.homes, "bob"));
    run(fx, place, { SUDO_USER: "alice" });
    const link = join(desk, "octop.desktop");
    assert.equal(readFileSync(link, "utf8"), readFileSync(fx.entry, "utf8"));
    assert.equal(statSync(link).mode & 0o777, 0o755);
    assert.equal(statSync(join(home, ".local/share/octop/desktop-shortcut-created")).isFile(), true);
    assert.equal(readFileSync(fx.gioLog, "utf8").includes(`set ${link} metadata::trusted true`), true);
    assert.equal(
      statSync(join(fx.homes, "bob", "Desktop", "octop.desktop"), { throwIfNoEntry: false }),
      undefined,
    );
  } finally {
    await fx.cleanup();
  }
});

test("a removed icon stays gone, and an icon that remains is refreshed", { skip: !bashOk }, async () => {
  const fx = await fixture();
  try {
    const home = join(fx.homes, "alice");
    mkdirSync(home, { recursive: true });
    const link = join(desktopOf(home), "octop.desktop");
    writeFileSync(fx.passwd, account(home, "alice", 1000));
    run(fx, place, { SUDO_USER: "alice" });
    await rm(link);
    run(fx, place, { SUDO_USER: "alice" });
    assert.equal(statSync(link, { throwIfNoEntry: false }), undefined);

    writeFileSync(fx.entry, "[Desktop Entry]\nName=Octop\nExec=/usr/bin/octop-new %U\n");
    writeFileSync(link, "stale\n");
    run(fx, place, { SUDO_USER: "alice" });
    assert.equal(readFileSync(link, "utf8"), readFileSync(fx.entry, "utf8"));
  } finally {
    await fx.cleanup();
  }
});

test("Chinese desktop dir and xdg-user-dir are honored", { skip: !bashOk }, async () => {
  const fx = await fixture();
  try {
    const home = join(fx.homes, "li");
    mkdirSync(join(home, ".config"), { recursive: true });
    const desk = desktopOf(home, "桌面");
    writeFileSync(join(home, ".config/user-dirs.dirs"), 'XDG_DESKTOP_DIR="$HOME/桌面"\n');
    writeFileSync(fx.passwd, account(home, "li", 1000));
    run(fx, place, { SUDO_USER: "li" });
    assert.equal(statSync(join(desk, "octop.desktop")).isFile(), true);

    const custom = join(home, "DeskCustom");
    mkdirSync(custom);
    writeExe(
      fx.bin,
      "xdg-user-dir",
      `#!/bin/sh
[ "$1" = "DESKTOP" ] || exit 1
printf '%s\\n' "$OCTOP_FAKE_XDG_DESKTOP"
`,
    );
    await rm(join(home, ".local/share/octop/desktop-shortcut-created"));
    await rm(join(desk, "octop.desktop"));
    run(fx, place, { SUDO_USER: "li", OCTOP_FAKE_XDG_DESKTOP: custom });
    assert.equal(statSync(join(custom, "octop.desktop")).isFile(), true);
  } finally {
    await fx.cleanup();
  }
});

test("root install without sudo user covers ordinary accounts only", { skip: !bashOk }, async () => {
  const fx = await fixture();
  try {
    const alice = join(fx.homes, "alice");
    const bob = join(fx.homes, "bob");
    const svc = join(fx.homes, "svc");
    for (const home of [alice, bob, svc]) {
      mkdirSync(home, { recursive: true });
      desktopOf(home);
    }
    writeFileSync(
      fx.passwd,
      account(alice, "alice", 1000) + account(bob, "bob", 1001) + account(svc, "svc", 999),
    );
    run(fx, place, { SUDO_USER: "root", PKEXEC_UID: "", OCTOP_FAKE_LOGNAME: "" });
    assert.equal(statSync(join(alice, "Desktop/octop.desktop")).isFile(), true);
    assert.equal(statSync(join(bob, "Desktop/octop.desktop")).isFile(), true);
    assert.equal(statSync(join(svc, "Desktop/octop.desktop"), { throwIfNoEntry: false }), undefined);
  } finally {
    await fx.cleanup();
  }
});

test("pkexec uid and logname select one account", { skip: !bashOk }, async () => {
  const fx = await fixture();
  try {
    const alice = join(fx.homes, "alice");
    const bob = join(fx.homes, "bob");
    mkdirSync(alice, { recursive: true });
    mkdirSync(bob, { recursive: true });
    desktopOf(alice);
    desktopOf(bob);
    writeFileSync(fx.passwd, account(alice, "alice", 1000) + account(bob, "bob", 1001));
    run(fx, place, { PKEXEC_UID: "1000" });
    assert.equal(statSync(join(alice, "Desktop/octop.desktop")).isFile(), true);
    assert.equal(statSync(join(bob, "Desktop/octop.desktop"), { throwIfNoEntry: false }), undefined);

    await rm(join(alice, "Desktop/octop.desktop"));
    await rm(join(alice, ".local/share/octop/desktop-shortcut-created"));
    run(fx, place, { OCTOP_FAKE_LOGNAME: "bob" });
    assert.equal(statSync(join(bob, "Desktop/octop.desktop")).isFile(), true);
    assert.equal(statSync(join(alice, "Desktop/octop.desktop"), { throwIfNoEntry: false }), undefined);
  } finally {
    await fx.cleanup();
  }
});

test("uninstall removes the icon and the stamp, not a same-named directory", { skip: !bashOk }, async () => {
  const fx = await fixture();
  try {
    const alice = join(fx.homes, "alice");
    const bob = join(fx.homes, "bob");
    mkdirSync(alice, { recursive: true });
    mkdirSync(bob, { recursive: true });
    const aliceDesk = desktopOf(alice);
    const bobDesk = desktopOf(bob);
    writeFileSync(fx.passwd, account(alice, "alice", 1000) + account(bob, "bob", 1001));
    run(fx, place, { SUDO_USER: "root" });
    writeFileSync(join(aliceDesk, "notes.txt"), "keep\n");
    const planted = join(bob, "桌面");
    mkdirSync(planted);
    writeFileSync(join(planted, "octop.desktop"), "also\n");
    const blocked = join(aliceDesk, "octop.desktop");
    await rm(blocked);
    mkdirSync(blocked);
    writeFileSync(join(blocked, "inside.txt"), "dir\n");
    run(fx, removeIcons, { SUDO_USER: "root" });
    assert.equal(statSync(join(bobDesk, "octop.desktop"), { throwIfNoEntry: false }), undefined);
    assert.equal(statSync(join(planted, "octop.desktop"), { throwIfNoEntry: false }), undefined);
    assert.equal(readFileSync(join(aliceDesk, "notes.txt"), "utf8"), "keep\n");
    assert.equal(readFileSync(join(blocked, "inside.txt"), "utf8"), "dir\n");
    assert.equal(
      statSync(join(alice, ".local/share/octop/desktop-shortcut-created"), { throwIfNoEntry: false }),
      undefined,
    );
    assert.equal(
      statSync(join(bob, ".local/share/octop/desktop-shortcut-created"), { throwIfNoEntry: false }),
      undefined,
    );
  } finally {
    await fx.cleanup();
  }
});
