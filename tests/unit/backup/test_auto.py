"""Unit tests for automatic backup helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from octop.config import BackupConfig, load_config
from octop.infra.backup.auto import (
    AUTO_BACKUP_JOB_ID,
    apply_auto_backup_schedule,
    backup_config_from_payload,
    persist_backup_config,
    to_auto_backup_filename,
)
from octop.infra.errors import OctopError


def test_to_auto_backup_filename() -> None:
    assert (
        to_auto_backup_filename("octop-backup-20260101T000000Z.tar.gz")
        == "octop-auto-backup-20260101T000000Z.tar.gz"
    )
    assert (
        to_auto_backup_filename("octop-auto-backup-20260101T000000Z.tar.gz")
        == "octop-auto-backup-20260101T000000Z.tar.gz"
    )


def test_backup_config_from_payload_rejects_bad_schedule() -> None:
    with pytest.raises(OctopError):
        backup_config_from_payload({"schedule": "not-a-trigger", "retention_count": 3})


def test_backup_config_from_payload_rejects_bad_retention() -> None:
    with pytest.raises(OctopError):
        backup_config_from_payload({"schedule": "cron:0 4 * * *", "retention_count": 0})


def test_persist_backup_config(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.json"
    load_config(cfg_path)
    out = persist_backup_config(
        cfg_path,
        BackupConfig(auto_enabled=True, schedule="interval:3600", retention_count=3),
    )
    assert out.backup.auto_enabled is True
    assert out.backup.schedule == "interval:3600"
    assert out.backup.retention_count == 3
    reloaded = load_config(cfg_path)
    assert reloaded.backup.auto_enabled is True


def test_apply_auto_backup_schedule_skips_when_disabled(tmp_path: Path) -> None:
    paths = MagicMock()
    paths.config = tmp_path / "config.json"
    load_config(paths.config)

    cron = MagicMock()
    server = MagicMock()
    server.paths = paths

    apply_auto_backup_schedule(cron, server=server)
    cron.unschedule_system_job.assert_called_once_with(AUTO_BACKUP_JOB_ID)
    cron.schedule_system_job.assert_not_called()


def test_apply_auto_backup_schedule_registers_when_enabled(tmp_path: Path) -> None:
    paths = MagicMock()
    paths.config = tmp_path / "config.json"
    load_config(paths.config)
    persist_backup_config(
        paths.config,
        BackupConfig(auto_enabled=True, schedule="cron:0 4 * * *", retention_count=7),
    )

    cron = MagicMock()
    server = MagicMock()
    server.paths = paths

    apply_auto_backup_schedule(cron, server=server)
    cron.unschedule_system_job.assert_called_once_with(AUTO_BACKUP_JOB_ID)
    cron.schedule_system_job.assert_called_once()
    kwargs = cron.schedule_system_job.call_args
    assert kwargs.args[0] == AUTO_BACKUP_JOB_ID
    assert kwargs.kwargs["trigger"] == "cron:0 4 * * *"
