"""Credential serialization with a master key stored outside the database."""

from __future__ import annotations

import base64
import hashlib
import os
import stat
import tempfile
from contextlib import suppress
from pathlib import Path
from threading import RLock

from cryptography.fernet import Fernet, InvalidToken

from octop.i18n import error_message
from octop.infra.errors import ErrorCode, OctopError

PREFIX = b"octop:fernet:v1:"
KEY_ENV = "OCTOP_SECRET_KEY"
KEY_FILE_ENV = "OCTOP_SECRET_KEY_FILE"
KEYRING_ENV = "OCTOP_SECRET_KEY_KEYRING"


def storage_error() -> OctopError:
    code = ErrorCode.SECRET_STORAGE_UNAVAILABLE
    return OctopError(code, error_message(code, "en"))


class CredentialCipher:
    """One deployment key, loaded lazily and never persisted alongside ciphertext.

    An explicit keyring account opts into the OS credential store. Otherwise a
    private key file supports unattended/headless installs. Process environment
    injection takes precedence over either store.
    """

    def __init__(self, home: Path) -> None:
        self.key_path = Path(os.environ.get(KEY_FILE_ENV) or home / "secrets.key")
        self._keyring_account = os.environ.get(KEYRING_ENV)
        self._fernet: Fernet | None = None
        self._key_id: str | None = None
        self._lock = RLock()

    def _file_key(self, *, create: bool) -> bytes:
        path = self.key_path
        if not path.exists() and create:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Publish a fully written file without overwriting another worker's key.
            fd, name = tempfile.mkstemp(prefix=".octop-key-", dir=path.parent)
            tmp = Path(name)
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(Fernet.generate_key())
                    f.flush()
                    os.fsync(f.fileno())
                with suppress(FileExistsError):
                    os.link(tmp, path)
            finally:
                tmp.unlink(missing_ok=True)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(path, flags), "rb") as f:
            info = os.fstat(f.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise storage_error()
            if os.name == "posix" and (info.st_mode & 0o077 or info.st_uid != os.getuid()):
                raise storage_error()
            return f.read(128).strip()

    def _keyring_key(self, *, create: bool) -> bytes:
        import keyring

        backend = keyring.get_keyring()
        # Do not silently select a plaintext third-party or null/fail backend.
        if type(backend).__module__ not in {
            "keyring.backends.macOS",
            "keyring.backends.Windows",
            "keyring.backends.SecretService",
            "keyring.backends.kwallet",
        }:
            raise storage_error()
        assert self._keyring_account is not None
        value = backend.get_password("octop", self._keyring_account)
        if value is None and create:
            value = Fernet.generate_key().decode("ascii")
            backend.set_password("octop", self._keyring_account, value)
            if backend.get_password("octop", self._keyring_account) != value:
                raise storage_error()
        if value is None:
            raise storage_error()
        return value.encode("ascii")

    def _load(self, *, create: bool) -> Fernet:
        with self._lock:
            if self._fernet is None:
                try:
                    if KEY_ENV in os.environ:
                        key = os.environ[KEY_ENV].encode("ascii")
                    elif self._keyring_account:
                        key = self._keyring_key(create=create)
                    else:
                        key = self._file_key(create=create)
                    self._fernet = Fernet(key)
                    self._key_id = hashlib.sha256(base64.urlsafe_b64decode(key)).hexdigest()
                except Exception:
                    # No key material or backend exception text in logs / API errors.
                    raise storage_error() from None
            return self._fernet

    def encrypt(self, value: bytes) -> bytes:
        return PREFIX + self._load(create=True).encrypt(value)

    def decrypt(self, value: bytes) -> bytes:
        if not value.startswith(PREFIX):
            if value.startswith(b"octop:fernet:"):
                raise storage_error()
            # Legacy rows are upgraded by the startup migration, including restores.
            return value
        try:
            return self._load(create=False).decrypt(value[len(PREFIX) :])
        except InvalidToken:
            raise storage_error() from None

    def key_id(self) -> str:
        self._load(create=False)
        assert self._key_id is not None
        return self._key_id
