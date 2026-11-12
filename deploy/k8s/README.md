# Octop on Kubernetes

[中文](README_CN.md)

One set of manifests deploys three things: PostgreSQL with pgvector, multiple Octop replicas, and one external entrypoint. The replicas share one control-plane configuration. Cron jobs and IM channels take a database lease so only one replica runs each of them.

## What this stack shares

The PostgreSQL control plane already holds the shared configuration:

- Users, models, connectors, channels, and cron jobs
- Skill-package sources (`skill_package_files`)
- Knowledge-base originals and pgvector embeddings (`knowledge_files`, `knowledge_chunks`)
- The JWT secret (the `secrets` table; every replica reads the same row)
- Agent memory. With a PostgreSQL control plane, an agent that does not set its own memory backend uses that same database, in schema `agent_<id>`

A cron job or IM channel runs only after it claims a row lease. The lease lasts about 90 seconds and the holder renews it about every 30 seconds. Shutdown releases it. Another replica picks it up on the next reconcile.

## What still depends on a sticky entrypoint

Every replica loads the enabled experts at startup. The lease covers channels and cron runs, not the expert process.

Dashboard WebSocket delivery and trajectory live updates stay in process memory. They are not forwarded across replicas. A chat request that lands on a different Pod drops the live stream.

The Ingress cookie pins one browser to one Pod. After that Pod disappears, the next request moves to a live replica. Leave Service `sessionAffinity` unset. `ClientIP` affinity would pin every user who arrives through the same Ingress Pod to a single Octop replica.

Agent workspace files follow that agent's backend. The default is the local filesystem on the Pod `emptyDir`, so those files disappear when the Pod is recreated. To keep them in a cluster, point the agent backend at S3, COS, OpenSandbox, or another movable backend. The Feishu dedup database is also local. After the Pod that held that channel is replaced, Feishu redelivery can be processed twice for a short time.

## Requirements

- Kubernetes and a default StorageClass (PostgreSQL requests a 20Gi ReadWriteOnce volume)
- Pull access to `pgvector/pgvector:pg16` and `ghcr.io/tencentcloud/octop:latest`
- Ingress NGINX. `ingressClassName` is `nginx`. Another controller needs its own class name and affinity annotations in `octop/ingress.yaml`
- A TLS certificate for `octop.example.com`, stored as Secret `octop-tls`

`:latest` is the lite image. It has no virtual desktop, local embeddings, or OCR. For those, change the Deployment image to `ghcr.io/tencentcloud/octop:<version>-full` and give the container about 1Gi of shm.

## Files

| File | Role |
|------|------|
| `kustomization.yaml` | Namespace `octop` and the resources below |
| `postgres/configmap.yaml` | `CREATE EXTENSION vector`, same SQL as `deploy/docker/postgres/init-vector.sql` |
| `postgres/` | Single-replica pgvector. The extension script runs only on first volume init |
| `octop/deployment.yaml` | Two replicas by default |
| `octop/service.yaml` | In-cluster `octop:8088`, no session affinity |
| `octop/ingress.yaml` | TLS, cookie stickiness, WebSocket timeouts, 100Mi uploads |
| `octop/pdb.yaml` | At most one replica down during voluntary disruption |
| `secrets.example.yaml` | Secret example, not part of the kustomization |

## Install

Run from the repository root. Database and admin passwords are separate secrets. The admin password must be at least 8 characters and contain both letters and digits. If it fails that policy, the entrypoint does not create an admin and each Pod starts the setup wizard on its own.

```bash
kubectl apply -f deploy/k8s/namespace.yaml

kubectl -n octop create secret generic octop-pg \
  --from-literal=user=octop \
  --from-literal=password="$(openssl rand -base64 24)" \
  --from-literal=database=octop

kubectl -n octop create secret generic octop-admin \
  --from-literal=username=admin \
  --from-literal=password='REPLACE_WITH_ADMIN_PASSWORD'

kubectl -n octop create secret tls octop-tls \
  --cert=fullchain.pem --key=privkey.pem

kubectl apply -k deploy/k8s
kubectl -n octop rollout status statefulset/octop-pgvector
kubectl -n octop rollout status deploy/octop
```

On the first start both replicas may run `octop init`. The later one skips creation when the admin already exists and still starts. If the two inserts hit the unique constraint together, the later Pod exits once and skips creation after restart. That restart is expected.

After the data volume is initialized, changing the username or password in `octop-pg` does not change the role already stored in Postgres. Change it with `ALTER USER`, then update the Secret.

## Change the public hostname

Change these together:

1. `host` and `tls.hosts` in `octop/ingress.yaml`
2. `OCTOP_CORS_ORIGINS` in `octop/deployment.yaml` (include the scheme, for example `https://octop.example.com`)
3. TLS Secret `octop-tls`

Apply again with `kubectl apply -k deploy/k8s`.

## Check

```bash
kubectl -n octop exec octop-pgvector-0 -- \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\dx"'

kubectl -n octop port-forward svc/octop 8088:8088
curl -fsS http://127.0.0.1:8088/api/health
```

`\dx` lists `vector`. `/api/health` returns JSON with `ok` true and `db` true.

Open the Ingress host and sign in with the username and password from `octop-admin`. Channel and cron ownership shows up in the logs: the replica that claimed the lease runs the work, and the others record a skip.

## Scale and roll

```bash
kubectl -n octop scale deploy/octop --replicas=3
kubectl -n octop rollout restart deploy/octop
```

A rolling update starts a new Pod before stopping an old one. The old Pod releases channel and cron leases on exit, and a new Pod claims them on the next reconcile. A page stuck to the old Pod disconnects; a refresh lands on a live replica.

## Use a managed PostgreSQL

Skip the `postgres/` manifests when the database is managed elsewhere. That server must already allow `CREATE EXTENSION vector` (many managed roles cannot create extensions themselves). Keep the Octop Deployment, Service, Ingress, and PDB, and point `OCTOP_DATABASE_HOST` at the managed address. Octop still applies control-plane migrations on startup. There is no need to run `*.pg.sql` by hand.
