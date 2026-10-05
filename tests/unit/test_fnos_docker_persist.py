"""FnOS Docker FPK must persist data on the official data-share (not /var/apps/.../share)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

posix_only = pytest.mark.skipif(os.name != "posix", reason="bash helpers")

REPO = Path(__file__).resolve().parents[2]
COMMON_SH = REPO / "scripts" / "fnos" / "common.sh"
FNOS_DOCKER = REPO / "fnos" / "docker"
FNOS_NATIVE = REPO / "fnos" / "native"
COMPOSE = FNOS_DOCKER / "app" / "docker" / "docker-compose.yaml"
LEGACY_DIR = "/var/apps/octop/share/octop/data"


def _pyproject_version() -> str:
    for line in (REPO / "pyproject.toml").read_text(encoding="utf-8").splitlines():
        if line.startswith("version"):
            return line.split("=", 1)[1].strip().strip('"')
    raise AssertionError("pyproject.toml 没有 version")


@pytest.mark.parametrize("manifest", [FNOS_DOCKER / "manifest", FNOS_NATIVE / "manifest"])
def test_fnos_manifest_maintainer_and_tags(manifest: Path) -> None:
    text = manifest.read_text(encoding="utf-8")
    assert "maintainer=TencentCloud\n" in text
    assert "maintainer=TencentCloud OrcaKit" not in text
    assert "tags=AI,Practical Efficiency" in text


@pytest.mark.parametrize("manifest", [FNOS_DOCKER / "manifest", FNOS_NATIVE / "manifest"])
def test_fnos_manifest_version_matches_pyproject(manifest: Path) -> None:
    text = manifest.read_text(encoding="utf-8")
    assert f"version={_pyproject_version()}\n" in text


def test_publish_skill_bumps_fnos_manifest_versions() -> None:
    text = (REPO / ".cursor" / "skills" / "publish" / "SKILL.md").read_text(encoding="utf-8")
    assert "fnos/docker/manifest" in text
    assert "fnos/native/manifest" in text


def test_fnos_docker_compose_uses_trim_data_share_paths() -> None:
    text = COMPOSE.read_text(encoding="utf-8")
    assert "${TRIM_DATA_SHARE_PATHS}/.octop:/data/.octop" in text
    assert "${TRIM_DATA_SHARE_PATHS}/fnos-boot.sh:/usr/local/bin/fnos-boot.sh:ro" in text
    assert "${TRIM_DATA_SHARE_PATHS}/fnos-admin.env:/data/fnos-admin.env:ro" in text
    assert 'entrypoint: ["bash", "/usr/local/bin/fnos-boot.sh"]' in text
    assert "healthcheck:" in text
    assert "/api/health" in text
    assert "users_loaded" in text
    assert "pull_policy: missing" in text
    assert "pull_policy: always" not in text
    assert "ghcr.io/tencentcloud/octop:latest" not in text
    assert "ghcr.io/tencentcloud/octop:1.0.2b5" in text
    assert "env_file:" not in text
    volume_lines = [
        line
        for line in text.splitlines()
        if line.lstrip().startswith("- ") and ":/data/.octop" in line
    ]
    assert volume_lines, "compose must bind a host path onto /data/.octop"
    assert all(LEGACY_DIR not in line for line in volume_lines)


def test_fnos_docker_callbacks_do_not_hardcode_legacy_data_dir() -> None:
    for rel in (
        "cmd/install_callback",
        "cmd/config_callback",
        "cmd/upgrade_callback",
        "cmd/uninstall_callback",
        "cmd/main",
    ):
        text = (FNOS_DOCKER / rel).read_text(encoding="utf-8")
        assignments = [
            line
            for line in text.splitlines()
            if "DATA_DIR=" in line and LEGACY_DIR in line and not line.lstrip().startswith("#")
        ]
        assert not assignments, f"{rel} still hardcodes the non-persistent share path"


@posix_only
def test_octop_data_share_dir_prefers_trim_env(tmp_path: Path) -> None:
    share = tmp_path / "appshare" / "octop" / "data"
    share.mkdir(parents=True)
    script = f"""
set -euo pipefail
source "{COMMON_SH}"
TRIM_DATA_SHARE_PATHS="{share}:/ignored/other"
export TRIM_DATA_SHARE_PATHS
octop_data_share_dir octop/data
"""
    out = subprocess.check_output(["bash", "-c", script], text=True)
    assert out == str(share)


@posix_only
def test_octop_prepare_docker_persist_migrates_legacy_db(tmp_path: Path) -> None:
    dest = tmp_path / "share"
    dest.mkdir()
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "octop.db").write_text("db", encoding="utf-8")
    (legacy / "config.json").write_text("{}", encoding="utf-8")
    env_file = tmp_path / "docker.env"
    pkgvar = tmp_path / "pkgvar"
    script = f"""
