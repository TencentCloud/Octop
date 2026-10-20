"""Probe PostgreSQL once before pool-backed integration fixtures."""

import os

import pytest


@pytest.fixture(scope="session")
def postgres_dsn() -> str:
    psycopg = pytest.importorskip("psycopg")
    dsn = os.environ.get("TEST_POSTGRES_DSN", "postgresql://localhost/octop_memory_test")
    try:
        with psycopg.connect(dsn, connect_timeout=2):
            pass
    except psycopg.OperationalError:
        if "TEST_POSTGRES_DSN" in os.environ:
            pytest.fail("TEST_POSTGRES_DSN is set but the dedicated PostgreSQL is unavailable")
        pytest.skip("PostgreSQL not available")
    return dsn
