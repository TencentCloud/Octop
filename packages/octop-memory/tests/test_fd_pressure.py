"""69 agents remain usable under the reported 1024-fd limit (Octop#2060)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(os.name != "posix", reason="requires POSIX RLIMIT_NOFILE")
def test_multi_agent_workers_do_not_exhaust_file_descriptors(tmp_path: Path) -> None:
    import resource

    hard = resource.getrlimit(resource.RLIMIT_NOFILE)[1]
    if hard != resource.RLIM_INFINITY and hard < 1024:
        pytest.skip("test requires a hard fd limit of at least 1024")
    script = r"""
import concurrent.futures
import fcntl
import gc
import resource
import socket
import sys
import threading
from pathlib import Path
from octop_memory import Memory

hard = resource.getrlimit(resource.RLIMIT_NOFILE)[1]
resource.setrlimit(resource.RLIMIT_NOFILE, (1024, hard))

def fds():
    count = 0
    for fd in range(1024):
        try:
            fcntl.fcntl(fd, fcntl.F_GETFD)
            count += 1
        except OSError:
            pass
    return count

baseline = fds()
memories = []
try:
    for index in range(69):
        memories.append(Memory(namespace=f'agent_{index}', backend_config={
            'db_path': str(Path(sys.argv[1]) / f'{index}.sqlite')
        }))
    barrier = threading.Barrier(8)
    def query_all():
        barrier.wait(timeout=10)
        for memory in memories:
            memory.backend.list_raw(limit=1)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(query_all) for _ in range(8)]
        for future in futures:
            future.result(timeout=15)
        with socket.socket():
            pass
        assert fds() < 512, f'workers retained {fds()} file descriptors'
finally:
    for memory in memories:
        if memory._checkpointer is not None:
            memory._checkpointer.conn.close()
        memory.backend.close()
    gc.collect()
assert fds() == baseline, (baseline, fds())
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)], capture_output=True, text=True, timeout=40, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
