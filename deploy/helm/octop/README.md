# Octop Helm chart

[中文](README_CN.md)

One release installs Octop and, by default, PostgreSQL with pgvector. Replicas share that control plane. Cron jobs and IM channels take a database lease so only one replica runs each of them. The chart does not install a HorizontalPodAutoscaler.

Each Pod is still one process. Every replica loads enabled experts at startup. Dashboard WebSocket delivery and trajectory updates stay in that process. The Ingress cookie `OCTOP_AFFINITY` pins one browser to one Pod. After that Pod disappears, the next request moves to a live replica. Leave Service `sessionAffinity` unset.

Agent workspaces in this install use PostgreSQL, OpenSandbox, or another movable backend. `OCTOP_HOME` on each Pod is an emptyDir, so it is not a shared workspace. Use the user policy `allowed_backend_types` to keep new experts off the local filesystem. The Feishu dedup database is also local. After the Pod that held that channel is replaced, Feishu redelivery can be processed twice for a short time. That gap is accepted.

The longer multi-replica guide is [docs/cluster_CN.md](../../../docs/cluster_CN.md).

## Where to install from

Install the chart from GHCR. A clone is not required. The chart sits next to the image. There is no separate HTTP Helm repository. A `v*` tag publishes the package. `appVersion` is the image tag, for example `1.0.3b5`. Helm chart `version` must be SemVer, so `1.0.3b5` is published as `1.0.3-b5` and `1.0.3` stays `1.0.3`. The published `appVersion` is already the image tag, so the install does not set `image.tag`.

```bash
helm upgrade --install octop oci://ghcr.io/tencentcloud/octop/charts/octop \
  --version 1.0.3-b5 \
  -n octop \
  --set ingress.host=octop.example.com
```

Edit chart source in `deploy/helm/octop` and install that directory from the repository root. Later upgrades keep the first source: an OCI install keeps `--version`, a directory install keeps `deploy/helm/octop`.

## What you set

The chart does not store passwords and does not create Secrets from values. Published defaults are `helm show values oci://ghcr.io/tencentcloud/octop/charts/octop --version 1.0.3-b5`. In this repository, `values.example.yaml` is the same knobs with comments, and `secrets.example.yaml` is the password sample. Copy them, change the hostname and image, replace the placeholders, and do not commit filled-in passwords.

```bash
helm upgrade --install octop oci://ghcr.io/tencentcloud/octop/charts/octop \
  --version 1.0.3-b5 \
  -n octop \
  -f my-values.yaml
```

| Setting | Required | Role |
|---------|----------|------|
| Secret `octop-admin` keys `username`, `password` | Yes | Console login. Used only when the admin user is first created |
| Secret `octop-pg` keys `user`, `password`, `database` | Yes | PostgreSQL database name, user, and password. Not the console password |
| `ingress.host` | Yes when Ingress is enabled | Public hostname. An empty `config.corsOrigins` becomes `https://<ingress.host>` |
| Secret `octop-tls` | Yes when `ingress.tls.enabled` is true | TLS certificate for that hostname. Default name `octop-tls` |
| `image.tag` | Set this | Empty uses the chart `appVersion`. Use a tag that exists in the registry |
| `replicaCount` | Optional | Default 2. There is no HPA; change this value and upgrade |
| `config.timezone` | Optional | Default `Asia/Shanghai` |
| `postgresql.enabled` | Optional | Default true deploys pgvector. Set false and set `database.host` for a managed database |
| `shm.enabled` | On for the full image | Leave false for the lite image. The virtual desktop, local embeddings, and OCR need a `<version>-full` tag and this flag |

The admin password must be at least 8 characters, contain both letters and digits, and must not be a common password. Otherwise no admin is created and each Pod starts the setup wizard on its own. After the first boot, changing `octop-admin` does not change the console password already stored. Changing `octop-pg` does not change the database role already stored in the volume. Change that role with `ALTER USER`, then update the Secret. Change the console password after you sign in.

While editing the source, the same defaults are `helm show values deploy/helm/octop`.

## Publishing the chart

Pushing the chart to GHCR does not need a separate Helm repository key or chart signing key. `.github/workflows/helm-publish.yml` uses the built-in `GITHUB_TOKEN` with `contents: read` and `packages: write`. The repository's workflow permissions must allow reading and writing packages. If the organization restricts package creation or public packages, an admin has to allow this repository to publish them.

The workflow runs on a `v*` tag, or on a manual run with `tag=v1.0.3b5`. A manual tag must point at a commit that already contains this chart. The existing `v1.0.3b5` tag does not, so it is not backfilled. The image is published by the Docker workflow to `ghcr.io/tencentcloud/octop`. The chart only names that tag; packaging does not pull the image. The package name is `octop/charts/octop`, separate from the container image package `octop`.

