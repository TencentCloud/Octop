"""In-process in-flight peer jobs for team roster locks."""

from __future__ import annotations

from threading import Lock


class TeamJobTracker:
    """Tracks in-flight host→member dispatches.

    Prefer a stable ``job_id`` (inbox id) so begin/end is idempotent. Pair
    counters remain for callers that have no job id. Lost on process restart —
    roster locks do not survive a reboot and cannot fence leftover inbox jobs.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._counts: dict[tuple[str, str], int] = {}
        self._jobs: dict[str, tuple[str, str]] = {}

    def begin(
        self,
        team_agent_id: str,
        member_agent_id: str,
        job_id: str | None = None,
    ) -> None:
        key = (team_agent_id, member_agent_id)
        with self._lock:
            if job_id:
                if job_id in self._jobs:
                    return
                self._jobs[job_id] = key
                return
            self._counts[key] = self._counts.get(key, 0) + 1

    def end(
        self,
        team_agent_id: str,
        member_agent_id: str,
        job_id: str | None = None,
    ) -> None:
        key = (team_agent_id, member_agent_id)
        with self._lock:
            if job_id:
                self._jobs.pop(job_id, None)
                return
            current = self._counts.get(key, 0) - 1
            if current <= 0:
                self._counts.pop(key, None)
            else:
                self._counts[key] = current

    def is_busy(self, team_agent_id: str, member_agent_id: str) -> bool:
        key = (team_agent_id, member_agent_id)
        with self._lock:
            if self._counts.get(key, 0) > 0:
                return True
            return any(pair == key for pair in self._jobs.values())

    def is_member_busy(self, member_agent_id: str) -> bool:
        with self._lock:
            if any(
                count > 0 and member == member_agent_id
                for (_, member), count in self._counts.items()
            ):
                return True
            return any(member == member_agent_id for (_, member) in self._jobs.values())

    def busy_member_ids(self, team_agent_id: str) -> set[str]:
        with self._lock:
            busy = {
                member
                for (team, member), count in self._counts.items()
                if team == team_agent_id and count > 0
            }
            busy.update(member for team, member in self._jobs.values() if team == team_agent_id)
            return busy
