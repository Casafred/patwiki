"""Bounded and authenticated snapshot envelope, independent of the transport."""
from __future__ import annotations

import hashlib
import io
import base64
import json
import secrets
import zipfile
import zlib
from datetime import datetime
from typing import Literal

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
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
    format_version: Literal[1, 2] = 1
    profile: Literal["patent-snapshot-v1"] = PROFILE
    package_id: str = Field(pattern=UID_PATTERN)
    encryption: Literal["aes-256-gcm+argon2id"] = "aes-256-gcm+argon2id"
    signer_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    signer_public_key: str | None = None
    signature_algorithm: Literal["ed25519"] | None = None
    payload_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    signature: str | None = None


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
    signature_status: Literal["not_signed", "signed"] = "not_signed"


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


def _aad(envelope: dict) -> bytes:
    return json_bytes({key: envelope[key] for key in ("format", "format_version", "profile", "package_id", "encryption")})


def _signature_payload(envelope: dict) -> bytes:
    return json_bytes({key: value for key, value in envelope.items() if key != "signature"})


def encode(
    manifest: dict,
    permissions: dict,
    records: list[dict],
    password: str,
    signing_private_key: bytes | None = None,
) -> bytes:
    SnapshotManifest.model_validate(manifest)
    SnapshotPermissions.model_validate(permissions)
    envelope = Envelope(package_id=manifest["package_id"]).model_dump(exclude_none=True)
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
    if signing_private_key is None:
        encrypted = AESGCM(_key(password, salt)).encrypt(nonce, plain, _aad(envelope))
        return _write_zip({"manifest.json": json_bytes(envelope), "payload.bin": salt + nonce + encrypted}, zipfile.ZIP_STORED)

    private_key = Ed25519PrivateKey.from_private_bytes(signing_private_key)
    public_key = private_key.public_key().public_bytes_raw()
    envelope.update({
        "format_version": 2,
        "signer_fingerprint": hashlib.sha256(public_key).hexdigest(),
        "signer_public_key": base64.b64encode(public_key).decode("ascii"),
        "signature_algorithm": "ed25519",
    })
    payload = salt + nonce + AESGCM(_key(password, salt)).encrypt(nonce, plain, _aad(envelope))
    envelope["payload_sha256"] = hashlib.sha256(payload).hexdigest()
    envelope["signature"] = base64.b64encode(private_key.sign(_signature_payload(envelope))).decode("ascii")
    return _write_zip({"manifest.json": json_bytes(envelope), "payload.bin": payload}, zipfile.ZIP_STORED)


def decode(
    raw: bytes,
    password: str,
    trusted_public_keys: dict[str, bytes] | None = None,
) -> tuple[dict, dict, list[dict]]:
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "同步包超过 100MB")
    try:
        outer = _read_zip(raw, {"manifest.json", "payload.bin"})
        envelope = Envelope.model_validate_json(outer["manifest.json"]).model_dump(exclude_none=True)
        encrypted = outer["payload.bin"]
        if len(encrypted) < 44:
            raise ValueError("truncated payload")
        signature_status = "not_signed"
        if envelope["format_version"] == 2:
            required = ("signer_fingerprint", "signer_public_key", "signature_algorithm", "payload_sha256", "signature")
            if any(not envelope.get(key) for key in required):
                raise ValueError("missing signature fields")
            public_key = base64.b64decode(envelope["signer_public_key"], validate=True)
            signature = base64.b64decode(envelope["signature"], validate=True)
            if len(public_key) != 32 or len(signature) != 64:
                raise ValueError("invalid signature key size")
            if hashlib.sha256(public_key).hexdigest() != envelope["signer_fingerprint"]:
                raise ValueError("signer fingerprint mismatch")
            if hashlib.sha256(encrypted).hexdigest() != envelope["payload_sha256"]:
                raise ValueError("signed payload hash mismatch")
            Ed25519PublicKey.from_public_bytes(public_key).verify(signature, _signature_payload(envelope))
            trusted = (trusted_public_keys or {}).get(envelope["signer_fingerprint"])
            if trusted is not None and trusted != public_key:
                raise ValueError("trusted key mismatch")
            signature_status = "trusted" if trusted is not None else "signed_untrusted"
        elif any(envelope.get(key) for key in ("signer_fingerprint", "signer_public_key", "signature_algorithm", "payload_sha256", "signature")):
            raise ValueError("legacy envelope contains signature fields")
        plain = AESGCM(_key(password, encrypted[:16])).decrypt(encrypted[16:28], encrypted[28:], _aad(envelope))
        inner = _read_zip(plain, {"manifest.json", "schema.json", "permissions.json", "data/patents.ndjson"})
        manifest = SnapshotManifest.model_validate_json(inner["manifest.json"]).model_dump()
        permissions = SnapshotPermissions.model_validate_json(inner["permissions.json"]).model_dump()
        if manifest["package_id"] != envelope["package_id"]:
            raise ValueError("package ID mismatch")
        if envelope["format_version"] == 2 and manifest["signature_status"] != "signed":
            raise ValueError("signed envelope has unsigned manifest")
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
        manifest["signature_status"] = signature_status
        manifest["signer_fingerprint"] = envelope.get("signer_fingerprint")
        manifest["signer_public_key"] = envelope.get("signer_public_key")
        return manifest, permissions, records
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError, ValidationError,
            InvalidSignature, InvalidTag, zipfile.BadZipFile, RuntimeError,
            NotImplementedError, EOFError, zlib.error) as exc:
        raise HTTPException(400, "同步包密码错误、格式不兼容或内容已损坏") from exc


def file_hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()
