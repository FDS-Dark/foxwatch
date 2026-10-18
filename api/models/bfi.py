from typing import Optional

from pydantic import BaseModel


class BfiInsightRequest(BaseModel):
    water_temperature_c: Optional[float] = None
    phosphorus_ug_l: Optional[float] = None
    nitrogen_mg_l: Optional[float] = None
    streamflow_cfs: Optional[float] = None
    seasonal_median_streamflow_cfs: Optional[float] = None
    rainfall_7day_in: Optional[float] = None
    solar_radiation_level: Optional[str] = None
    use_live_data: bool = True
    use_gemini: bool = True
