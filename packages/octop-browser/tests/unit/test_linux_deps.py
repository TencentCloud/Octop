"""Tests for octop_browser.linux_deps (native Chromium OS libraries)."""

from __future__ import annotations

from octop_browser.linux_deps import (
    build_install_steps,
    detect_package_manager,
    manual_hint,
    with_privileges,
)


def test_detect_package_manager_prefers_dnf(monkeypatch):
    monkeypatch.setattr(
        "octop_browser.linux_deps.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in ("dnf", "yum") else None,
    )
    assert detect_package_manager() == "dnf"


def test_detect_package_manager_none(monkeypatch):
    monkeypatch.setattr("octop_browser.linux_deps.shutil.which", lambda _name: None)
    assert detect_package_manager() is None


def test_with_privileges_noop_when_root(monkeypatch):
    monkeypatch.setattr("octop_browser.linux_deps.sys.platform", "linux")
    monkeypatch.setattr("octop_browser.linux_deps.os.geteuid", lambda: 0)
    assert with_privileges(["dnf", "install", "-y", "atk"]) == [
        "dnf",
        "install",
        "-y",
        "atk",
    ]


def test_with_privileges_prefixes_sudo_n(monkeypatch):
    monkeypatch.setattr("octop_browser.linux_deps.sys.platform", "linux")
    monkeypatch.setattr("octop_browser.linux_deps.os.geteuid", lambda: 1000)
    monkeypatch.setattr(
        "octop_browser.linux_deps.shutil.which",
        lambda name: "/usr/bin/sudo" if name == "sudo" else None,
    )
    assert with_privileges(["dnf", "install", "-y", "atk"]) == [
        "/usr/bin/sudo",
        "-n",
        "--",
        "dnf",
        "install",
        "-y",
        "atk",
    ]


def test_build_steps_skips_playwright_when_dnf(monkeypatch):
    monkeypatch.setattr("octop_browser.linux_deps.sys.platform", "linux")
    monkeypatch.setattr("octop_browser.linux_deps.os.geteuid", lambda: 0)
    monkeypatch.setattr(
        "octop_browser.linux_deps.shutil.which",
        lambda name: "/usr/bin/dnf" if name == "dnf" else None,
    )
    steps = build_install_steps(
        ["python", "-m", "playwright", "install-deps", "chromium"]
    )
    assert [s.label for s in steps] == [
        "dnf",
        "dnf cjk-fonts",
        "dnf cjk-fonts",
        "dnf cjk-fonts",
    ]
    assert steps[0].cmd[:3] == ["dnf", "install", "-y"]
    assert "at-spi2-atk" in steps[0].cmd
    assert "playwright" not in steps[0].cmd
    assert not steps[0].optional
    font_steps = steps[1:]
    assert all(s.optional for s in font_steps)
    # dnf must not rely on --skip-unavailable (unsupported on TencentOS 3 / dnf<4);
    # each CJK font package is installed independently.
    assert all("--skip-unavailable" not in s.cmd for s in font_steps)
    assert "google-noto-sans-cjk-ttc-fonts" in font_steps[0].cmd
    assert "google-noto-cjk-fonts" in font_steps[1].cmd
    assert "wqy-zenhei-fonts" in font_steps[2].cmd


def test_build_steps_apt_tries_playwright_then_native(monkeypatch):
    monkeypatch.setattr("octop_browser.linux_deps.sys.platform", "linux")
    monkeypatch.setattr("octop_browser.linux_deps.os.geteuid", lambda: 0)
    monkeypatch.setattr(
        "octop_browser.linux_deps.shutil.which",
        lambda name: "/usr/bin/apt-get" if name == "apt-get" else None,
    )
    pw = ["python", "-m", "playwright", "install-deps", "chromium"]
    steps = build_install_steps(pw)
    assert [s.label for s in steps] == [
        "playwright install-deps",
        "apt-get",
        "apt-get cjk-fonts",
    ]
    assert steps[0].cmd == pw
    assert steps[1].cmd[:3] == ["env", "DEBIAN_FRONTEND=noninteractive", "apt-get"]
    assert "libatk-bridge2.0-0" in steps[1].cmd
    assert steps[2].optional
    assert "fonts-noto-cjk" in steps[2].cmd


def test_build_steps_unknown_keeps_playwright(monkeypatch):
    monkeypatch.setattr("octop_browser.linux_deps.shutil.which", lambda _name: None)
    pw = ["python", "-m", "playwright", "install-deps", "chromium"]
    steps = build_install_steps(pw)
    assert len(steps) == 1
    assert steps[0].cmd == pw


def test_manual_hint_dnf(monkeypatch):
    monkeypatch.setattr(
        "octop_browser.linux_deps.shutil.which",
        lambda name: "/usr/bin/dnf" if name == "dnf" else None,
    )
    hint = manual_hint()
    assert hint.startswith("Run: sudo dnf install -y")
    assert "at-spi2-atk" in hint or "atk" in hint
    assert "playwright install-deps" not in hint


def test_manual_hint_unknown(monkeypatch):
    monkeypatch.setattr("octop_browser.linux_deps.shutil.which", lambda _name: None)
    assert manual_hint() == "Run: sudo playwright install-deps chromium"


def test_build_steps_yum_tries_font_packages_separately(monkeypatch):
    monkeypatch.setattr("octop_browser.linux_deps.sys.platform", "linux")
    monkeypatch.setattr("octop_browser.linux_deps.os.geteuid", lambda: 0)
    monkeypatch.setattr(
        "octop_browser.linux_deps.shutil.which",
        lambda name: "/usr/bin/yum" if name == "yum" else None,
    )
    steps = build_install_steps(["python", "-m", "playwright", "install-deps"])
    assert steps[0].label == "yum"
    font_steps = [s for s in steps if s.optional]
    assert len(font_steps) >= 2
    assert all(s.label == "yum cjk-fonts" for s in font_steps)
    assert font_steps[0].cmd[-1] == "google-noto-sans-cjk-ttc-fonts"


def test_build_steps_unknown_has_no_font_step(monkeypatch):
    monkeypatch.setattr("octop_browser.linux_deps.shutil.which", lambda _name: None)
    steps = build_install_steps(["python", "-m", "playwright", "install-deps"])
    assert len(steps) == 1
    assert not steps[0].optional