set -euo pipefail
source "{COMMON_SH}"
octop_legacy_docker_data_dir() {{ printf '%s' "{legacy}"; }}
export TRIM_DATA_SHARE_PATHS="{dest}"
export TRIM_PKGVAR="{pkgvar}"
octop_prepare_docker_persist "{env_file}"
"""
    out = subprocess.check_output(["bash", "-c", script], text=True)
    assert out == str(dest)
    assert (dest / ".octop" / "octop.db").read_text(encoding="utf-8") == "db"
    assert (dest / ".octop" / "config.json").read_text(encoding="utf-8") == "{}"
    env_text = env_file.read_text(encoding="utf-8")
    assert f"TRIM_DATA_SHARE_PATHS={dest}" in env_text
    assert f"OCTOP_DATA={dest}" in env_text
    assert (pkgvar / "docker.env").read_text(encoding="utf-8") == env_text


@posix_only
def test_octop_prepare_docker_persist_does_not_overwrite_existing_db(
    tmp_path: Path,
) -> None:
    dest = tmp_path / "share"
    dest_home = dest / ".octop"
    dest_home.mkdir(parents=True)
    (dest_home / "octop.db").write_text("keep", encoding="utf-8")
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "octop.db").write_text("old", encoding="utf-8")
    env_file = tmp_path / "docker.env"
    script = f"""
set -euo pipefail
source "{COMMON_SH}"
octop_legacy_docker_data_dir() {{ printf '%s' "{legacy}"; }}
export TRIM_DATA_SHARE_PATHS="{dest}"
export TRIM_PKGVAR="{tmp_path / "pkgvar"}"
octop_prepare_docker_persist "{env_file}" >/dev/null
"""
    subprocess.check_call(["bash", "-c", script])
    assert (dest_home / "octop.db").read_text(encoding="utf-8") == "keep"


@posix_only
def test_octop_sync_fnos_compose_bakes_absolute_bind(tmp_path: Path) -> None:
    compose = tmp_path / "docker-compose.yaml"
    compose.write_text(
        COMPOSE.read_text(encoding="utf-8").replace(
            "    volumes:\n",
            "    env_file:\n      - .env\n    volumes:\n",
        ),
        encoding="utf-8",
    )
    data_dir = tmp_path / "share"
    env_file = tmp_path / "docker" / ".env"
    env_file.parent.mkdir()
    env_file.write_text(
        "OCTOP_DEFAULT_PASSWORD=WizardPass1\nOCTOP_ADMIN_USERNAME=alice\nOCTOP_PORT=8088\n",
        encoding="utf-8",
    )
    script = f"""
set -euo pipefail
source "{COMMON_SH}"
octop_sync_fnos_compose "{compose}" "{data_dir}" "{env_file}"
"""
    subprocess.check_call(["bash", "-c", script])
    text = compose.read_text(encoding="utf-8")
    assert f"{data_dir}/.octop:/data/.octop" in text
    assert "env_file:" not in text
    assert f"{data_dir}/fnos-boot.sh:/usr/local/bin/fnos-boot.sh:ro" in text
    assert f"{data_dir}/fnos-admin.env:/data/fnos-admin.env:ro" in text
    assert (data_dir / ".octop").is_dir()


@posix_only
def test_octop_write_fnos_bootstrap_script(tmp_path: Path) -> None:
    share = tmp_path / "share"
    script = f"""
set -euo pipefail
source "{COMMON_SH}"
octop_write_fnos_bootstrap "{share}" alice WizardPass1
bash -n "{share}/fnos-boot.sh"
"""
    subprocess.check_call(["bash", "-c", script])
    env_text = (share / "fnos-admin.env").read_text(encoding="utf-8")
    assert "OCTOP_ADMIN_USERNAME=alice" in env_text
    assert "OCTOP_DEFAULT_PASSWORD=WizardPass1" in env_text
    boot = (share / "fnos-boot.sh").read_text(encoding="utf-8")
    assert "octop user passwd" in boot
    assert "octop init" in boot
    assert "set-email" in boot
    assert "初始化失败" in boot
    assert ".fnos-apply-wizard-password" in boot
    assert ".fnos-wizard-password-applied" in boot
    assert "首次升级到不再每次改密" in boot


@posix_only
def test_octop_write_login_file_is_backup_only(tmp_path: Path) -> None:
    script = f"""
