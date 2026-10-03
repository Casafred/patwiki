"""Bounded and authenticated snapshot envelope, independent of the transport."""
from __future__ import annotations

import hashlib
import io
import base64
import json
import secrets
import zipfile
import zlib
import os
import tempfile
import shutil
from typing import BinaryIO, Iterable
from datetime import datetime
from typing import Literal

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

MAX_BYTES = int(os.getenv("PATWIKI_SYNC_MAX_BYTES", str(100 * 1024 * 1024)))
MAX_RECORDS = int(os.getenv("PATWIKI_SYNC_MAX_RECORDS", "20000"))
MAX_LINE_BYTES = 2 * 1024 * 1024
V3_CHUNK_BYTES = 1024 * 1024
PROFILE = "patent-snapshot-v1"
UID_PATTERN = r"^[a-z]+_[a-f0-9]{32}$"


class WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Envelope(WireModel):
    format: Literal["patwiki.pwshare"] = "patwiki.pwshare"
    format_version: Literal[1, 2, 3] = 1
    profile: Literal["patent-snapshot-v1"] = PROFILE
    package_id: str = Field(pattern=UID_PATTERN)
    encryption: Literal["aes-256-gcm+argon2id"] = "aes-256-gcm+argon2id"
    signer_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    signer_public_key: str | None = None
    signature_algorithm: Literal["ed25519"] | None = None
    payload_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    signature: str | None = None


class SnapshotRecord(WireModel):
    entity_type: Literal["patent", "patent_tombstone"] = "patent"
    operation: Literal["upsert", "delete"] = "upsert"
    entity_uid: str = Field(pattern=UID_PATTERN)
    record_version: int = Field(ge=1)
    origin_node_uid: str = Field(pattern=UID_PATTERN)
    updated_at: str | None = None
    scope: dict = Field(default_factory=dict)
    payload: dict = Field(default_factory=dict)
    base_version: int = Field(default=0, ge=0)
    field_provenance: dict = Field(default_factory=dict)


class SnapshotManifest(WireModel):
    package_id: str = Field(pattern=UID_PATTERN)
    profile: Literal["patent-snapshot-v1"] = PROFILE
    package_type: Literal["snapshot", "department_publication"] = "snapshot"
    created_at: str
    expires_at: str
    created_by: dict
    origin_node_uid: str = Field(pattern=UID_PATTERN)
    fields: list[str] = Field(min_length=1, max_length=100)
    count: int = Field(ge=0, le=MAX_RECORDS)
    databases: list[dict] = Field(max_length=500)
    signature_status: Literal["not_signed", "signed"] = "not_signed"
    signer_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    signer_public_key: str | None = None
    update_requests: list[dict] = Field(default_factory=list, max_length=MAX_RECORDS)
    external_update_results: dict = Field(default_factory=dict)
    export_mode: Literal["full", "delta"] = "full"
    base_package_uid: str | None = Field(default=None, pattern=UID_PATTERN)
    recipient_names: list[str] = Field(default_factory=list, max_length=100)
    selection: dict = Field(default_factory=dict)


class SnapshotPermissions(WireModel):
    access: Literal["viewer"] = "viewer"
    recipients: list[str] = Field(default_factory=list, max_length=100)
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


def encrypt_v3_stream(source, target, password: str) -> None:
    """Encrypt independent chunks so a decoder can authenticate incrementally."""
    salt = secrets.token_bytes(16)
    key = _key(password, salt)
    target.write(salt + V3_CHUNK_BYTES.to_bytes(4, "big"))
    offset = 0
    while True:
        chunk = source.read(V3_CHUNK_BYTES)
        if not chunk:
            break
        nonce = secrets.token_bytes(12)
        encrypted = AESGCM(key).encrypt(nonce, chunk, b"patwiki.pwshare.v3:" + offset.to_bytes(8, "big"))
        target.write(len(encrypted).to_bytes(4, "big") + nonce + encrypted)
        offset += V3_CHUNK_BYTES


