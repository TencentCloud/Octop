from pathlib import Path

import pytest

from octop_browser.profile import ProfileManager


@pytest.fixture()
def tmp_profiles_dir(tmp_path: Path) -> Path:
    return tmp_path / "profiles"


def test_get_or_create_creates_directory(tmp_profiles_dir: Path) -> None:
    pm = ProfileManager(base_dir=tmp_profiles_dir)
    p = pm.get_or_create("work")
    assert p.name == "work"
    assert p.data_dir.exists()
    assert p.data_dir == tmp_profiles_dir / "work"


def test_get_or_create_is_idempotent(tmp_profiles_dir: Path) -> None:
    pm = ProfileManager(base_dir=tmp_profiles_dir)
    p1 = pm.get_or_create("work")
    p2 = pm.get_or_create("work")
    assert p1.cdp_port == p2.cdp_port


def test_default_profile_gets_port_9222(tmp_profiles_dir: Path) -> None:
    pm = ProfileManager(base_dir=tmp_profiles_dir)
    p = pm.get_or_create("default")
    assert p.cdp_port == 9222


def test_second_profile_gets_incremented_port(tmp_profiles_dir: Path) -> None:
    pm = ProfileManager(base_dir=tmp_profiles_dir)
    pm.get_or_create("default")
    p2 = pm.get_or_create("other")
    assert p2.cdp_port == 9223


def test_port_assignment_survives_new_manager_instance(
    tmp_profiles_dir: Path,
) -> None:
    pm1 = ProfileManager(base_dir=tmp_profiles_dir)
    p1 = pm1.get_or_create("default")

    pm2 = ProfileManager(base_dir=tmp_profiles_dir)
    p2 = pm2.get_or_create("default")

    assert p2.cdp_port == p1.cdp_port


def test_new_manager_does_not_reuse_port_assigned_to_other_profile(
    tmp_profiles_dir: Path,
) -> None:
    pm1 = ProfileManager(base_dir=tmp_profiles_dir)
    task_profile = pm1.get_or_create("task4tabs")

    pm2 = ProfileManager(base_dir=tmp_profiles_dir)
    default_profile = pm2.get_or_create("default")

    assert default_profile.cdp_port != task_profile.cdp_port
    assert default_profile.cdp_port == task_profile.cdp_port + 1


def test_existing_port_mapping_file_is_honored(tmp_profiles_dir: Path) -> None:
    tmp_profiles_dir.mkdir(parents=True)
    (tmp_profiles_dir / ".octop-browser-profiles.json").write_text(
        '{"default": 9333, "work": 9334}', encoding="utf-8"
    )

    pm = ProfileManager(base_dir=tmp_profiles_dir)
    default_profile = pm.get_or_create("default")
    work_profile = pm.get_or_create("work")

    assert default_profile.cdp_port == 9333
    assert work_profile.cdp_port == 9334


def test_corrupt_port_mapping_file_rebuilds_from_start(
    tmp_profiles_dir: Path,
) -> None:
    tmp_profiles_dir.mkdir(parents=True)
    (tmp_profiles_dir / ".octop-browser-profiles.json").write_text(
        "not json", encoding="utf-8"
    )

    pm = ProfileManager(base_dir=tmp_profiles_dir)
    profile = pm.get_or_create("default")

    assert profile.cdp_port == 9222


def test_existing_profile_directory_without_mapping_claims_start_port(
    tmp_profiles_dir: Path,
) -> None:
    (tmp_profiles_dir / "default").mkdir(parents=True)

    pm = ProfileManager(base_dir=tmp_profiles_dir)
    default_profile = pm.get_or_create("default")
    other_profile = pm.get_or_create("other")

    assert default_profile.cdp_port == 9222
    assert other_profile.cdp_port == 9223


def test_list_profiles(tmp_profiles_dir: Path) -> None:
    pm = ProfileManager(base_dir=tmp_profiles_dir)
    pm.get_or_create("a")
    pm.get_or_create("b")
    names = [p.name for p in pm.list_profiles()]
    assert set(names) == {"a", "b"}


def test_delete_profile(tmp_profiles_dir: Path) -> None:
    pm = ProfileManager(base_dir=tmp_profiles_dir)
    profile = pm.get_or_create("temp")
    pm.delete("temp")
    assert not any(p.name == "temp" for p in pm.list_profiles())

    recreated = pm.get_or_create("new")
    assert recreated.cdp_port == profile.cdp_port


def test_delete_nonexistent_profile_is_noop(tmp_profiles_dir: Path) -> None:
    pm = ProfileManager(base_dir=tmp_profiles_dir)
    pm.delete("nonexistent")  # should not raise


# ---------------------------------------------------------------------------
# Sticky target persistence (cross-process attach continuity)
# ---------------------------------------------------------------------------


def test_load_target_returns_none_when_absent(tmp_profiles_dir: Path) -> None:
    pm = ProfileManager(base_dir=tmp_profiles_dir)
    p = pm.get_or_create("work")
    assert p.load_target() is None


def test_save_then_load_target(tmp_profiles_dir: Path) -> None:
    pm = ProfileManager(base_dir=tmp_profiles_dir)
    p = pm.get_or_create("work")
    p.save_target("ABC123")
    assert p.load_target() == "ABC123"


def test_clear_target(tmp_profiles_dir: Path) -> None:
    pm = ProfileManager(base_dir=tmp_profiles_dir)
    p = pm.get_or_create("work")
    p.save_target("ABC123")
    p.clear_target()
    assert p.load_target() is None


def test_clear_target_when_absent_is_noop(tmp_profiles_dir: Path) -> None:
    pm = ProfileManager(base_dir=tmp_profiles_dir)
    p = pm.get_or_create("work")
    p.clear_target()  # should not raise


def test_save_target_ignores_empty_id(tmp_profiles_dir: Path) -> None:
    pm = ProfileManager(base_dir=tmp_profiles_dir)
    p = pm.get_or_create("work")
    p.save_target("")
    assert p.load_target() is None


def test_load_target_handles_corrupt_state(tmp_profiles_dir: Path) -> None:
    pm = ProfileManager(base_dir=tmp_profiles_dir)
    p = pm.get_or_create("work")
    (p.data_dir / ".octop-browser-target.json").write_text("not json", encoding="utf-8")
    assert p.load_target() is None


def test_load_target_handles_wrong_shape(tmp_profiles_dir: Path) -> None:
    pm = ProfileManager(base_dir=tmp_profiles_dir)
    p = pm.get_or_create("work")
    (p.data_dir / ".octop-browser-target.json").write_text(
        '{"target_id": null}', encoding="utf-8"
    )
    assert p.load_target() is None
