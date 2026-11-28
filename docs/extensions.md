# Server extensions

A product built on Octop can ship as its own Python package that depends on the
`octop` wheel, instead of a fork that patches Octop's files. The package
declares one entry point in the `octop.extensions` group:

```toml
[project.entry-points."octop.extensions"]
my_product = "my_product.extension:extension"
```

The entry point resolves to any object. Octop calls each of the hooks below
only if the object defines it.

| Hook | When | Use it to |
|------|------|-----------|
| `async on_startup(server)` | End of runtime boot (database, agents, gateway, cron are up) | Start background tasks, warm caches |
| `async on_shutdown(server)` | First step of `OctopServer.stop`, database still open | Stop background tasks |
| `configure_app(app, server)` | In `build_app`, before the dashboard catch-all route | `app.include_router(...)`, exception handlers, static mounts |
| `migrations() -> ExtensionMigrations` | End of `run_migrations` (server, CLI, rebind, restore) | Own tables, see below |
| `repos(db)` | Every time Octop builds its `RepoBundle` for a pool (server start, CLI, database rebind) | Return your repo object(s); read them back with `services.repos.extension("<entry point name>")` |
| `public_paths() -> PublicPaths` | First request | Name `/api/...` paths that skip the Octop JWT (`exact`, `prefixes`) and that stay reachable before setup creates the first user (`setup_exact`, `setup_prefixes`) |

```python
# my_product/extension.py
from fastapi import APIRouter
from octop.infra.extensions import PublicPaths

router = APIRouter(prefix="/api/my-product")


class Extension:
    async def on_startup(self, server): ...
    async def on_shutdown(self, server): ...

    def configure_app(self, app, server):
        app.include_router(router)

    def public_paths(self):
        return PublicPaths(exact=("/api/my-product/status",))


extension = Extension()
```

## Tables

`migrations()` returns `ExtensionMigrations(namespace, directory)` from
`octop.infra.db.extension_migrations`. The directory holds
`NNN_description.sql` (SQLite) and `NNN_description.pg.sql` (PostgreSQL)
files, numbered from `001`. These numbers are independent of Octop's own
migrations, so a product's schema never takes Octop's next number. Each
namespace (`[a-z][a-z0-9_]*`, unique across extensions) keeps its own
version in `_extension_schema`. That table is created only when an extension
declares migrations.

Files run after Octop's migrations, in order. Each file and its version
commit in one transaction, under a lock every connection and process shares
(SQLite `BEGIN IMMEDIATE`, a PostgreSQL advisory lock), and the version is
re-read under that lock. Two workers starting at once run each file exactly
once, and a file that fails leaves nothing behind, so a fixed file can be
retried. Statements are split at a `;` that ends a line: keep one statement
per `;` line (no trigger bodies). Prefix table names with the namespace.

Build repos for those tables in `repos(db)`, not in `on_startup`: Octop calls
it again whenever it opens a new pool (for example when setup switches the
control-plane database), so the repos always point at the live database.

```python
class Extension:
    def migrations(self):
        return ExtensionMigrations("my_product", Path(__file__).parent / "migrations")

    def repos(self, db):
        return MyProductRepos(rooms=RoomRepo(db))

# elsewhere
rooms = server.services.repos.extension("my_product").rooms
```

Rules:

- Extensions load once per process, sorted by entry point name. An extension
  that fails to import is logged and skipped.
- An exception in `on_startup` stops the server from starting. The extensions
  that already started get `on_shutdown` in reverse order, then the runtime
  is stopped and the database closed, so a failed first-run database bind can
  be retried. `on_shutdown` runs only for extensions whose startup finished
  (an extension without `on_startup` counts as started).
- A failing `on_shutdown` is logged, and the other extensions still shut down.
- Public paths must start with `/api/`. A route listed there must
  authenticate the caller itself.
- Agent tools, skills, middleware hooks, and IM channels belong in harness
  plugins (see [plugin-package.md](plugin-package.md)), not here.
