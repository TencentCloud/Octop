"""A folder cannot be renamed to a path component like "." or ".."."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from octop.infra.knowledge.service import KnowledgeService

DOCUMENT = SimpleNamespace(path="notes", kb_id="kb", id="doc")


class _Repo:
    def __init__(self):
        self.renames: list[tuple[str, str, str]] = []

    def get_document(self, doc_id):
        return DOCUMENT if doc_id == "doc" else None

    def get_document_by_path(self, kb_id, path):
        return None

    def rename_document(self, kb_id, doc_id, name):
        self.renames.append((kb_id, doc_id, name))
        return SimpleNamespace(path=name)


def _service():
    repo = _Repo()
    services = SimpleNamespace(knowledge_repo=repo)
    service = KnowledgeService(services)
    service.get_writable_base = lambda *a, **k: None
    return service, repo


@pytest.mark.parametrize("name", [".", " . ", "..", " .. "])
def test_path_components_are_rejected_before_any_update(name):
    service, repo = _service()

    with pytest.raises(ValueError):
        service.rename_document("kb", "doc", new_name=name, actor_user_id=1)

    # The rename must be refused before the repository rewrites descendant paths.
    assert repo.renames == []


def test_a_real_hidden_name_is_still_allowed():
    service, repo = _service()

    service.rename_document("kb", "doc", new_name=".notes", actor_user_id=1)

    assert repo.renames == [("kb", "doc", ".notes")]