def decrypt_v3_stream(source, target, password: str) -> None:
    header = source.read(20)
    if len(header) < 20:
        raise ValueError("truncated v3 payload")
    salt, chunk_size = header[:16], int.from_bytes(header[16:20], "big")
    if chunk_size != V3_CHUNK_BYTES:
        raise ValueError("unsupported v3 chunk size")
    key, offset = _key(password, salt), 0
    while True:
        header = source.read(16)
        if not header:
            break
        if len(header) != 16:
            raise ValueError("truncated v3 chunk")
        size = int.from_bytes(header[:4], "big")
        nonce = header[4:]
        if size < 16 or size > chunk_size + 16:
            raise ValueError("invalid v3 chunk size")
        encrypted = source.read(size)
        if len(encrypted) != size:
            raise ValueError("truncated v3 chunk")
        target.write(AESGCM(key).decrypt(nonce, encrypted, b"patwiki.pwshare.v3:" + offset.to_bytes(8, "big")))
        offset += chunk_size


def _encrypt_v3(plain: bytes, password: str) -> bytes:
    output = io.BytesIO()
    encrypt_v3_stream(io.BytesIO(plain), output, password)
    return output.getvalue()


def _decrypt_v3(payload: bytes, password: str) -> bytes:
    output = io.BytesIO()
    decrypt_v3_stream(io.BytesIO(payload), output, password)
    return output.getvalue()


def encode_to(
    target: BinaryIO,
    manifest: dict,
    permissions: dict,
    records: Iterable[dict],
    password: str,
    signing_private_key: bytes | None = None,
) -> None:
    SnapshotManifest.model_validate(manifest)
    SnapshotPermissions.model_validate(permissions)
    envelope = Envelope(package_id=manifest["package_id"]).model_dump(exclude_none=True)
    lines = tempfile.SpooledTemporaryFile(max_size=4 * 1024 * 1024)
    line_total = 0
    for record in records:
        line = json_bytes(record)
        line_total += len(line) + 1
        if len(line) > MAX_LINE_BYTES or line_total > MAX_BYTES:
            raise HTTPException(413, "记录或同步包过大，请缩小字段范围")
        lines.write(line + b"\n")
    lines.seek(0)
    plain = tempfile.SpooledTemporaryFile(max_size=4 * 1024 * 1024)
    with zipfile.ZipFile(plain, "w", zipfile.ZIP_DEFLATED) as inner:
        inner.writestr("manifest.json", json_bytes(manifest))
        inner.writestr("schema.json", json_bytes({"profile": PROFILE, "fields": manifest["fields"]}))
        inner.writestr("permissions.json", json_bytes(permissions))
        with inner.open("data/patents.ndjson", "w") as member:
            shutil.copyfileobj(lines, member, length=256 * 1024)
    plain.seek(0)
    if signing_private_key is None:
        plain_bytes = plain.read()
        salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
        encrypted = AESGCM(_key(password, salt)).encrypt(nonce, plain_bytes, _aad(envelope))
        with zipfile.ZipFile(target, "w", zipfile.ZIP_STORED) as outer:
            outer.writestr("manifest.json", json_bytes(envelope))
            outer.writestr("payload.bin", salt + nonce + encrypted)
        lines.close()
        plain.close()
        return
    private_key = Ed25519PrivateKey.from_private_bytes(signing_private_key)
    public_key = private_key.public_key().public_bytes_raw()
    envelope.update({
        "format_version": 3,
        "signer_fingerprint": hashlib.sha256(public_key).hexdigest(),
        "signer_public_key": base64.b64encode(public_key).decode("ascii"),
        "signature_algorithm": "ed25519",
    })
    payload = tempfile.SpooledTemporaryFile(max_size=4 * 1024 * 1024)
    digest = hashlib.sha256()
    class HashingWriter:
        def write(self, data):
            digest.update(data)
            return payload.write(data)
    encrypt_v3_stream(plain, HashingWriter(), password)
    envelope["payload_sha256"] = digest.hexdigest()
    envelope["signature"] = base64.b64encode(private_key.sign(_signature_payload(envelope))).decode("ascii")
    payload.seek(0)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_STORED) as outer:
        outer.writestr("manifest.json", json_bytes(envelope))
        with outer.open("payload.bin", "w") as member:
            shutil.copyfileobj(payload, member, length=256 * 1024)
    lines.close()
    plain.close()
    payload.close()