A manual push uses a GitHub PAT with `write:packages`. `helm package` on the git tree publishes chart version `0.1.0`. To match a release tag, rewrite `Chart.yaml` `version` and `appVersion` the way the workflow does, and do not commit that rewrite:

```bash
echo "$GHCR_PAT" | helm registry login ghcr.io --username <GitHub user> --password-stdin
helm package deploy/helm/octop
helm push octop-*.tgz oci://ghcr.io/tencentcloud/octop/charts
```

After the first push, confirm the package is public. A private package requires a login for `helm pull`.

## Requirements

- Kubernetes 1.25 or newer, Helm 3, and a default StorageClass when the bundled database is enabled (20Gi ReadWriteOnce)
- Pull access to `pgvector/pgvector:pg16` and `ghcr.io/tencentcloud/octop:<tag>`. The init container that waits for PostgreSQL uses `postgresql.image`, including when the database is managed
- Ingress NGINX when `ingress.className` stays `nginx`. Another controller needs its own class name and annotations in values
- A TLS certificate for the Ingress host, stored as Secret `octop-tls`, when TLS is enabled

`image.tag` defaults to the chart `appVersion`. Set it to a tag that exists in the registry. The default repository is the lite image. For the virtual desktop, local embeddings, or OCR, set the tag to `<version>-full` and set `shm.enabled` to `true`.

## Install

The two Secrets and the password rules are in the previous section. Set `--version` to a published chart version. The image tag comes from that package's `appVersion`.

```bash
kubectl create namespace octop

kubectl -n octop create secret generic octop-pg \
  --from-literal=user=octop \
  --from-literal=password="$(openssl rand -base64 24)" \
  --from-literal=database=octop

kubectl -n octop create secret generic octop-admin \
  --from-literal=username=admin \
  --from-literal=password='REPLACE_WITH_ADMIN_PASSWORD'

kubectl -n octop create secret tls octop-tls \
  --cert=fullchain.pem --key=privkey.pem

helm upgrade --install octop oci://ghcr.io/tencentcloud/octop/charts/octop \
  --version 1.0.3-b5 \
  -n octop \
  --set ingress.host=octop.example.com
```

Without a public hostname, or when the ingress controller is not Ingress NGINX, turn Ingress off and use a port forward:

```bash
helm upgrade --install octop oci://ghcr.io/tencentcloud/octop/charts/octop \
  --version 1.0.3-b5 \
  -n octop \
  --set ingress.enabled=false

kubectl -n octop port-forward svc/octop 8088:8088
```

For another ingress controller, change `ingress.className` and replace the NGINX entries in `ingress.annotations`. MicroK8s Traefik commonly uses the class `public`. Keep cookie stickiness, a long connection timeout, and response buffering disabled on that controller.

On the first boot the two replicas may both run `octop init`. The one that finishes second sees the admin already exists, skips creation, and continues. If they hit the unique constraint together, the second Pod exits and starts again, then skips creation.

After the database volume is initialized, changing the `octop-pg` user or password does not change the role already stored in that volume. Change it with `ALTER USER`, then update the Secret.

## Check

```bash
kubectl -n octop rollout status statefulset/octop-pgvector
kubectl -n octop rollout status deploy/octop

kubectl -n octop exec octop-pgvector-0 -- \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\dx"'

kubectl -n octop port-forward svc/octop 8088:8088
curl -fsS http://127.0.0.1:8088/api/health
```

`\dx` lists `vector`. `/api/health` returns JSON with `ok` and `db` both true.

Sign in through the Ingress host with the `octop-admin` username and password. The replica that claimed a lease runs that channel or cron job. The others log a skip.

## Change the hostname

```bash
helm upgrade octop oci://ghcr.io/tencentcloud/octop/charts/octop \
  --version 1.0.3-b5 \
  -n octop \
  --reuse-values \
  --set ingress.host=octop.example.com
```

Keep the TLS secret's names in step with that host. If TLS is turned off, also set `nginx.ingress.kubernetes.io/session-cookie-secure` to `"false"`.

## Replicas and upgrades

```bash
helm upgrade octop oci://ghcr.io/tencentcloud/octop/charts/octop \
  --version 1.0.3-b5 \
  -n octop \
  --reuse-values \
  --set replicaCount=3
```

A rolling update starts a new Pod before stopping an old one. The old Pod releases channel and cron leases on exit. A new Pod claims them on the next reconcile. A page stuck to the old Pod disconnects. A refresh lands on a live replica.

## Managed PostgreSQL

Leave the extension to the database operator (`CREATE EXTENSION vector`). The chart then skips its own database:

```bash
helm upgrade --install octop oci://ghcr.io/tencentcloud/octop/charts/octop \
  --version 1.0.3-b5 \
  -n octop \
  --set postgresql.enabled=false \
  --set database.host=pg.example.com \
  --set ingress.host=octop.example.com
```

The `octop-pg` Secret still supplies the database name, user, and password. Octop applies control-plane migrations on startup. Do not apply `*.pg.sql` by hand.
