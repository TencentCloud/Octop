# Credential storage and recovery

LLM provider API keys and values in the `secrets` table (including the JWT signing
secret and connector Fernet key) are encrypted with authenticated Fernet encryption.
The master key is stored **outside the database**. Connector credential blobs keep
their existing format; their encryption key is now wrapped by the master key.
Both SQLite and PostgreSQL use the same credential format.

This protects against disclosure of a database file/dump alone. It is not full
database encryption and does not isolate credentials from a process that can read
both the database and the key, inspect Octop's environment/memory, or access its OS
keyring. Other configuration, provider extra headers, voice-provider keys, channel
settings, workspace files and environment files can still contain secrets. Protect
the whole Octop installation and run untrusted tools in a suitably isolated sandbox.

## Choose a key source before upgrading

The sources below are checked in order. A configured source that is unavailable,
invalid or incompatible causes `SECRET_STORAGE_UNAVAILABLE`; Octop does not fall
back to a new key or plaintext. Keep the same source/key across restarts and across
every worker/host sharing a database.

| Source | Configuration |
| --- | --- |
| Process environment | `OCTOP_SECRET_KEY`: a URL-safe base64-encoded 32-byte Fernet key, injected by the service manager or secret manager. |
| OS keyring | `OCTOP_SECRET_KEY_KEYRING`: an explicit, unique deployment account name. The keyring service name is `octop`. |
| Private file | `OCTOP_SECRET_KEY_FILE`: an absolute path; defaults to `$OCTOP_HOME/secrets.key` (`~/.octop/secrets.key`). |

For headless/Docker deployments, an externally provisioned secret file mounted
outside workspace/backup directories is recommended. A read-only secret mount is
supported when it already contains a valid key. With no explicit configuration,
Octop generates the separate `secrets.key` file on first initialization. On POSIX
it is created with mode `0600`; existing files must be owned by the process user
and must not be readable or writable by group/others. On Windows, restrict the
file/directory ACL to the service account. The master key is never written to a
database table or returned through the API.

Keep key files outside directories replaced during restore (plugins, knowledge,
and skill packages). Restore refuses to replace a tree that
contains the configured key file; move the same key to a safe location first.

The OS keyring option uses `keyring` and supports its native macOS Keychain,
Windows Credential Locker, Secret Service and KWallet backends. Configure/unlock
the keyring for the actual Octop service account. If automatic selection returns
a chained or third-party backend, explicitly select a supported native backend
with `PYTHON_KEYRING_BACKEND` as described in the
[keyring documentation](https://keyring.readthedocs.io/en/latest/#configuring).
Null, fail and plaintext third-party stores are refused. No automatic file
fallback occurs when the keyring is locked or unavailable. Initialize one process
first before starting additional workers.

Do not put the master key in `config.json`, source control, a shared agent
workspace or the dashboard Environment variables page. Prefer OS keyring or
service-level injection. Octop's existing environment inheritance still applies
to agent tools; an environment variable is not a boundary against arbitrary code
running as the Octop user.

## Upgrade existing installations

1. Stop all Octop server/CLI processes using the database. Retain a protected
   pre-upgrade backup, and choose/provision the master key source.
2. Start the upgraded Octop normally. Startup migrates plaintext provider keys
   and existing `secrets` rows in one transaction. API keys, existing JWT signing
   bytes and connector Fernet keys are preserved, so existing sessions and OAuth
   credentials continue to work. Repeated startup does not re-encrypt rows.
3. Separately back up the master key in a secure secret store. Test recovery
   before retiring pre-upgrade backups.

SQLite migration also compacts the database and truncates the WAL to remove old
plaintext from SQLite pages. Stop other readers/writers during the upgrade; a
busy WAL checkpoint must be resolved before proceeding. This is not secure erase
of filesystem/volume snapshots or SSD history. PostgreSQL WAL, replicas, physical
backups and old SQLite copies can still contain pre-migration plaintext; retain
them only under the same protection as the original credentials.

Changing/deleting the master key is **not** key rotation. Restore the original
key if startup reports a key error. Never delete `secrets.key` to fix decryption:
there is no recovery from encrypted credentials without the correct key. To move
to another key source, provision the **same key** there before changing settings.

## Provider keys from environment variables

Supply a reference in the existing provider **API Key** field:

```text
env:OPENAI_API_KEY
```

The same syntax works with the provider API and CLI `--api-key` option. Inject
`OPENAI_API_KEY` into the Octop service environment. Only the reference is stored
in `providers.api_key`; the value is resolved for runtime use. Admin responses
return the reference so saving an edited provider does not persist the resolved
value. Draft connection tests and model discovery resolve references too. Missing
or empty variables do not fall back to a previously saved key. Restart/reload
running agents when changing a runtime variable.

Environment names must match `[A-Za-z_][A-Za-z0-9_]*`. A literal key is encrypted
automatically. Using Octop's `env` file or a workspace `.env` persists those
variables to disk; use service-level injection if the value must not be stored
in Octop's files.

## Backup and restore

New system archives contain ciphertext plus a non-secret master-key fingerprint.
They do not contain the master key. The active key file is excluded from included
workspace/package trees, and master-key settings are removed from the archived
Octop `env` file. Other environment values and workspace files remain part of
backups when requested, so **treat every archive as sensitive** and protect it
with access controls and separate backup encryption.

- **Same installation:** restore normally with the original key available.
- **Another machine:** provision the original key separately, before initializing
  the new installation. OS keyring accounts must be provisioned under the new
  service user; copying the database alone is insufficient.
- **Replacing an already initialized installation:** stop Octop and use offline
  `octop backup restore` with the backup's original key supplied to that process.
  Preserve the destination database and its old key separately if rollback is
  needed. Restart with the restored database's key.
- **Old plaintext archives:** supported; credentials are encrypted during restore
  with the destination key. Keep those old archives protected until retired.

Restore checks the key fingerprint before overwriting the live database or files.
For SQLite, it also validates encrypted values in the extracted database, even
when a legacy manifest lacks a fingerprint. PostgreSQL custom archives rely on
the fingerprint in new manifests; keep the manifest and dump together. Do not
strip or edit it. Existing destination key-source settings in Octop's `env` file
are preserved on restore, so copying configuration cannot silently replace them.
