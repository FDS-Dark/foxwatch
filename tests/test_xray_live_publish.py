"""Unit tests for X-Ray live object-storage publication."""
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from xray_live_publish import (  # noqa: E402
    LiveArtifactPublisher,
    PublishConfig,
    RecordingObjectStore,
    manifest_with_public_layers,
)


def test_manifest_rewrites_layer_urls():
    manifest = {
        "run_id": "20261018T120000Z-abc12345",
        "layers": [
            {"id": "prediction", "url": "/api/xray/live/old/prediction", "bounds": [[0, 0], [1, 1]]},
            {"id": "satellite", "url": "/api/xray/live/old/satellite"},
        ],
    }
    out = manifest_with_public_layers(manifest, "https://objects.example.com/bucket")
    assert out["layers"][0]["url"] == (
        "https://objects.example.com/bucket/live/20261018T120000Z-abc12345/prediction.png"
    )
    assert out["layers"][1]["url"].endswith("/satellite.png")


def test_publish_snapshot_upload_order_and_headers(tmp_path):
    run_id = "20261018T120000Z-deadbeef"
    dest = tmp_path / run_id
    dest.mkdir()
    for name in ("prediction", "satellite", "support", "age"):
        (dest / f"{name}.png").write_bytes(b"PNG")
    sample = {"width": 1, "height": 1, "values": [1.0], "scenes": [1], "outside_support": [0], "bounds": [[0, 0], [1, 1]]}
    with gzip.open(dest / "samples.json.gz", "wt") as stream:
        json.dump(sample, stream)
    manifest = {"run_id": run_id, "layers": [{"id": "prediction", "url": "/local"}]}
    store = RecordingObjectStore()
    config = PublishConfig(
        endpoint="https://s3.example.com",
        bucket="foxwatch",
        access_key="k",
        secret_key="s",
        public_base_url="https://cdn.example.com/foxwatch",
    )
    publisher = LiveArtifactPublisher(config, store=store)
    publisher.publish_snapshot(run_id, dest, manifest)
    keys = [item[0] for item in store.uploads]
    assert keys[-1] == "live/manifest.json"
    assert keys[-2] == f"live/{run_id}/manifest.json"
    for layer in ("prediction", "satellite", "support", "age"):
        assert f"live/{run_id}/{layer}.png" in keys
    png_upload = next(u for u in store.uploads if u[0].endswith("prediction.png"))
    assert png_upload[2] == "image/png"
    assert "immutable" in png_upload[3]
    status_body = json.dumps({"phase": "ready"}, indent=2) + "\n"
    publisher.publish_status(json.loads(status_body))
    status_upload = store.uploads[-1]
    assert status_upload[0] == "live/status.json"
    assert status_upload[3] == "no-store"
