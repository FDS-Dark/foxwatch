import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pandas as pd
from fastapi.testclient import TestClient
from sqlalchemy.exc import ProgrammingError

from services.usgs_client import fetch_features, observation_row
from services.usgs_ingestion import Collector, Settings
from main import app, collect_forever


def feature(code="00010", value="15.4"):
    return {"properties": {
        "monitoring_location_id": "USGS-040851385",
        "time_series_id": "temperature-series",
        "parameter_code": code,
        "time": "2026-10-17T23:00:00Z",
        "value": value, "unit_of_measure": "degC",
        "approval_status": "Provisional", "qualifier": None,
    }}


class ParsingTests(unittest.TestCase):
    def test_missing_values_and_parameter_filter(self):
        for value in (None, "", "Ice", "NaN", "Infinity"):
            self.assertIsNone(observation_row(feature(value=value), "USGS-040851385")[4])
        self.assertEqual(observation_row(feature(value="0"), "USGS-040851385")[4], 0)
        self.assertIsNone(observation_row(feature("00065"), "USGS-040851385"))
        self.assertIsNone(observation_row(feature(), "USGS-other"))
        self.assertEqual(observation_row(feature(), "USGS-040851385")[0].tzinfo, timezone.utc)

    def test_pagination_preserves_next_query(self):
        calls = []

        def respond(request):
            calls.append(request)
            if "offset" in request.url.params:
                return httpx.Response(200, json={"type": "FeatureCollection", "features": [feature(value="16")]})
            self.assertEqual(request.url.params["monitoring_location_id"], "USGS-040851385")
            return httpx.Response(200, json={"type": "FeatureCollection", "features": [feature()],
                "links": [{"rel": "next", "href": "?offset=1&monitoring_location_id=USGS-040851385&f=json"}]})

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            rows = list(fetch_features(client, "continuous", "USGS-040851385"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(calls), 2)

    def test_rejects_external_pagination_and_http_failure(self):
        for response in (
            httpx.Response(200, json={"type": "FeatureCollection", "features": [],
                "links": [{"rel": "next", "href": "https://example.com/steal-key"}]}),
            httpx.Response(429),
        ):
            with httpx.Client(transport=httpx.MockTransport(lambda request: response)) as client:
                with self.assertRaises((ValueError, httpx.HTTPStatusError)):
                    list(fetch_features(client, "continuous", "USGS-040851385"))


class TransactionTests(unittest.TestCase):
    def connection(self, checkpoint=None):
        connection = MagicMock()
        cursor = connection.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [(True,), checkpoint]
        return connection, cursor

    def test_checkpoint_and_observations_share_transaction(self):
        collector = Collector(Settings(database_url="test"))
        checkpoint = datetime.now(timezone.utc) - timedelta(days=3)
        connection, cursor = self.connection((checkpoint,))
        with patch("services.usgs_ingestion.psycopg.connect", return_value=connection), \
             patch("services.usgs_ingestion.fetch_features", return_value=iter([feature()])) as fetch:
            result = collector.poll()
        self.assertTrue(result["catching_up"])
        self.assertEqual(fetch.call_args.args[3], checkpoint - timedelta(hours=6))
        self.assertEqual(fetch.call_args.args[4], checkpoint + timedelta(days=1))
        self.assertEqual(result["observations_processed"], 1)
        self.assertIn("ON CONFLICT", cursor.executemany.call_args.args[0])
        self.assertIn("INSERT INTO usgs_ingestion_checkpoints", cursor.execute.call_args.args[0])
        self.assertEqual(connection.__exit__.call_args.args, (None, None, None))
        self.assertIsNotNone(collector.status["last_success"])

    def test_failed_fetch_does_not_advance_checkpoint(self):
        collector = Collector(Settings(database_url="test"))
        connection, cursor = self.connection()
        with patch("services.usgs_ingestion.psycopg.connect", return_value=connection), \
             patch("services.usgs_ingestion.fetch_features", side_effect=ValueError("secret")):
            with self.assertRaises(ValueError):
                collector.poll()
        cursor.executemany.assert_not_called()
        self.assertFalse(any("INSERT INTO usgs_ingestion_checkpoints" in c.args[0]
                             for c in cursor.execute.call_args_list))
        self.assertIs(connection.__exit__.call_args.args[0], ValueError)
        self.assertEqual(collector.status["last_error"], "ValueError")
        self.assertIsNone(collector.status["last_success"])
        self.assertFalse(collector.status["running"])

    def test_other_worker_skips_cycle(self):
        connection, cursor = self.connection()
        cursor.fetchone.side_effect = [(False,)]
        with patch("services.usgs_ingestion.psycopg.connect", return_value=connection):
            result = Collector(Settings(database_url="test")).poll()
        self.assertIn("skipped", result)
        self.assertEqual(cursor.execute.call_count, 1)


class EndpointTests(unittest.TestCase):
    def _observations_frame(self):
        return pd.DataFrame([{
            "parameter_code": "00010", "time_series_id": "series",
            "observed_at": datetime(2026, 10, 17, tzinfo=timezone.utc),
            "value": None, "unit": "degC", "approval_status": "Provisional",
            "qualifier": "Ice", "ingested_at": datetime.now(timezone.utc),
        }])

    def test_stored_readings_use_database_and_preserve_missing_values(self):
        query_mock = AsyncMock(return_value=self._observations_frame())
        with patch("settings.resolved_database_url", return_value="postgresql://127.0.0.1:5432/foxwatch"), \
             patch("settings.IngestionSettings.from_env", return_value=Settings(database_url="postgresql://127.0.0.1:5432/foxwatch", enabled=False)), \
             patch("databridge.postgres_databridge.PostgresDatabridge.execute_query", query_mock), \
             patch("services.usgs_ingestion.fetch_features") as fetch, TestClient(app) as client:
            response = client.get("/api/observations/latest")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["source"], "tiger_data")
        self.assertIsNone(body["readings"][0]["value"])
        self.assertEqual(body["readings"][0]["qualifier"], "Ice")
        self.assertIn("00671", body["missing_parameters"])
        self.assertNotIn("00010", body["missing_parameters"])
        self.assertIn("observed_at DESC", query_mock.call_args.args[0])
        params = query_mock.call_args.args[1]
        self.assertEqual(params["station_id"], "USGS-040851385")
        fetch.assert_not_called()

    def test_stored_readings_empty_database(self):
        with patch("settings.resolved_database_url", return_value="postgresql://127.0.0.1:5432/foxwatch"), \
             patch("settings.IngestionSettings.from_env", return_value=Settings(database_url="postgresql://127.0.0.1:5432/foxwatch", enabled=False)), \
             patch("databridge.postgres_databridge.PostgresDatabridge.execute_query", AsyncMock(return_value=pd.DataFrame())), \
             TestClient(app) as client:
            response = client.get("/api/observations/latest")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["readings"], [])
        self.assertEqual(len(response.json()["missing_parameters"]), 11)

    def test_database_failure_never_falls_back_to_usgs(self):
        missing = ProgrammingError("stmt", {}, type("Orig", (), {"sqlstate": "42P01"})())
        runtime = RuntimeError("secret connection string")
        for failure, status in ((missing, 503), (runtime, 502)):
            with patch("settings.resolved_database_url", return_value="postgresql://127.0.0.1:5432/foxwatch"), \
                 patch("settings.IngestionSettings.from_env", return_value=Settings(database_url="postgresql://127.0.0.1:5432/foxwatch", enabled=False)), \
                 patch("databridge.postgres_databridge.PostgresDatabridge.execute_query", AsyncMock(side_effect=failure)), \
                 patch("services.usgs_ingestion.fetch_features") as fetch, TestClient(app) as client:
                response = client.get("/api/observations/latest")
            self.assertEqual(response.status_code, status)
            self.assertNotIn("secret", response.text)
            fetch.assert_not_called()

    def test_unconfigured_status_and_manual_poll(self):
        with patch("settings.IngestionSettings.from_env", return_value=Settings()), TestClient(app) as client:
            self.assertFalse(client.get("/ingestion/status").json()["configured"])
            self.assertEqual(client.post("/ingestion/poll").status_code, 503)
            self.assertEqual(client.get("/api/observations/latest").status_code, 503)

    def test_live_preview_lists_missing_codes(self):
        with patch("settings.IngestionSettings.from_env", return_value=Settings()), \
             patch("services.usgs_ingestion.fetch_features", return_value=iter([feature()])), \
             TestClient(app) as client:
            response = client.get("/usgs/latest")
        self.assertEqual(response.status_code, 200)
        self.assertIn("00671", response.json()["missing_parameters"])
        self.assertNotIn("00010", response.json()["missing_parameters"])


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_retries_after_failure_and_stops(self):
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        collector = MagicMock()
        collector.settings.poll_seconds = 0.001

        def poll():
            if collector.poll.call_count == 1:
                raise ValueError("temporary failure")
            loop.call_soon_threadsafe(stop.set)

        collector.poll.side_effect = poll
        await asyncio.wait_for(collect_forever(collector, stop), timeout=2)
        self.assertEqual(collector.poll.call_count, 2)


if __name__ == "__main__":
    unittest.main()
