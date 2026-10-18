import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import main
import settings
from dependencies import get_ingestion_service


class IngestionAdminTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.mock_ingestion = MagicMock()
        self.mock_ingestion.collector.settings.database_url = "postgresql://example"
        self.mock_ingestion.poll.return_value = {"observations_processed": 0}

        def override():
            return self.mock_ingestion

        main.app.dependency_overrides[get_ingestion_service] = override

    def tearDown(self):
        main.app.dependency_overrides.clear()

    @patch.object(settings, "INGESTION_ADMIN_TOKEN", "secret-token")
    def test_poll_requires_token_when_configured(self):
        response = self.client.post("/ingestion/poll")
        self.assertEqual(response.status_code, 401)

        response = self.client.post(
            "/ingestion/poll",
            headers={"X-Ingestion-Token": "secret-token"},
        )
        self.assertEqual(response.status_code, 200)

    @patch.object(settings, "INGESTION_ADMIN_TOKEN", "")
    def test_poll_open_when_token_unset(self):
        response = self.client.post("/ingestion/poll")
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
