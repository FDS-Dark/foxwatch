import gzip
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
import settings
from services import xray_live


class XrayLiveRemoteTests(unittest.TestCase):
    def setUp(self):
        xray_live._sample_grid.cache_clear()
        self.client = TestClient(main.app)
        self.run_id = "20261018T120000Z-abc12345"
        now = datetime.now(timezone.utc)
        self.manifest = {
            "run_id": self.run_id,
            "acquisition_start": (now - timedelta(days=1)).isoformat().replace("+00:00", "Z"),
            "acquisition_end": now.isoformat().replace("+00:00", "Z"),
            "scenes": [{"index": 1, "id": "scene-a", "acquired_at": now.isoformat().replace("+00:00", "Z"), "url": "https://example.com"}],
            "layers": [{"id": "prediction", "url": f"https://cdn.example.com/live/{self.run_id}/prediction.png"}],
        }
        self.status = {"phase": "ready", "message": "ok", "checked_at": now.isoformat()}
        sample = {
            "width": 1,
            "height": 1,
            "bounds": [[44.5, -88.0], [45.5, -87.0]],
            "values": [1.5],
            "scenes": [1],
            "outside_support": [0],
        }
        self.sample_gz = gzip.compress(json.dumps(sample).encode("utf-8"))

    def tearDown(self):
        xray_live._sample_grid.cache_clear()

    @patch.object(settings, "XRAY_LIVE_PUBLIC_BASE_URL", "https://cdn.example.com/bucket")
    @patch("services.xray_live._fetch_bytes")
    @patch("services.xray_live._fetch_json")
    def test_live_metadata_ready_from_remote(self, fetch_json, fetch_bytes):
        fetch_json.side_effect = [
            self.status,
            self.manifest,
        ]
        response = self.client.get("/api/xray/live")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ready")
        self.assertEqual(body["map"]["run_id"], self.run_id)

    @patch.object(settings, "XRAY_LIVE_PUBLIC_BASE_URL", "https://cdn.example.com/bucket")
    @patch("services.xray_live._fetch_json")
    def test_live_metadata_unavailable_when_manifest_missing(self, fetch_json):
        import httpx

        def side_effect(url):
            if url.endswith("status.json"):
                return self.status
            raise httpx.HTTPError("missing manifest")

        fetch_json.side_effect = side_effect
        with patch("services.xray_live._read_local_json", return_value=None):
            response = self.client.get("/api/xray/live")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "unavailable")

    @patch.object(settings, "XRAY_LIVE_PUBLIC_BASE_URL", "https://cdn.example.com/bucket")
    @patch("services.xray_live._fetch_bytes")
    @patch("services.xray_live._fetch_json")
    def test_live_sample_from_remote(self, fetch_json, fetch_bytes):
        fetch_json.return_value = self.manifest
        fetch_bytes.return_value = self.sample_gz
        response = self.client.get(
            f"/api/xray/live/{self.run_id}/sample",
            params={"lat": 45.0, "lon": -87.5},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "available")
        self.assertEqual(body["value"], 1.5)


if __name__ == "__main__":
    unittest.main()
