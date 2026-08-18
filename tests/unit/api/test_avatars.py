"""Unit tests for avatar storage, preferences refs, and router helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from octop.api.routers.avatars import looks_like_image
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.preferences import (
    get_avatar_reference_from_json,
    merge_avatar_preferences_json,
    normalize_avatar_reference,
)
from octop.infra.utils.paths import PathLayout


class TestLooksLikeImage:
    def test_png_jpeg_webp_gif_signatures(self) -> None:
        assert looks_like_image(b"\x89PNG\r\n\x1a\n" + b"body")
        assert looks_like_image(b"\xff\xd8\xff\xe0" + b"body")
        assert looks_like_image(b"RIFF1234WEBPVP8 " + b"body")
        assert looks_like_image(b"GIF89a" + b"body")

    def test_rejects_non_images(self) -> None:
        assert not looks_like_image(b"hello world")
        assert not looks_like_image(b"")
        assert not looks_like_image(b"<script>alert(1)</script>")


class TestAvatarReferenceNormalization:
    def test_accepts_users_and_agents_refs(self) -> None:
        assert normalize_avatar_reference("users/3") == "users/3"
        assert normalize_avatar_reference("agents/main") == "agents/main"
        assert normalize_avatar_reference("agents/my-writer_02") == "agents/my-writer_02"

    def test_rejects_malformed_refs(self) -> None:
        assert normalize_avatar_reference(None) is None
        assert normalize_avatar_reference("") is None
        assert normalize_avatar_reference("users") is None
        assert normalize_avatar_reference("channels/3") is None
        assert normalize_avatar_reference("../etc/passwd") is None
        assert normalize_avatar_reference("a" * 200) is None


class TestAvatarPreferencesRoundTrip:
    def test_set_and_clear(self) -> None:
        raw = merge_avatar_preferences_json("{}", avatar="users/1")
        assert get_avatar_reference_from_json(raw) == "users/1"
        cleared = merge_avatar_preferences_json(raw, avatar=None)
        assert get_avatar_reference_from_json(cleared) is None

    def test_preserves_other_keys(self) -> None:
        base = '{"preferred_model":"openai/gpt","avatar":"users/2"}'
        raw = merge_avatar_preferences_json(base, avatar="users/9")
        assert get_avatar_reference_from_json(raw) == "users/9"
        assert "preferred_model" in raw

    def test_invalid_ref_rejected(self) -> None:
        with pytest.raises(OctopError) as exc:
            merge_avatar_preferences_json("{}", avatar="bad/ref/shape/")
        assert exc.value.code == ErrorCode.SLASH_BAD_ARGS


class TestPathLayoutAvatarPaths:
    def test_avatar_file_sanitizes_traversal(self) -> None:
        layout = PathLayout(root=Path("/tmp/fake-octop"))
        safe = layout.avatar_file("users", "../../etc/passwd")
        assert safe.parent.parent == layout.avatars_dir
        assert ".." not in safe.name and "/" not in safe.name

    def test_avatar_file_unknown_kind_quarantined(self) -> None:
        layout = PathLayout(root=Path("/tmp/fake-octop"))
        p = layout.avatar_file("channels", "3")
        assert p.parent.name == "_"

    def test_avatar_reference_is_stable(self) -> None:
        layout = PathLayout(root=Path("/tmp/fake-octop"))
        assert layout.avatar_reference("agents", "main") == "agents/main"


class TestRequireAvatarTargetAuthz:
    def _server(self, *, agent_owner: int | None) -> SimpleNamespace:
        agent_row = SimpleNamespace(user_id=agent_owner, config_json="{}")
        return SimpleNamespace(
            services=SimpleNamespace(
                user_repo=SimpleNamespace(
                    get=lambda uid: SimpleNamespace(id=uid) if uid in (1, 2) else None,
                ),
                agent_repo=SimpleNamespace(get=lambda aid: agent_row if aid == "main" else None),
                paths=PathLayout(root=Path("/tmp/fake-octop")),
            ),
        )

    def _user(self, uid: int = 1) -> SimpleNamespace:
        return SimpleNamespace(id=uid)

    def test_other_user_avatar_forbidden(self) -> None:
        from octop.api.routers.avatars import _require_avatar_target

        with pytest.raises(OctopError) as exc:
            _require_avatar_target(
                "users",
                "2",
                user=self._user(1),
                server=self._server(agent_owner=1),
                require_owner=True,
            )
        assert exc.value.code == ErrorCode.FORBIDDEN

    def test_me_alias_maps_to_current_user(self) -> None:
        from octop.api.routers.avatars import _require_avatar_target

        target, layout = _require_avatar_target(
            "users",
            "me",
            user=self._user(1),
            server=self._server(agent_owner=1),
            require_owner=True,
        )
        assert target == layout.avatar_file("users", "1")

    def test_agent_owner_required_for_write(self) -> None:
        from octop.api.routers.avatars import _require_avatar_target

        with pytest.raises(OctopError) as exc:
            _require_avatar_target(
                "agents",
                "main",
                user=self._user(2),
                server=self._server(agent_owner=1),
                require_owner=True,
            )
        assert exc.value.code == ErrorCode.FORBIDDEN

    def test_shared_agent_readable_without_ownership(self) -> None:
        from octop.api.routers.avatars import _require_avatar_target

        target, _ = _require_avatar_target(
            "agents",
            "main",
            user=self._user(2),
            server=self._server(agent_owner=1),
            require_owner=False,
        )
        assert target.name == "main.png"
