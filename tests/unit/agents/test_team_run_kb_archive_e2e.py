"""`T-71` 第三件 · **A1：归档跳的端到端（unit 层）** —— `kb_document_id` 真的落库。

**三问**
* **关切面** = 经生产代码路径写一个工件 ⇒ `project_artifacts.kb_document_id` **真的被写入**（归档跳真的发生）；
* **一致性** = 与 `run_service.py:1485` 的归档跳守卫同口径（`… and kb_id and user is not None`）+
  `learnings.py:449/451/493/530`：`set_kb_document_id` 是 `kb_document_id` 的**唯一写者**；
* **入口** = **生产服务面**（`TeamRunService.write_artifact`）+ **真 `ProjectKbArchiver`** + **真 KB**（真 DB 行）。

**第四问 · 前置自证**：断言依赖"归档跳真的执行了"这个前置 ⇒ 三档里只有第 ③ 档算数：
| 档 | 写法 | 判定 |
|---|---|---|
| ① | 断言 stub/mock 被调用过 | ❌ 只证明"我的仪器响过"（本 run 两次栽在"仪器报告它自己"） |
| ② | 只断言 `kb_document_id` 非空 | ❌ **可能因为别的原因非空** ⇒ 假绿 |
| ③ | ★ **经真实读口读回前置产物的内容** | ✅ 本文件：`KnowledgeService.list_documents` 读回文档，断言**带着我写入的文本** |

★★ **第③档的读口必须能读到【内容】，不是【元数据】——为什么不是 `list_documents`**：
本用例初版用 `list_documents` 读回，**主判据与反向对照都过了，却卡在自证上** ——
因为 `list_documents` **只返回元数据行**（`id` / `path` / `byte_size` / `status`），**读不出内容**。
★ **元数据是"产物的影子"，内容才是产物本身** ——
元数据只能证明"**有行**"，证明不了"**带着我写入的东西**" ⇒ **影子不算自证**。
⇒ 内容要用 `preview_document(kb_id, document_id, actor_user_id=…)`
（既有 fixture 用的就是这个口，`test_memory_kb_reference_bridge.py:117`）。
★ **反面**：若在这里退一步接受元数据，本文件就会变成一个"**看起来有自证、实际只证明了有行**"的用例 ——
而那正是本 run 反复治的"**仪器报告它自己**"。

**既有口径出处**（来源 `tests/unit/agents/test_memory_kb_reference_bridge.py`）
```
:58-59  settings: knowledge_embedding_backend="onnx" / knowledge_embedding_model="tiny"
:67-69  monkeypatch.setattr("octop.infra.knowledge.service.assert_knowledge_usable", lambda *_a, **_k: None)
:87     documents = L.KnowledgeServiceDocuments(service, actor_user_id=owner_id)
:88-90  archiver  = L.ProjectKbArchiver(documents=documents, artifacts=repo, kb_id=…, artifact_id=…)
```
★ **承载差异（写明，否则"同一口径"只是自我声明）**：
* `:67-69` 的 **patch 目标符号逐字相同、不换层**；
* `:58-59` 在 unit 里就是**真 settings 行**（本文件的 unit 装置带真 `settings_repo`）—— 与 `T-71` integration 尝试里
  的承载一致；★ 而**差别在于本文件用 `assert_knowledge_usable` 的 no-op 短路了能力门**，
  因此**不需要已下载的嵌入模型**（`infra/knowledge/gate.py:71 model_downloaded` / `:85 usable = feature_enabled and prerequisites_ok`）。
★ **判据锚**：本文件断言的是【**归档真的发生**】这件事实，判据锚在**唯一写者写下的那一行落库**上（不是 mock 上）。

★ **删除条件**：当测试环境提供嵌入模型、或 gate 出现可注入 stub 点时，本断言可上移到
`tests/integration/test_team_run_kb_reference_e2e.py` 的集成形态（届时本文件与其集成版并存或合并，由卡主定）。
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from octop.config import OctopConfig
from octop.infra.agents.teams import learnings as L
from octop.infra.agents.teams.run_service import TeamRunService
from octop.infra.agents.teams.service import TeamService
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import build_shared_services
from octop.infra.knowledge.service import KnowledgeService
from octop.infra.utils.paths import PathLayout

TEAM_ID = "ag-kb-team"
MANIFEST = ".octop/manifest.json"
MEMBERS = [(TEAM_ID, "lead"), ("ag-be", "backend"), ("ag-qa", "qa")]
BODY = "# SPEC\n\n## 边界与禁止项\n\n| 边界 | 处置 |\n| --- | --- |\n| 只读 | 不改生产码 |\n"
PROBE_TEXT = "T71-KB-ARCHIVE-PROBE"


class Actor:
    def __init__(self, user_id: int) -> None:
        self.id = user_id
        self.permissions = ["projects", "knowledge_bases"]

    @property
    def is_admin(self) -> bool:
        return False


class FakeWorkspace:
    def __init__(self) -> None:
        self.files: dict[str, str] = {}

    def read_text(self, path: str, *, limit: int = 10_000_000) -> str | None:
        return self.files.get(str(path))

    def write_text(self, path: str, content: str, *, force: bool = False) -> None:
        self.files[str(path)] = content

    def exists(self, path: str) -> bool:
        return str(path) in self.files

    def list_dir(self, path: str = ".") -> list[Any]:
        """**harness 真形状**：`{"path": <workspace-relative>, "is_dir": bool}`。

        消费点在 `run_service.py:439-441`：`isinstance(entry, Mapping)` ⇒ 读 `entry["path"]` /
        `entry["is_dir"]`；harness 的契约是"**Always workspace-relative, never basename-only**"。
        ★ 本替身此前是 `SimpleNamespace(name=…)` —— 那正是 **T-72 那个 bug 的旧形状**；
        `test_present_artifacts_shape.py`（T-79）会把它判红（见 `T60-23`）。
        """
        prefix = "" if str(path) in {"", "."} else str(path).rstrip("/") + "/"
        return [
            {"path": n, "is_dir": False}
            for n in sorted(self.files)
            if n.startswith(prefix) and "/" not in n[len(prefix) :]
        ]


@dataclass
class Harness:
    services: Any
    service: TeamRunService
    workspace: FakeWorkspace
    user: Actor
    kb_service: KnowledgeService
    kb_id: str


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Harness]:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / "home"))
    # 抄 `:67-69`：同一目标符号，打成 no-op（不换层）
    monkeypatch.setattr(
        "octop.infra.knowledge.service.assert_knowledge_usable", lambda *_a, **_k: None
    )
    paths = PathLayout(tmp_path / ".octop")
    paths.ensure_root()
    db = SqlitePool(paths.db)
    run_migrations(db)
    services = build_shared_services(db=db, paths=paths, config=OctopConfig())
    # 抄 `:58-59` 的键值
    services.settings_repo.set("knowledge_embedding_backend", "onnx")
    services.settings_repo.set("knowledge_embedding_model", "tiny")
    uid = services.user_repo.create(username="owner", password_hash="h", role="user")
    services.agent_repo.create(agent_id=TEAM_ID, user_id=uid, name="KB Team", kind="team")
    workspace = FakeWorkspace()
    workspace.write_text(
        MANIFEST,
        json.dumps(
            {
                "members": [{"agent_id": a, "role": r} for a, r in MEMBERS],
                "lead_agent_id": TEAM_ID,
            }
        ),
    )
    service = TeamRunService(
        services=services,
        gateway=None,  # type: ignore[arg-type]
        workspace_for=lambda agent_id: workspace if agent_id == TEAM_ID else None,
        team_service=TeamService(
            services.repos,
            workspace_for=lambda agent_id: workspace if agent_id == TEAM_ID else None,
        ),
    )
    kb_service = KnowledgeService(services)
    kb = kb_service.create_base(owner_user_id=uid, name="T71 KB")
    yield Harness(
        services=services,
        service=service,
        workspace=workspace,
        user=Actor(uid),
        kb_service=kb_service,
        kb_id=str(kb.id),
    )


def _bind_real_archiver(harness: Harness) -> None:
    """真 `ProjectKbArchiver`（唯一写者链路），形状同既有 `_Boom` 工厂。"""

    def factory(kb_id: str, artifact_id: str, *, actor_user_id: int) -> Any:
        documents = L.KnowledgeServiceDocuments(harness.kb_service, actor_user_id=actor_user_id)
        return L.ProjectKbArchiver(
            documents=documents,
            artifacts=harness.services.project_artifact_repo,
            kb_id=kb_id,
            artifact_id=artifact_id,
        )

    harness.service.bind_runtime(kb_archiver_factory=factory)


def test_the_archive_hop_really_writes_kb_document_id_and_the_document_lands(
    harness: Harness,
) -> None:
    """主判据 + 前置自证（第③档），**同一用例内**。"""
    _bind_real_archiver(harness)
    run = harness.service.create(
        team_agent_id=TEAM_ID, goal="kb archive", tier="quick", user=harness.user
    )
    harness.services.project_repo.set_kb_id(run.project_id, harness.kb_id)

    written = harness.service.write_artifact(
        run.run_id,
        name="SPEC.md",
        content=f"{BODY}\n{PROBE_TEXT}\n",
        revision="",
        role="pm",
        user=harness.user,
    )
    assert written["revision"]

    # ★ 主判据：唯一写者真的写了这一行
    row = harness.services.project_artifact_repo.get_workflow(
        project_id=run.project_id, name="SPEC.md"
    )
    assert row is not None and row.kb_document_id, (
        f"kb_document_id 未落库（期望非空，实得 {getattr(row, 'kb_document_id', None)!r}）"
    )

    # ★★ 前置自证（第③档）：经真实读口读回**文档内容**，断言它带着我写入的文本。
    # ★ 教训（本条初版就是栽在这里）：`list_documents` 只给**元数据行**
    #   （id/path/byte_size/status），**读不出内容**；内容要用 `preview_document`
    #   （既有 fixture 用的就是这个口，见 `test_memory_kb_reference_bridge.py:117`）。
    docs = harness.kb_service.list_documents(harness.kb_id, actor_user_id=harness.user.id)
    assert docs, "KB 里没有文档 ⇒ 归档跳没真跑"
    preview = harness.kb_service.preview_document(
        harness.kb_id, str(docs[0].id), actor_user_id=harness.user.id
    )
    blob = str(preview)
    assert PROBE_TEXT in blob, (
        f"读回的文档**内容**里没有探针文本 ⇒ 前置动作未真正发生。preview={blob[:300]}"
    )


def test_without_a_kb_id_the_hop_does_not_write_it(harness: Harness) -> None:
    """反向对照：**只改 project 的 `kb_id` 一个字段**（None）⇒ 同一写入路径不再产生 `kb_document_id`。"""
    _bind_real_archiver(harness)
    run = harness.service.create(
        team_agent_id=TEAM_ID, goal="kb archive reverse", tier="quick", user=harness.user
    )
    assert harness.services.project_repo.get(run.project_id).kb_id is None  # 反向前提

    harness.service.write_artifact(
        run.run_id,
        name="SPEC.md",
        content=f"{BODY}\n{PROBE_TEXT}\n",
        revision="",
        role="pm",
        user=harness.user,
    )
    row = harness.services.project_artifact_repo.get_workflow(
        project_id=run.project_id, name="SPEC.md"
    )
    assert row is not None
    assert not row.kb_document_id, (
        f"未绑 KB 的 project 也写了 kb_document_id（{row.kb_document_id!r}）"
        " ⇒ 那不是归档跳生效，是字段本来就有值"
    )
