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

Rules:

- Extensions load once per process, sorted by entry point name. An extension
  that fails to import is logged and skipped. An exception in `on_startup`
  stops the server from starting. A failing `on_shutdown` is logged, and the
  other extensions still shut down.
- Public paths must start with `/api/`. A route listed there must
  authenticate the caller itself.
- Agent tools, skills, middleware hooks, and IM channels belong in harness
  plugins (see [plugin-package.md](plugin-package.md)), not here.
