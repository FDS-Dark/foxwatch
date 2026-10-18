"""Publish completed X-Ray live snapshots to S3-compatible object storage (Vultr)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urljoin

PREFIX = "live"
LAYER_NAMES = ("prediction", "satellite", "support", "age")
IMMUTABLE_CACHE = "public, max-age=31536000, immutable"
JSON_CACHE = "no-store"


class ObjectStore(Protocol):
    def put_bytes(self, key: str, body: bytes, content_type: str, cache_control: str) -> None: ...


@dataclass(frozen=True)
class PublishConfig:
    endpoint: str
    bucket: str
    access_key: str
    secret_key: str
    public_base_url: str
    region: str = "us-east-1"

    @classmethod
    def from_env(cls) -> PublishConfig | None:
        base = os.getenv("XRAY_LIVE_PUBLIC_BASE_URL", "").strip().rstrip("/")
        bucket = os.getenv("VULTR_S3_BUCKET", "").strip()
        access = os.getenv("VULTR_S3_ACCESS_KEY", "").strip()
        secret = os.getenv("VULTR_S3_SECRET_KEY", "").strip()
        endpoint = os.getenv("VULTR_S3_ENDPOINT", "").strip()
        if not all((base, bucket, access, secret, endpoint)):
            return None
        return cls(
            endpoint=endpoint,
            bucket=bucket,
            access_key=access,
            secret_key=secret,
            public_base_url=base,
            region=os.getenv("VULTR_S3_REGION", "us-east-1").strip() or "us-east-1",
        )


class BotoObjectStore:
    def __init__(self, config: PublishConfig):
        import boto3
        from botocore.config import Config

        self._bucket = config.bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=config.endpoint,
            aws_access_key_id=config.access_key,
            aws_secret_access_key=config.secret_key,
            region_name=config.region,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def put_bytes(self, key: str, body: bytes, content_type: str, cache_control: str) -> None:
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
            CacheControl=cache_control,
            ACL="public-read",
        )


class RecordingObjectStore:
    """Test double that records uploads in order."""

    def __init__(self):
        self.uploads: list[tuple[str, bytes, str, str]] = []

    def put_bytes(self, key: str, body: bytes, content_type: str, cache_control: str) -> None:
        self.uploads.append((key, body, content_type, cache_control))


def public_object_url(public_base: str, key: str) -> str:
    return urljoin(public_base.rstrip("/") + "/", key.lstrip("/"))


def snapshot_prefix(run_id: str) -> str:
    return f"{PREFIX}/{run_id}"


def layer_public_url(public_base: str, run_id: str, layer_id: str) -> str:
    return public_object_url(public_base, f"{snapshot_prefix(run_id)}/{layer_id}.png")


def manifest_with_public_layers(manifest: dict, public_base: str) -> dict:
    updated = dict(manifest)
    layers = []
    for layer in manifest.get("layers", []):
        item = dict(layer)
        layer_id = item.get("id")
        if layer_id in LAYER_NAMES:
            item["url"] = layer_public_url(public_base, manifest["run_id"], layer_id)
        layers.append(item)
    updated["layers"] = layers
    return updated


def fetch_public_json(public_base: str, name: str, timeout: float = 30) -> dict | None:
    import requests

    url = public_object_url(public_base, f"{PREFIX}/{name}")
    try:
        response = requests.get(url, timeout=timeout, headers={"Cache-Control": "no-store"})
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, json.JSONDecodeError):
        return None


class LiveArtifactPublisher:
    def __init__(self, config: PublishConfig, store: ObjectStore | None = None):
        self.config = config
        self.store = store or BotoObjectStore(config)

    def load_previous_manifest(self, local_path: Path) -> dict | None:
        if local_path.is_file():
            return json.loads(local_path.read_text(encoding="utf-8"))
        return fetch_public_json(self.config.public_base_url, "manifest.json")

    def publish_status(self, status: dict) -> None:
        body = (json.dumps(status, indent=2, allow_nan=False) + "\n").encode("utf-8")
        self.store.put_bytes(f"{PREFIX}/status.json", body, "application/json", JSON_CACHE)

    def publish_snapshot(self, run_id: str, dest: Path, manifest: dict) -> None:
        public_manifest = manifest_with_public_layers(manifest, self.config.public_base_url)
        prefix = snapshot_prefix(run_id)
        for layer in LAYER_NAMES:
            path = dest / f"{layer}.png"
            data = path.read_bytes()
            self.store.put_bytes(
                f"{prefix}/{layer}.png",
                data,
                "image/png",
                IMMUTABLE_CACHE,
            )
        samples = (dest / "samples.json.gz").read_bytes()
        self.store.put_bytes(
            f"{prefix}/samples.json.gz",
            samples,
            "application/gzip",
            IMMUTABLE_CACHE,
        )
        run_manifest_body = (json.dumps(public_manifest, indent=2, allow_nan=False) + "\n").encode("utf-8")
        self.store.put_bytes(
            f"{prefix}/manifest.json",
            run_manifest_body,
            "application/json",
            IMMUTABLE_CACHE,
        )
        root_manifest_body = (json.dumps(public_manifest, indent=2, allow_nan=False) + "\n").encode("utf-8")
        self.store.put_bytes(f"{PREFIX}/manifest.json", root_manifest_body, "application/json", JSON_CACHE)

    def public_layer_url(self, run_id: str, layer_id: str) -> str:
        return layer_public_url(self.config.public_base_url, run_id, layer_id)
