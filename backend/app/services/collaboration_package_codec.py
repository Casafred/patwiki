"""Bounded and authenticated snapshot envelope, independent of the transport."""
from __future__ import annotations

import hashlib
import io
import json
import secrets
import zipfile
import zlib
from datetime import datetime
from typing import Literal

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

MAX_BYTES = 100 * 1024 * 1024
MAX_RECORDS = 20000
MAX_LINE_BYTES = 2 * 1024 * 1024
PROFILE = "patent-snapshot-v1"
UID_PATTERN = r"^[a-z]+_[a-f0-9]{32}$"


class WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Envelope(WireModel):
    format: Literal["patwiki.pwshare"] = "patwiki.pwshare"
    format_version: Literal[1] = 1
    profile: Literal["patent-snapshot-v1"] = PROFILE
    package_id: str = Field(pattern=UID_PATTERN)
    encryption: Literal["aes-256-gcm+argon2id"] = "aes-256-gcm+argon2id"


class SnapshotRecord(WireModel):
    entity_type: Literal["patent"] = "patent"
    entity_uid: str = Field(pattern=UID_PATTERN)
    record_version: int = Field(ge=1)
    origin_node_uid: str = Field(pattern=UID_PATTERN)
    updated_at: str | None = None
    scope: dict = Field(default_factory=dict)
    payload: dict
    field_provenance: dict = Field(default_factory=dict)


class SnapshotManifest(WireModel):
    package_id: str = Field(pattern=UID_PATTERN)
    profile: Literal["patent-snapshot-v1"] = PROFILE
    package_type: Literal["snapshot"] = "snapshot"
    created_at: str
    expires_at: str
    created_by: dict
    origin_node_uid: str = Field(pattern=UID_PATTERN)
    fields: list[str] = Field(min_length=1, max_length=100)
    count: int = Field(ge=0, le=MAX_RECORDS)
    databases: list[dict] = Field(max_length=500)
    signature_status: Literal["not_signed"] = "not_signed"


class SnapshotPermissions(WireModel):
    access: Literal["viewer"] = "viewer"
    recipients: list[str] = Field(min_length=1, max_length=100)
    fields: list[str] = Field(min_length=1, max_length=100)
    can_edit: Literal[False] = False
    can_redistribute: Literal[False] = False


def json_bytes(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _key(password: str, salt: bytes) -> bytes:
    if not 10 <= len(password) <= 200:
        raise HTTPException(400, "同步密码长度须为 10 至 200 位")
    return hash_secret_raw(password.encode("utf-8"), salt, time_cost=3,
                           memory_cost=65536, parallelism=1, hash_len=32, type=Type.ID)


def _read_zip(raw: bytes, expected: set[str]) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        # Exact names also reject traversal, duplicate names, symlinks and extra files.
        if len(entries) != len(expected) or {entry.filename for entry in entries} != expected:
            raise ValueError("invalid archive entries")
        if sum(entry.file_size for entry in entries) > MAX_BYTES:
            raise ValueError("expanded archive too large")
        result = {}
        for entry in entries:
            if entry.flag_bits & 1 or entry.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                raise ValueError("unsupported compression")
            if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("symlink")
            limit = MAX_BYTES if entry.filename in {"payload.bin", "data/patents.ndjson"} else 256 * 1024
            if entry.file_size > limit:
                raise ValueError("entry too large")
            with archive.open(entry) as stream:
                data = stream.read(limit + 1)
            if len(data) > limit or len(data) != entry.file_size:
                raise ValueError("entry size mismatch")
            result[entry.filename] = data
        return result


def _write_zip(entries: dict[str, bytes], compression=zipfile.ZIP_DEFLATED) -> bytes:
    if sum(map(len, entries.values())) > MAX_BYTES:
        raise HTTPException(413, "同步数据超过 100MB，请缩小范围")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression) as archive:
        for name, value in entries.items():
            archive.writestr(name, value)
    if output.tell() > MAX_BYTES:
        raise HTTPException(413, "同步包超过 100MB，请缩小范围")
    return output.getvalue()


def encode(manifest: dict, permissions: dict, records: list[dict], password: str) -> bytes:
    SnapshotManifest.model_validate(manifest)
    SnapshotPermissions.model_validate(permissions)
    envelope = Envelope(package_id=manifest["package_id"]).model_dump()
    lines = io.BytesIO()
    for record in records:
        line = json_bytes(record)
        if len(line) > MAX_LINE_BYTES or lines.tell() + len(line) + 1 > MAX_BYTES:
            raise HTTPException(413, "记录或同步包过大，请缩小字段范围")
        lines.write(line + b"\n")
    plain = _write_zip({
        "manifest.json": json_bytes(manifest),
        "schema.json": json_bytes({"profile": PROFILE, "fields": manifest["fields"]}),
        "permissions.json": json_bytes(permissions),
        "data/patents.ndjson": lines.getvalue(),
    })
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    encrypted = AESGCM(_key(password, salt)).encrypt(nonce, plain, json_bytes(envelope))
    return _write_zip({"manifest.json": json_bytes(envelope), "payload.bin": salt + nonce + encrypted}, zipfile.ZIP_STORED)


def decode(raw: bytes, password: str) -> tuple[dict, dict, list[dict]]:
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "同步包超过 100MB")
    try:
        outer = _read_zip(raw, {"manifest.json", "payload.bin"})
        envelope = Envelope.model_validate_json(outer["manifest.json"]).model_dump()
        encrypted = outer["payload.bin"]
        if len(encrypted) < 44:
            raise ValueError("truncated payload")
        plain = AESGCM(_key(password, encrypted[:16])).decrypt(encrypted[16:28], encrypted[28:], json_bytes(envelope))
        inner = _read_zip(plain, {"manifest.json", "schema.json", "permissions.json", "data/patents.ndjson"})
        manifest = SnapshotManifest.model_validate_json(inner["manifest.json"]).model_dump()
        permissions = SnapshotPermissions.model_validate_json(inner["permissions.json"]).model_dump()
        if manifest["package_id"] != envelope["package_id"]:
            raise ValueError("package ID mismatch")
        if permissions["fields"] != manifest["fields"] or any(
            name != name.strip().lower() or not name for name in permissions["recipients"]
        ):
            raise ValueError("permission scope mismatch")
        if json.loads(inner["schema.json"]) != {"profile": PROFILE, "fields": manifest["fields"]}:
            raise ValueError("schema mismatch")
        created, expires = datetime.fromisoformat(manifest["created_at"]), datetime.fromisoformat(manifest["expires_at"])
        if created.tzinfo is not None or expires.tzinfo is not None or expires <= created:
            raise ValueError("invalid UTC timestamps")
        records, seen = [], set()
        for line in io.BytesIO(inner["data/patents.ndjson"]):
            if len(line) > MAX_LINE_BYTES + 1 or len(records) >= MAX_RECORDS:
                raise ValueError("record limits exceeded")
            record = SnapshotRecord.model_validate_json(line).model_dump()
            if record["entity_uid"] in seen or set(record["payload"]) != set(manifest["fields"]):
                raise ValueError("duplicate identity or unexpected field")
            seen.add(record["entity_uid"])
            records.append(record)
        if manifest["count"] != len(records):
            raise ValueError("record count mismatch")
        return manifest, permissions, records
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError, ValidationError, InvalidTag,
            zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError, zlib.error) as exc:
        raise HTTPException(400, "同步包密码错误、格式不兼容或内容已损坏") from exc


def file_hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()
