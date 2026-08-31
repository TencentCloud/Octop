import { describe, expect, it } from "vitest";

import {
  applyMemoryBackendChoice,
  buildPostgresMemoryDsn,
  parseMemoryBackendChoice,
  parsePostgresMemoryDsn,
  postgresFormMatchesStored,
  storedPostgresDsn,
} from "./memoryBackendChoice";

describe("parseMemoryBackendChoice", () => {
  it("treats a missing backend as follow", () => {
    expect(parseMemoryBackendChoice({})).toBe("follow");
    expect(
      parseMemoryBackendChoice({ memory: { extract_idle_seconds: 30 } }),
    ).toBe("follow");
  });

  it("reads an explicit type", () => {
    expect(
      parseMemoryBackendChoice({ memory: { backend: { type: "sqlite" } } }),
    ).toBe("sqlite");
    expect(
      parseMemoryBackendChoice({ memory: { backend: { type: "postgres" } } }),
    ).toBe("postgres");
  });
});

describe("applyMemoryBackendChoice", () => {
  it("drops only backend when following the platform", () => {
    const out = applyMemoryBackendChoice(
      { memory: { backend: { type: "sqlite" }, extract_idle_seconds: 120 } },
      "follow",
    );
    expect(out.memory).toEqual({ extract_idle_seconds: 120 });
  });

  it("writes an explicit sqlite backend", () => {
    expect(applyMemoryBackendChoice({}, "sqlite")).toEqual({
      memory: { backend: { type: "sqlite" } },
    });
  });

  it("keeps a custom postgres DSN when the choice stays postgres", () => {
    const out = applyMemoryBackendChoice(
      { memory: { backend: { type: "postgres", dsn: "postgresql://a@b/c" } } },
      "postgres",
    );
    expect(out.memory).toEqual({
      backend: { type: "postgres", dsn: "postgresql://a@b/c" },
    });
  });

  it("builds a DSN from host fields like the setup wizard", () => {
    expect(
      buildPostgresMemoryDsn({
        host: "127.0.0.1",
        port: 5432,
        database: "octop",
        user: "octop",
        password: "p@ss",
      }),
    ).toBe("postgresql://octop:p%40ss@127.0.0.1:5432/octop");
    expect(buildPostgresMemoryDsn({ host: "db" })).toBeUndefined();
  });

  it("writes an explicit DSN when switching to postgres", () => {
    const out = applyMemoryBackendChoice({}, "postgres", {
      dsn: "postgresql://octop:x@db.example:5432/mem",
    });
    expect(out.memory).toEqual({
      backend: {
        type: "postgres",
        dsn: "postgresql://octop:x@db.example:5432/mem",
      },
    });
  });
});

describe("parsePostgresMemoryDsn", () => {
  it("reads wizard fields and ignores the password", () => {
    expect(
      parsePostgresMemoryDsn(
        "postgresql://yingningchen:secret@127.0.0.1:5432/octop_test",
      ),
    ).toEqual({
      host: "127.0.0.1",
      port: 5432,
      database: "octop_test",
      user: "yingningchen",
    });
  });

  it("matches a hydrated form to the stored DSN when password is blank", () => {
    const dsn = "postgresql://yingningchen@127.0.0.1:5432/octop_test";
    expect(storedPostgresDsn({ memory: { backend: { type: "postgres", dsn } } })).toBe(
      dsn,
    );
    expect(
      postgresFormMatchesStored(
        {
          memory_pg_host: "127.0.0.1",
          memory_pg_port: 5432,
          memory_pg_database: "octop_test",
          memory_pg_user: "yingningchen",
        },
        dsn,
      ),
    ).toBe(true);
    expect(
      postgresFormMatchesStored(
        {
          memory_pg_host: "127.0.0.1",
          memory_pg_port: 5432,
          memory_pg_database: "octop_test",
          memory_pg_user: "yingningchen",
          memory_pg_password: "changed",
        },
        dsn,
      ),
    ).toBe(false);
  });
});
