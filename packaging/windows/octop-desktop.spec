# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata


block_cipher = None
spec_dir = Path(SPECPATH)
repo_root = spec_dir.parents[1]
src_dir = repo_root / "src"


def safe_collect_submodules(package):
    try:
        return collect_submodules(package)
    except Exception:
        return []


def safe_collect_data_files(package):
    try:
        return collect_data_files(package)
    except Exception:
        return []


def safe_copy_metadata(package):
    try:
        return copy_metadata(package)
    except Exception:
        return []


datas = [
    (str(src_dir / "octop" / "dashboard"), "octop/dashboard"),
    (str(src_dir / "octop" / "i18n"), "octop/i18n"),
    (str(src_dir / "octop" / "infra" / "db" / "migrations"), "octop/infra/db/migrations"),
    (
        str(src_dir / "octop" / "infra" / "agents" / "experts" / "library"),
        "octop/infra/agents/experts/library",
    ),
    (
        str(src_dir / "octop" / "infra" / "agents" / "subagents" / "library"),
        "octop/infra/agents/subagents/library",
    ),
    (str(src_dir / "octop" / "infra" / "desktop" / "scripts"), "octop/infra/desktop/scripts"),
]
datas += safe_collect_data_files("playwright")
datas += safe_collect_data_files("webview")
datas += safe_collect_data_files("harness_agent")
datas += safe_collect_data_files("harness_gateway")
datas += safe_collect_data_files("harness_memory")
datas += safe_collect_data_files("harness_browser")

for dist_name in (
    "octop",
    "fastapi",
    "uvicorn",
    "starlette",
    "pydantic",
    "playwright",
    "pywebview",
    "harness-agent",
    "harness-gateway",
    "harness-memory",
    "harness-browser",
    "orcakit-harness-agent",
):
    datas += safe_copy_metadata(dist_name)

hiddenimports = []
for package_name in (
    "octop",
    "uvicorn",
    "playwright",
    "webview",
    "harness_agent",
    "harness_gateway",
    "harness_memory",
    "harness_browser",
):
    hiddenimports += safe_collect_submodules(package_name)

hiddenimports += [
    "webview.platforms.edgechromium",
    "uvicorn.lifespan.on",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
]

a = Analysis(
    [str(src_dir / "octop" / "desktop_app.py")],
    pathex=[str(src_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Octop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Octop",
)