set -euo pipefail
source "{COMMON_SH}"
octop_write_login_file "{tmp_path}" alice WizardPass1 8088
"""
    subprocess.check_call(["bash", "-c", script])
    text = (tmp_path / "octop-login.txt").read_text(encoding="utf-8")
    assert "管理员账号：alice" in text
    assert "管理员密码：WizardPass1" in text
    assert "http://<飞牛IP>:8088" in text
    assert "设置」窗口中直接查看" not in text
    assert "应急备份" in text or "不是实时密码本" in text
    assert "不会自动更新" in text


@posix_only
def test_octop_distribute_docker_env_copies_to_compose_dirs(tmp_path: Path) -> None:
    src = tmp_path / "target" / "docker" / ".env"
    src.parent.mkdir(parents=True)
    src.write_text(
        "OCTOP_DEFAULT_PASSWORD=Abcdefg1\nTRIM_DATA_SHARE_PATHS=/data\n", encoding="utf-8"
    )
    runtime = tmp_path / "appcenter" / "octop" / "docker"
    runtime.mkdir(parents=True)
    (runtime / "docker-compose.yaml").write_text(
        COMPOSE.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    script = f"""
set -euo pipefail
source "{COMMON_SH}"
octop_docker_compose_dirs() {{
    printf '%s\\n' "{src.parent}"
    printf '%s\\n' "{runtime}"
}}
octop_distribute_docker_env "{src}" "{tmp_path / "share"}"
"""
    subprocess.check_call(["bash", "-c", script])
    copied = runtime / ".env"
    assert copied.read_text(encoding="utf-8") == src.read_text(encoding="utf-8")
    assert "env_file:" not in (runtime / "docker-compose.yaml").read_text(encoding="utf-8")


@posix_only
def test_octop_restore_docker_env_from_pkgvar(tmp_path: Path) -> None:
    pkgvar = tmp_path / "pkgvar"
    pkgvar.mkdir()
    (pkgvar / "docker.env").write_text("OCTOP_PORT=8088\n", encoding="utf-8")
    env_file = tmp_path / "target" / "docker" / ".env"
    script = f"""
