from __future__ import annotations

from typing import Any

from services.ml.logistic_regression_v2 import FEATURE_PARAMETERS, predict_readings
from services.ml_review import active_model_path_for_inference
from services.observations import ObservationsService


class PredictionsService:
    def __init__(self, observations: ObservationsService):
        self.observations = observations

    async def latest(self) -> dict[str, Any]:
        readings = await self.observations.prediction_readings(
            list(FEATURE_PARAMETERS.values())
        )
        result = predict_readings(readings, model_path=active_model_path_for_inference())
        return {
            "source": "tiger_data",
            "station_id": self.observations.station_id,
            **result,
        }
