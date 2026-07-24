"""Database services — RepoBundle and SharedServices DI container."""

from __future__ import annotations

from dataclasses import dataclass

from octop.config import OctopConfig
from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.audit import AuditRepo
from octop.infra.db.repos.backends import BackendRepo
from octop.infra.db.repos.care_push import CarePushRepo
from octop.infra.db.repos.channels import ChannelRepo
from octop.infra.db.repos.connectors import ConnectorRepo
from octop.infra.db.repos.cron import CronJobRepo
from octop.infra.db.repos.proactive_care_config import ProactiveCareConfigRepo
from octop.infra.db.repos.providers import ProviderRepo
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.db.repos.sessions import SessionRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.usage import UsageRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.db.repos.voice_providers import VoiceProviderRepo
from octop.infra.utils.paths import PathLayout


@dataclass(frozen=True)
class RepoBundle:
    db: DatabasePool

    user_repo: UserRepo
    agent_repo: AgentRepo
    provider_repo: ProviderRepo
    channel_repo: ChannelRepo
    cron_repo: CronJobRepo
    session_repo: SessionRepo
    thread_repo: ThreadRepo
    secret_repo: SecretRepo
    audit_repo: AuditRepo
    usage_repo: UsageRepo
    settings_repo: SettingsRepo
    storage_backend_repo: BackendRepo
    connector_repo: ConnectorRepo
    voice_provider_repo: VoiceProviderRepo
    care_push_repo: CarePushRepo
    proactive_care_config_repo: ProactiveCareConfigRepo

    @classmethod
    def from_pool(cls, db: DatabasePool) -> RepoBundle:
        return cls(
            db=db,
            user_repo=UserRepo(db),
            agent_repo=AgentRepo(db),
            provider_repo=ProviderRepo(db),
            channel_repo=ChannelRepo(db),
            cron_repo=CronJobRepo(db),
            session_repo=SessionRepo(db),
            thread_repo=ThreadRepo(db),
            secret_repo=SecretRepo(db),
            audit_repo=AuditRepo(db),
            usage_repo=UsageRepo(db),
            settings_repo=SettingsRepo(db),
            storage_backend_repo=BackendRepo(db),
            connector_repo=ConnectorRepo(db),
            voice_provider_repo=VoiceProviderRepo(db),
            care_push_repo=CarePushRepo(db),
            proactive_care_config_repo=ProactiveCareConfigRepo(db),
        )


@dataclass(frozen=True)
class SharedServices:
    paths: PathLayout
    config: OctopConfig
    repos: RepoBundle

    @property
    def db(self) -> DatabasePool:
        return self.repos.db

    @property
    def user_repo(self) -> UserRepo:
        return self.repos.user_repo

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
    def voice_provider_repo(self) -> VoiceProviderRepo:
        return self.repos.voice_provider_repo

    @property
    def care_push_repo(self) -> CarePushRepo:
        return self.repos.care_push_repo

    @property
    def proactive_care_config_repo(self) -> ProactiveCareConfigRepo:
        return self.repos.proactive_care_config_repo


def build_shared_services(
    *, db: DatabasePool, paths: PathLayout, config: OctopConfig
) -> SharedServices:
    return SharedServices(
        paths=paths,
        config=config,
        repos=RepoBundle.from_pool(db),
    )
