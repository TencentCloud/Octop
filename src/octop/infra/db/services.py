"""Database services — RepoBundle and SharedServices DI container."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from octop.config import OctopConfig
from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.audit import AuditRepo
from octop.infra.db.repos.backends import BackendRepo
from octop.infra.db.repos.care_push import CarePushRepo
from octop.infra.db.repos.channels import ChannelRepo
from octop.infra.db.repos.connectors import ConnectorRepo
from octop.infra.db.repos.cron import CronJobRepo
from octop.infra.db.repos.invites import InviteRepo
from octop.infra.db.repos.knowledge import KnowledgeRepo
from octop.infra.db.repos.proactive_care_config import ProactiveCareConfigRepo
from octop.infra.db.repos.project_artifacts import ProjectArtifactRepo
from octop.infra.db.repos.project_connectors import ProjectConnectorRepo
from octop.infra.db.repos.project_content import ProjectCommentRepo
from octop.infra.db.repos.project_custom_fields import ProjectCustomFieldRepo
from octop.infra.db.repos.project_skills import ProjectSkillRepo
from octop.infra.db.repos.project_tags import ProjectTagRepo
from octop.infra.db.repos.project_task_findings import ProjectTaskFindingRepo
from octop.infra.db.repos.project_tasks import ProjectTaskRepo, TimelineRepo
from octop.infra.db.repos.projects import (
    ProjectMemberRepo,
    ProjectRepo,
)
from octop.infra.db.repos.providers import ProviderRepo
from octop.infra.db.repos.published_experts import PublishedExpertRepo
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.db.repos.sessions import SessionRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.db.repos.skill_packages import SkillPackageRepo
from octop.infra.db.repos.sso import SsoRepo
from octop.infra.db.repos.team_runs import TeamRunRepo
from octop.infra.db.repos.thread_messages import ThreadMessageRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.trajectory_events import TrajectoryEventRepo
from octop.infra.db.repos.usage import UsageRepo
from octop.infra.db.repos.user_policies import UserPolicyRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.db.repos.voice_providers import VoiceProviderRepo
from octop.infra.utils.paths import PathLayout


@dataclass(frozen=True)
class RepoBundle:
    db: DatabasePool

    user_repo: UserRepo
    user_policy_repo: UserPolicyRepo
    invite_repo: InviteRepo
    agent_repo: AgentRepo
    provider_repo: ProviderRepo
    channel_repo: ChannelRepo
    cron_repo: CronJobRepo
    session_repo: SessionRepo
    thread_repo: ThreadRepo
    thread_message_repo: ThreadMessageRepo
    trajectory_event_repo: TrajectoryEventRepo
    secret_repo: SecretRepo
    audit_repo: AuditRepo
    usage_repo: UsageRepo
    settings_repo: SettingsRepo
    storage_backend_repo: BackendRepo
    connector_repo: ConnectorRepo
    skill_package_repo: SkillPackageRepo
    published_expert_repo: PublishedExpertRepo
    knowledge_repo: KnowledgeRepo
    voice_provider_repo: VoiceProviderRepo
    care_push_repo: CarePushRepo
    proactive_care_config_repo: ProactiveCareConfigRepo
    project_repo: ProjectRepo
    project_member_repo: ProjectMemberRepo
    project_task_repo: ProjectTaskRepo
    project_comment_repo: ProjectCommentRepo
    project_tag_repo: ProjectTagRepo
    project_custom_field_repo: ProjectCustomFieldRepo
    project_artifact_repo: ProjectArtifactRepo
    project_connector_repo: ProjectConnectorRepo
    project_skill_repo: ProjectSkillRepo
    timeline_repo: TimelineRepo
    sso_repo: SsoRepo
    team_run_repo: TeamRunRepo
    task_finding_repo: ProjectTaskFindingRepo

    @classmethod
    def from_pool(cls, db: DatabasePool) -> RepoBundle:
        return cls(
            db=db,
            user_repo=UserRepo(db),
            user_policy_repo=UserPolicyRepo(db),
            invite_repo=InviteRepo(db),
            agent_repo=AgentRepo(db),
            provider_repo=ProviderRepo(db),
            channel_repo=ChannelRepo(db),
            cron_repo=CronJobRepo(db),
            session_repo=SessionRepo(db),
            thread_repo=ThreadRepo(db),
            thread_message_repo=ThreadMessageRepo(db),
            trajectory_event_repo=TrajectoryEventRepo(db),
            secret_repo=SecretRepo(db),
            audit_repo=AuditRepo(db),
            usage_repo=UsageRepo(db),
            settings_repo=SettingsRepo(db),
            storage_backend_repo=BackendRepo(db),
            connector_repo=ConnectorRepo(db),
            skill_package_repo=SkillPackageRepo(db),
            published_expert_repo=PublishedExpertRepo(db),
            knowledge_repo=KnowledgeRepo(db),
            voice_provider_repo=VoiceProviderRepo(db),
            care_push_repo=CarePushRepo(db),
            proactive_care_config_repo=ProactiveCareConfigRepo(db),
            project_repo=ProjectRepo(db),
            project_member_repo=ProjectMemberRepo(db),
            project_task_repo=ProjectTaskRepo(db),
            project_comment_repo=ProjectCommentRepo(db),
            project_tag_repo=ProjectTagRepo(db),
            project_custom_field_repo=ProjectCustomFieldRepo(db),
            project_artifact_repo=ProjectArtifactRepo(db),
            project_connector_repo=ProjectConnectorRepo(db),
            project_skill_repo=ProjectSkillRepo(db),
            timeline_repo=TimelineRepo(db),
            sso_repo=SsoRepo(db),
            team_run_repo=TeamRunRepo(db),
            task_finding_repo=ProjectTaskFindingRepo(db),
        )


@dataclass(frozen=True)
class SharedServices:
    paths: PathLayout
    config: OctopConfig
    repos: RepoBundle
    #: Memo for :meth:`team_run_service`. A mutable *container* rather than a mutable
    #: attribute: the dataclass stays frozen (``compare=False`` keeps equality and the
    #: hash exactly as they were), while the service can still be resolved once. The
    #: alternative -- dropping ``frozen=True`` here -- would have changed equality and
    #: hashing for every user of this bundle, or forced ``object.__setattr__``, which
    #: writes around the frozen contract instead of honouring it.
    _team_run_service_memo: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @property
    def db(self) -> DatabasePool:
        return self.repos.db

    @property
    def user_repo(self) -> UserRepo:
        return self.repos.user_repo

    @property
    def user_policy_repo(self) -> UserPolicyRepo:
        return self.repos.user_policy_repo

    @property
    def invite_repo(self) -> InviteRepo:
        return self.repos.invite_repo

    @property
    def agent_repo(self) -> AgentRepo:
        return self.repos.agent_repo

    @property
    def provider_repo(self) -> ProviderRepo:
        return self.repos.provider_repo

    @property
    def channel_repo(self) -> ChannelRepo:
        return self.repos.channel_repo

    @property
    def cron_repo(self) -> CronJobRepo:
        return self.repos.cron_repo

    @property
    def session_repo(self) -> SessionRepo:
        return self.repos.session_repo

    @property
    def thread_repo(self) -> ThreadRepo:
        return self.repos.thread_repo

    @property
    def thread_message_repo(self) -> ThreadMessageRepo:
        return self.repos.thread_message_repo

    @property
    def trajectory_event_repo(self) -> TrajectoryEventRepo:
        return self.repos.trajectory_event_repo

    @property
    def secret_repo(self) -> SecretRepo:
        return self.repos.secret_repo

    @property
    def audit_repo(self) -> AuditRepo:
        return self.repos.audit_repo

    @property
    def usage_repo(self) -> UsageRepo:
        return self.repos.usage_repo

    @property
    def settings_repo(self) -> SettingsRepo:
        return self.repos.settings_repo

    @property
    def storage_backend_repo(self) -> BackendRepo:
        return self.repos.storage_backend_repo

    @property
    def connector_repo(self) -> ConnectorRepo:
        return self.repos.connector_repo

    @property
    def skill_package_repo(self) -> SkillPackageRepo:
        return self.repos.skill_package_repo

    @property
    def published_expert_repo(self) -> PublishedExpertRepo:
        return self.repos.published_expert_repo

    @property
    def knowledge_repo(self) -> KnowledgeRepo:
        return self.repos.knowledge_repo

    @property
    def voice_provider_repo(self) -> VoiceProviderRepo:
        return self.repos.voice_provider_repo

    @property
    def care_push_repo(self) -> CarePushRepo:
        return self.repos.care_push_repo

    @property
    def proactive_care_config_repo(self) -> ProactiveCareConfigRepo:
        return self.repos.proactive_care_config_repo

    @property
    def project_repo(self) -> ProjectRepo:
        return self.repos.project_repo

    @property
    def project_member_repo(self) -> ProjectMemberRepo:
        return self.repos.project_member_repo

    @property
    def project_task_repo(self) -> ProjectTaskRepo:
        return self.repos.project_task_repo

    @property
    def project_comment_repo(self) -> ProjectCommentRepo:
        return self.repos.project_comment_repo

    @property
    def project_tag_repo(self) -> ProjectTagRepo:
        return self.repos.project_tag_repo

    @property
    def project_custom_field_repo(self) -> ProjectCustomFieldRepo:
        return self.repos.project_custom_field_repo

    @property
    def project_artifact_repo(self) -> ProjectArtifactRepo:
        return self.repos.project_artifact_repo

    @property
    def project_connector_repo(self) -> ProjectConnectorRepo:
        return self.repos.project_connector_repo

    @property
    def project_skill_repo(self) -> ProjectSkillRepo:
        return self.repos.project_skill_repo

    @property
    def timeline_repo(self) -> TimelineRepo:
        return self.repos.timeline_repo

    @property
    def sso_repo(self) -> SsoRepo:
        return self.repos.sso_repo

    @property
    def team_run_repo(self) -> TeamRunRepo:
        return self.repos.team_run_repo

    @property
    def task_finding_repo(self) -> ProjectTaskFindingRepo:
        return self.repos.task_finding_repo

    def team_run_service(self) -> Any:
        """Construct the expert-team run service.

        Imported lazily on purpose: ``TeamRunService`` lives in
        ``infra/agents/teams/run_service.py``, which is **not** part of the DB layer
        -- a module-level import would point ``infra/db`` at ``infra/agents`` and
        break the inward-only dependency rule (AGENTS.md section 5). The service is
        also built after this bundle, so a circular import would be the alternative.

        **Memoised on purpose.** ``bind_runtime`` mutates the service *in place*, and the
        server's boot does ``build once -> inject the gateway -> bind_runtime on that
        object``. Returning a fresh instance per call therefore handed the HTTP routers
        an unbound service: the gateway's copy had the runtime, the routes did not, and
        rooms / dispatch / artifact I/O were dead on the HTTP face -- silently, because
        nothing errors when the wiring is merely dangling.
        """
        memo = self._team_run_service_memo
        service = memo.get("service")
        if service is None:
            from octop.infra.agents.teams.run_service import TeamRunService

            service = TeamRunService(services=self)
            memo["service"] = service
        return service


def build_shared_services(
    *, db: DatabasePool, paths: PathLayout, config: OctopConfig
) -> SharedServices:
    return SharedServices(
        paths=paths,
        config=config,
        repos=RepoBundle.from_pool(db),
    )