set -euo pipefail
source "{COMMON_SH}"
export TRIM_PKGVAR="{pkgvar}"
octop_restore_docker_env "{env_file}"
"""
    subprocess.check_call(["bash", "-c", script])
    assert env_file.read_text(encoding="utf-8") == "OCTOP_PORT=8088\n"


@posix_only
def test_fnos_docker_scripts_bash_syntax() -> None:
    scripts = [
        COMMON_SH,
        FNOS_DOCKER / "cmd" / "main",
        FNOS_DOCKER / "cmd" / "install_init",
        FNOS_DOCKER / "cmd" / "install_callback",
        FNOS_DOCKER / "cmd" / "config_init",
        FNOS_DOCKER / "cmd" / "config_callback",
        FNOS_DOCKER / "cmd" / "upgrade_callback",
        FNOS_DOCKER / "cmd" / "uninstall_callback",
        FNOS_DOCKER / "cmd" / "uninstall_init",
        REPO / "scripts" / "fnos" / "slim-site-packages.sh",
        FNOS_NATIVE / "cmd" / "main",
        FNOS_NATIVE / "cmd" / "install_init",
        FNOS_NATIVE / "cmd" / "install_callback",
        FNOS_NATIVE / "app" / "bin" / "octop",
    ]
    subprocess.check_call(["bash", "-n", *[str(p) for p in scripts]])


def test_fnos_native_site_packages_has_storage_errors() -> None:
    sp = FNOS_NATIVE / "app" / "site-packages"
    if not (sp / "octop").is_dir():
        return
    assert (sp / "octop_harness" / "backends" / "storage_errors.py").is_file()


def test_fnos_native_start_reports_failure() -> None:
    main = (FNOS_NATIVE / "cmd" / "main").read_text(encoding="utf-8")
    launcher = (FNOS_NATIVE / "app" / "bin" / "octop").read_text(encoding="utf-8")
    install = (FNOS_NATIVE / "cmd" / "install_callback").read_text(encoding="utf-8")
    assert "fail_start" in main
    assert "octop-start-error.txt" in main
    assert "OCTOP_START_WAIT_SECS" in main
    assert "return 0" in main
    assert "--prepare" in launcher
    assert "PREPARE_ONLY" in launcher
    assert '"$LAUNCHER" --prepare' in install or "--prepare" in install


@posix_only
def test_slim_site_packages_drops_driver_and_discovery(tmp_path: Path) -> None:
    sp = tmp_path / "site-packages"
    driver = sp / "playwright" / "driver"
    driver.mkdir(parents=True)
    (driver / "node").write_text("x", encoding="utf-8")
    cache = sp / "googleapiclient" / "discovery_cache"
    cache.mkdir(parents=True)
    (cache / "docs.json").write_text("{}", encoding="utf-8")
    pyc = sp / "pkg" / "__pycache__"
    pyc.mkdir(parents=True)
    (pyc / "a.pyc").write_bytes(b"x")
    (sp / "keep.py").write_text("ok", encoding="utf-8")
    subprocess.check_call(["bash", str(REPO / "scripts/fnos/slim-site-packages.sh"), str(sp)])
    assert not driver.exists()
    assert not cache.exists()
    assert not pyc.exists()
    assert (sp / "keep.py").read_text(encoding="utf-8") == "ok"


def _wizard_fields(path: Path, step: int = 0) -> set[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {item["field"] for item in data[step]["items"] if "field" in item}


def test_fnos_install_wizard_is_account_then_next_steps() -> None:
    required = {
        "wizard_admin_username",
        "wizard_admin_display_name",
        "wizard_admin_email",
        "wizard_admin_password",
        "wizard_admin_password_confirm",
    }
    forbidden = {
        "wizard_password_mode",
        "wizard_log_level",
        "wizard_openai_api_key",
        "wizard_dashscope_api_key",
    }
    for rel, port in (
        ("fnos/docker/wizard/install", "8088"),
        ("fnos/native/wizard/install", "8089"),
    ):
        path = REPO / rel
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data) == 2
        assert data[1]["stepTitle"] == "接下来怎么用"
        assert port in json.dumps(data[1], ensure_ascii=False)
        assert "设置 → 模型" in json.dumps(data[1], ensure_ascii=False)
        assert "不要再走网页" not in json.dumps(data, ensure_ascii=False)
        fields = _wizard_fields(path, 0)
        assert required <= fields
        assert not (fields & forbidden)
        assert not _wizard_fields(path, 1)
        pw_rules = next(
            item["rules"]
            for item in data[0]["items"]
            if item.get("field") == "wizard_admin_password"
        )
        patterns = {rule.get("pattern") for rule in pw_rules if "pattern" in rule}
        assert "^.{8,64}$" in patterns
        assert "[A-Za-z]" in patterns
        assert "[0-9]" in patterns
        confirm = next(
            item
            for item in data[0]["items"]
            if item.get("field") == "wizard_admin_password_confirm"
        )
        assert any(
            rule.get("sameAs") == "wizard_admin_password" for rule in confirm.get("rules", [])
        )
        if rel.startswith("fnos/docker/"):
            assert "ghcr.io" in json.dumps(data[1], ensure_ascii=False)
        else:
            assert "octop-start-error.txt" in json.dumps(data[1], ensure_ascii=False)


def test_fnos_config_wizard_is_password_change_only() -> None:
    required = {"wizard_admin_password", "wizard_admin_password_confirm"}
    forbidden = {
        "wizard_password_mode",
        "wizard_log_level",
        "wizard_openai_api_key",
        "wizard_dashscope_api_key",
    }
    paths = [
        REPO / "fnos/docker/wizard/config",
        REPO / "fnos/native/wizard/config",
        REPO / "fnos/docker/app/wizard/config.template",
        REPO / "fnos/native/app/wizard/config.template",
    ]
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data) == 1
        text = path.read_text(encoding="utf-8")
        assert "octop-current-password" not in text
        assert "octop-current-username" in text
        assert "octop-data-dir" in text
        assert "不会自动更新" in text
        assert "/volX/@appshare" not in text
        fields = _wizard_fields(path, 0)
        assert required <= fields
        assert not (fields & forbidden)


@posix_only
def test_octop_assert_native_arch_rejects_mismatch(tmp_path: Path) -> None:
    marker = tmp_path / "fpk-arch"
    marker.write_text("arm64\n", encoding="utf-8")
    script = f"""
set -euo pipefail
source "{COMMON_SH}"
export OCTOP_FPK_ARCH_FILE="{marker}"
export OCTOP_FPK_HOST_ARCH=amd64
octop_assert_native_arch && exit 10
export OCTOP_FPK_HOST_ARCH=arm64
octop_assert_native_arch || exit 11
unset OCTOP_FPK_ARCH_FILE
octop_assert_native_arch || exit 12
"""
    subprocess.check_call(["bash", "-c", script])


@posix_only
def test_octop_prepend_fnos_node_path_when_missing(tmp_path: Path) -> None:
    bindir = tmp_path / "fnos-node"
    bindir.mkdir()
    node = bindir / "node"
    node.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    node.chmod(0o755)
    empty = tmp_path / "empty"
    empty.mkdir()
    script = f"""
