"""Credential reference resolution for external connectors.

Only references are stored in SQLite.  Values are read at connector runtime
from the operating-system keyring or, for local development and tests, from
an explicitly named environment variable.
"""
from __future__ import annotations

import os
from urllib.parse import unquote, urlparse


class CredentialStoreError(RuntimeError):
    """Raised when a configured credential reference cannot be resolved."""


def validate_credential_ref(reference: str) -> str:
    """Validate a stored credential reference without resolving its secret."""
    parsed = urlparse(reference.strip())
    if parsed.scheme.casefold() not in {"env", "keyring"}:
        raise CredentialStoreError("凭证必须引用 env:// 或 keyring://，禁止保存明文")
    if parsed.scheme.casefold() == "env":
        variable = parsed.netloc or parsed.path.lstrip("/")
        if not variable or any(char in variable for char in " \\t\\r\\n"):
            raise CredentialStoreError("环境变量凭证引用无效")
    elif not parsed.netloc or not parsed.path.lstrip("/"):
        raise CredentialStoreError("keyring 凭证引用必须包含 service 和 account")
    return reference.strip()


def resolve_credential_ref(reference: str | None) -> str | None:
    if not reference:
        return None
    validate_credential_ref(reference)
    parsed = urlparse(reference)
    scheme = parsed.scheme.casefold()
    if scheme == "env":
        variable = parsed.netloc or parsed.path.lstrip("/")
        if not variable or any(char in variable for char in " \\t\\r\\n"):
            raise CredentialStoreError("环境变量凭证引用无效")
        value = os.environ.get(variable)
        if not value:
            raise CredentialStoreError(f"凭证环境变量未配置: {variable}")
        return value
    if scheme == "keyring":
        service = parsed.netloc
        account = parsed.path.lstrip("/")
        if not service or not account:
            raise CredentialStoreError("keyring 凭证引用必须包含 service 和 account")
        try:
            import keyring
        except ImportError as exc:  # pragma: no cover - depends on installation
            raise CredentialStoreError("当前环境未安装 keyring") from exc
        value = keyring.get_password(unquote(service), unquote(account))
        if not value:
            raise CredentialStoreError("keyring 中未找到配置的凭证")
        return value
    raise CredentialStoreError("凭证必须引用 env:// 或 keyring://，禁止在配置中保存明文")