def encode(manifest: dict, permissions: dict, records: Iterable[dict], password: str,
           signing_private_key: bytes | None = None) -> bytes:
    target = io.BytesIO()
    encode_to(target, manifest, permissions, records, password, signing_private_key)
    if target.tell() > MAX_BYTES:
        raise HTTPException(413, "同步包超过 100MB，请缩小范围")
    return target.getvalue()


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
        if len(encrypted) < (20 if envelope.get("format_version") == 3 else 44):
            raise ValueError("truncated payload")
        signature_status = "not_signed"
        if envelope["format_version"] in {2, 3}:
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
        if envelope["format_version"] == 3:
            plain = _decrypt_v3(encrypted, password)
        else:
            plain = AESGCM(_key(password, encrypted[:16])).decrypt(encrypted[16:28], encrypted[28:], _aad(envelope))
        inner = _read_zip(plain, {"manifest.json", "schema.json", "permissions.json", "data/patents.ndjson"})
        manifest = SnapshotManifest.model_validate_json(inner["manifest.json"]).model_dump()
        permissions = SnapshotPermissions.model_validate_json(inner["permissions.json"]).model_dump()
        if manifest["package_id"] != envelope["package_id"]:
            raise ValueError("package ID mismatch")
        if envelope["format_version"] in {2, 3} and manifest["signature_status"] != "signed":
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
            if record["entity_uid"] in seen or (record["operation"] == "upsert" and set(record["payload"]) != set(manifest["fields"] )) or (record["operation"] == "delete" and record["entity_type"] != "patent_tombstone"):
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