set -euo pipefail
source "{COMMON_SH}"
export PATH="{empty}"
export OCTOP_FNOS_NODE_BIN_DIRS="{bindir}"
octop_prepend_fnos_node_path
found="$(command -v node)"
test "$found" = "{node}"
"""
    subprocess.check_call(["bash", "-c", script])


@posix_only
def test_octop_prepend_fnos_node_path_keeps_existing(tmp_path: Path) -> None:
    existing = tmp_path / "already"
    existing.mkdir()
    node = existing / "node"
    node.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    node.chmod(0o755)
    other = tmp_path / "other"
    other.mkdir()
    other_node = other / "node"
    other_node.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    other_node.chmod(0o755)
    script = f"""
set -euo pipefail
source "{COMMON_SH}"
export PATH="{existing}"
export OCTOP_FNOS_NODE_BIN_DIRS="{other}"
octop_prepend_fnos_node_path
found="$(command -v node)"
test "$found" = "{node}"
"""
    subprocess.check_call(["bash", "-c", script])


@posix_only
def test_octop_validate_install_fields_rejects_mismatch_and_bad_email() -> None:
    script = f"""
set -euo pipefail
source "{COMMON_SH}"
octop_validate_install_fields admin 'GoodPass1' 'GoodPass1' '' '' || exit 10
octop_validate_install_fields admin 'GoodPass1' 'GoodPass2' '' '' && exit 11
octop_validate_install_fields admin 'GoodPass1' 'GoodPass1' 'not-an-email' '' && exit 12
octop_validate_install_fields admin 'GoodPass1' 'GoodPass1' 'a@b.co' 'Ada' || exit 13
"""
    subprocess.check_call(["bash", "-c", script])


def test_fnos_upgrade_wizard_explains_password_kept() -> None:
    for rel in ("fnos/docker/wizard/upgrade", "fnos/native/wizard/upgrade"):
        text = (REPO / rel).read_text(encoding="utf-8")
        data = json.loads(text)
        assert len(data) == 1
        assert "不会改你的登录密码" in text
        assert "文件管理" in text
        assert "不会自动更新" in text
        assert not {item.get("field") for item in data[0]["items"] if "field" in item}


def test_fnos_docker_main_does_not_apply_wizard_password_on_start() -> None:
    text = (FNOS_DOCKER / "cmd" / "main").read_text(encoding="utf-8")
    assert "octop_apply_wizard_password" not in text


@posix_only
def test_octop_render_config_wizard_injects_data_dir(tmp_path: Path) -> None:
    template = tmp_path / "config.template"
    wizard_dir = tmp_path / "wizard"
    wizard_dir.mkdir()
    template.write_text(
        "user=<octop-current-username> dir=<octop-data-dir>\n",
        encoding="utf-8",
    )
    data_dir = tmp_path / "share"
    script = f"""
set -euo pipefail
source "{COMMON_SH}"
octop_render_config_wizard "{template}" "{wizard_dir}" alice Secret1 "{data_dir}"
"""
    subprocess.check_call(["bash", "-c", script])
    text = (wizard_dir / "config").read_text(encoding="utf-8")
    assert "user=alice" in text
    assert f"dir={data_dir}" in text
    assert "<octop-data-dir>" not in text


@posix_only
def test_octop_mark_fnos_passwd_pending(tmp_path: Path) -> None:
    share = tmp_path / "share"
    script = f"""
set -euo pipefail
source "{COMMON_SH}"
octop_mark_fnos_passwd_pending "{share}"
"""
    subprocess.check_call(["bash", "-c", script])
    assert (share / ".octop" / ".fnos-apply-wizard-password").is_file()


@posix_only
def test_octop_validate_optional_password_change() -> None:
    script = f"""
set -euo pipefail
source "{COMMON_SH}"
octop_validate_optional_password_change '' '' || exit 10
octop_validate_optional_password_change 'GoodPass1' '' && exit 11
octop_validate_optional_password_change '' 'GoodPass1' && exit 12
octop_validate_optional_password_change 'GoodPass1' 'GoodPass2' && exit 13
octop_validate_optional_password_change 'GoodPass1' 'GoodPass1' || exit 14
"""
    subprocess.check_call(["bash", "-c", script])
