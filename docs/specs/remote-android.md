# Remote Android — Feature Specification

> **Status:** Implemented (physical adb v1 on `feature/remote-android`; Redroid/emulator install still phased)  
> **Target upstream:** [TencentCloud/Octop](https://github.com/TencentCloud/Octop) → base branch `develop`  
> **Author:** External contributor  
> **Related:** Remote Desktop, Browser AI+, Coze cloud phone (reference UX only)

## 1. Problem

Octop supports **Remote Desktop** (Linux GUI / native OS capture) and **Browser AI+** (Chromium automation), but cannot operate **native mobile apps** (Xiaohongshu, Dianping, Ctrip, etc.). Coze’s cloud phone solves this with a managed Android 13 instance; Octop is self-hosted and must adapt to **Mac Mini, homelab PCs, and VPS** with different hardware.

## 2. Goals

| Goal | Detail |
|------|--------|
| Multi-backend | Physical device (USB/WiFi adb), Redroid (binder VPS), docker-android (KVM VPS) |
| Opt-in install | Same pattern as Remote Desktop — not enabled by default on server |
| Install-time probe | Detect host capability during `scripts/install.sh`; persist to `config.json` |
| Auto-hide | When unsupported, hide dashboard nav **and** do not register backend routes |
| Agent integration | adb-based tools (later phases); handoff for login/captcha |
| Upstream-friendly | Small PRs against `develop`; cross-platform tests (Linux + Windows CI) |

## 3. Non-goals (v1)

- Coze cloud phone API integration (closed SaaS)
- Google Play Store in emulator
- Full 应用宝 automation parity with Coze
- Running on hosts with neither adb path, binder, nor KVM (e.g. Contabo-class VPS)

## 4. Host capability matrix

Probed at **install time** (host capability, not “phone plugged in now”):

| Host | Backend | `capabilities.mobile.enabled` |
|------|---------|--------------------------------|
| macOS / Windows | `physical` | `true` |
| Linux + `binder_linux` | `redroid` | `true` |
| Linux + `/dev/kvm` (no binder) | `emulator` | `true` |
| Linux VPS, no binder/KVM | `none` | `false` |

Priority when multiple apply on Linux: **redroid > emulator** (lighter than full QEMU emulator when binder works).

Runtime readiness (separate from capability):

| State | Meaning |
|-------|---------|
| `needs_device` | Physical backend; no adb device connected |
| `needs_install` | Redroid/emulator backend; container not provisioned |
| `ready` | Stream + control available |

## 5. Config schema

Add to `~/.octop/config.json`:

```json
{
  "capabilities": {
    "mobile": {
      "enabled": true,
      "backend": "physical",
      "probed_at": "2026-08-19T10:00:00Z",
      "reason": ""
    }
  }
}
```

- Env override: `OCTOP_ENABLE_MOBILE=true|false` (admin force)
- Parsed in `octop.config.OctopConfig` as `MobileCapabilities` dataclass
- Missing `capabilities.mobile` on existing installs: probe once on first boot or via `octop mobile probe` (TBD in implementation issue)

## 6. Architecture

```
scripts/install.sh ──► python -m octop.infra.mobile (probe) ──► config.json
                                      │
OctopServer / load_config ◄───────────┘
                                      │
                    ┌─────────────────┴─────────────────┐
                    ▼                                   ▼
         enable_mobile == false              enable_mobile == true
    (no /api/mobile/* routes)          GET /api/settings/capabilities
    (no sidebar nav)                   GET /api/mobile/status
                                       WS  /mobile-stream/ws (phase 4)
                                       POST /api/mobile/install (phase 3)
```

### Module layout (target)

```
src/octop/infra/mobile/
  probe.py           # host capability detection (unit-tested)
  config_probe.py    # merge into config.json
  setup.py           # runtime MobileStatus
  session.py         # phase 4
  capture.py         # phase 4
  input.py           # phase 4
  scripts/linux/v1.0/
    install.sh       # redroid/emulator (phase 3)
    check.sh
    start.sh / stop.sh

src/octop/api/routers/mobile/
  status.py
  install.py         # phase 3
  stream.py          # phase 4

dashboard/src/pages/Control/RemoteAndroid/   # phase 5
```

## 7. API (phased)

### Always available

`GET /api/settings/capabilities`

```json
{
  "mobile": {
    "enabled": true,
    "backend": "physical"
  }
}
```

### When `capabilities.mobile.enabled`

| Method | Path | Phase |
|--------|------|-------|
| GET | `/api/mobile/status` | 2 |
| POST | `/api/mobile/install` | 3 |
| POST | `/api/mobile/uninstall` | 3 |
| WS | `/mobile-stream/ws` | 4 |

When disabled: routes **not registered** (mirror `enable_dashboard` pattern in `api/app.py`).

## 8. Dashboard

- New nav item: **Control → Remote Phone** (`/remote-phone`)
- Permission key: `mobile` (control category, not in `BASELINE_PERMISSIONS`)
- Show nav only if: `user has mobile permission` **AND** `capabilities.mobile.enabled`
- Page states: unsupported (should not appear), needs_install, needs_device, ready

## 9. Install script changes

At end of `scripts/install.sh` / `install.ps1`:

```bash
"$OCTOP_VENV/bin/python" -m octop.infra.mobile "$OCTOP_HOME/config.json"
```

Windows: probe → `backend: physical` only.

## 10. Agent tools (phase 6)

Backend-agnostic adb tools:

- `mobile_screenshot`
- `mobile_tap` / `mobile_swipe`
- `mobile_launch_app`
- `mobile_ui_dump`
- `mobile_handoff_to_user`

## 11. Verification hosts (from probe)

| SSH host | Expected capability |
|----------|---------------------|
| Mac Mini (darwin) | `physical` |
| tencent VPS | `redroid` |
| jdcloud VPS | `emulator` |
| contabo VPS | **hidden** (`enabled: false`) |

## 12. Contribution workflow

Per [CONTRIBUTING.md](../CONTRIBUTING.md):

1. Discuss via upstream feature issue (RFC)
2. Branch from `develop`: `feature/remote-android`
3. One PR per phase (see GitHub Project tasks)
4. `make all` / `make check-all` green; CHANGELOG for user-facing changes
5. PR base: **`develop`**

### Tracking (fork kanban)

Since this is an external contribution, implementation tasks live on the **fork** project board (not upstream):

| Resource | Link |
|----------|------|
| **GitHub Project** | [Octop Remote Android](https://github.com/users/huangcheng/projects/2) |
| **Epic** | [huangcheng/Octop#1](https://github.com/huangcheng/Octop/issues/1) |
| Phase 0 — Upstream RFC | [#2](https://github.com/huangcheng/Octop/issues/2) |
| Phase 1 — Config + probe | [#3](https://github.com/huangcheng/Octop/issues/3) |
| Phase 2 — API + gating | [#4](https://github.com/huangcheng/Octop/issues/4) |
| Phase 3 — Container install | [#5](https://github.com/huangcheng/Octop/issues/5) |
| Phase 4 — WebSocket stream | [#6](https://github.com/huangcheng/Octop/issues/6) |
| Phase 5 — Dashboard | [#7](https://github.com/huangcheng/Octop/issues/7) |
| Phase 6 — Agent tools | [#8](https://github.com/huangcheng/Octop/issues/8) |
| Phase 7 — Physical device | [#9](https://github.com/huangcheng/Octop/issues/9) |
| Phase 8 — i18n, docs, PR | [#10](https://github.com/huangcheng/Octop/issues/10) |

**Shipped in fork PR (physical path):** probe + gated API + WS stream + dashboard `/remote-phone` + agent tools bound to active session. Follow-ups: CJK paste input, Workbench adb shell, container backends.

## 13. Open questions (for maintainers)

1. Accept `capabilities.*` namespace in `config.json` vs flat `enable_mobile`?
2. Probe on every `octop run` if config missing, or install-only?
3. Remote adb (`adb connect host:5555`) for split Octop/Android hosts in v1 or v2?
4. Permission `mobile` default for new users — off (like desktop)?

## 14. References

- Coze cloud device (UX reference): https://docs.coze.cn/cozespace_device
- Redroid: https://github.com/remote-android/redroid-doc
- docker-android: https://github.com/budtmo/docker-android (requires KVM)
- Octop Remote Desktop: `src/octop/infra/desktop/`, `dashboard/src/pages/Control/RemoteDesktop/`