def decode_stream(source: BinaryIO, password: str, trusted_public_keys: dict[str, bytes] | None = None,
                  record_handler=None, collect_records: bool = False):
    """Validate and process records one line at a time for v3 packages."""
    payload_copy = plain = None
    try:
        with zipfile.ZipFile(source) as outer_zip:
            entries = outer_zip.infolist()
            names = [entry.filename for entry in entries]
            if len(names) != 2 or set(names) != {"manifest.json", "payload.bin"} or len(set(names)) != 2:
                raise ValueError("unexpected archive entries")
            for entry in entries:
                if entry.flag_bits & 1 or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("invalid outer entry")
            if outer_zip.getinfo("manifest.json").file_size > 256 * 1024:
                raise ValueError("envelope too large")
            outer_manifest = outer_zip.read("manifest.json")
            envelope = Envelope.model_validate_json(outer_manifest).model_dump(exclude_none=True)
            payload_info = outer_zip.getinfo("payload.bin")
            if payload_info.file_size > MAX_BYTES or payload_info.compress_type != zipfile.ZIP_STORED:
                raise ValueError("invalid payload entry")
            if envelope["format_version"] != 3:
                source.seek(0)
                manifest, permissions, records = decode(source.read(MAX_BYTES + 1), password, trusted_public_keys)
                if record_handler:
                    for record in records:
                        record_handler(record)
                return manifest, permissions, records if collect_records else []
            with outer_zip.open("payload.bin") as encrypted:
                digest = hashlib.sha256()
                class HashReader:
                    def read(self, size=-1):
                        data = encrypted.read(size)
                        digest.update(data)
                        return data
                payload_copy = tempfile.SpooledTemporaryFile(max_size=4 * 1024 * 1024)
                shutil.copyfileobj(HashReader(), payload_copy, 256 * 1024)
            if payload_copy.tell() > MAX_BYTES:
                raise ValueError("payload too large")
            if digest.hexdigest() != envelope.get("payload_sha256"):
                raise ValueError("signed payload hash mismatch")
            required = ("signer_fingerprint", "signer_public_key", "signature_algorithm", "signature")
            if any(not envelope.get(key) for key in required):
                raise ValueError("missing signature fields")
            public_key = base64.b64decode(envelope["signer_public_key"], validate=True)
            signature = base64.b64decode(envelope["signature"], validate=True)
            if len(public_key) != 32 or hashlib.sha256(public_key).hexdigest() != envelope["signer_fingerprint"]:
                raise ValueError("invalid signer key")
            Ed25519PublicKey.from_public_bytes(public_key).verify(signature, _signature_payload(envelope))
            trusted = (trusted_public_keys or {}).get(envelope["signer_fingerprint"])
            if trusted is not None and trusted != public_key:
                raise ValueError("trusted key mismatch")
            payload_copy.seek(0)
            plain = tempfile.SpooledTemporaryFile(max_size=4 * 1024 * 1024)
            decrypt_v3_stream(payload_copy, plain, password)
            if plain.tell() > MAX_BYTES:
                raise ValueError("plaintext too large")
            plain.seek(0)
            with zipfile.ZipFile(plain) as inner_zip:
                expected = {"manifest.json", "schema.json", "permissions.json", "data/patents.ndjson"}
                infos = inner_zip.infolist()
                if len(infos) != len(expected) or {item.filename for item in infos} != expected:
                    raise ValueError("invalid inner archive")
                if sum(item.file_size for item in infos) > MAX_BYTES:
                    raise ValueError("expanded archive too large")
                for item in infos:
                    if item.filename != "data/patents.ndjson" and item.file_size > 256 * 1024:
                        raise ValueError("metadata too large")
                    if item.flag_bits & 1 or item.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                        raise ValueError("unsupported inner compression")
                    if (item.external_attr >> 16) & 0o170000 == 0o120000:
                        raise ValueError("inner symlink")
                manifest = SnapshotManifest.model_validate_json(inner_zip.read("manifest.json")).model_dump()
                permissions = SnapshotPermissions.model_validate_json(inner_zip.read("permissions.json")).model_dump()
                if manifest["package_id"] != envelope["package_id"] or manifest["signature_status"] != "signed":
                    raise ValueError("package identity or signature mismatch")
                if json.loads(inner_zip.read("schema.json")) != {"profile": PROFILE, "fields": manifest["fields"]}:
                    raise ValueError("schema mismatch")
                if permissions["fields"] != manifest["fields"]:
                    raise ValueError("permission mismatch")
                created, expires = datetime.fromisoformat(manifest["created_at"]), datetime.fromisoformat(manifest["expires_at"])
                if created.tzinfo is not None or expires.tzinfo is not None or expires <= created:
                    raise ValueError("invalid timestamps")
                count, seen, records = 0, set(), []
                with inner_zip.open("data/patents.ndjson") as lines:
                    while True:
                        line = lines.readline(MAX_LINE_BYTES + 2)
                        if not line:
                            break
                        count += 1
                        if count > MAX_RECORDS or len(line) > MAX_LINE_BYTES + 1:
                            raise ValueError("record limits exceeded")
                        record = SnapshotRecord.model_validate_json(line).model_dump()
                        if record["entity_uid"] in seen:
                            raise ValueError("duplicate record identity")
                        if record["operation"] == "upsert" and set(record["payload"]) != set(manifest["fields"]):
                            raise ValueError("unexpected record fields")
                        if record["operation"] == "delete" and record["entity_type"] != "patent_tombstone":
                            raise ValueError("invalid tombstone")
                        seen.add(record["entity_uid"])
                        if record_handler:
                            record_handler(record)
                        if collect_records:
                            records.append(record)
                if count != manifest["count"]:
                    raise ValueError("record count mismatch")
            manifest["signature_status"] = "trusted" if trusted is not None else "signed_untrusted"
            manifest["signer_fingerprint"] = envelope["signer_fingerprint"]
            manifest["signer_public_key"] = envelope["signer_public_key"]
            return manifest, permissions, records
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError, ValidationError,
            InvalidSignature, InvalidTag, zipfile.BadZipFile, RuntimeError, EOFError, zlib.error) as exc:
        raise HTTPException(400, "同步包密码错误、格式不兼容或内容已损坏") from exc
    finally:
        if payload_copy is not None:
            payload_copy.close()
        if plain is not None:
            plain.close()


def file_hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()
