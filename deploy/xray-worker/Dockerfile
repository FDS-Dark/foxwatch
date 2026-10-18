# Build context: repository root (docker build -f deploy/xray-worker/Dockerfile .)
FROM python:3.14-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin \
    libgdal-dev \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY deploy/xray-worker/pyproject.toml ./deploy/xray-worker/
RUN pip install --no-cache-dir \
    boto3 geopandas matplotlib numpy pandas pillow pyarrow pyproj rasterio requests scikit-learn scipy shapely

COPY scripts ./scripts
COPY research/xray_bay/scripts/xray_common.py ./research/xray_bay/scripts/xray_common.py
COPY research/xray_bay/phase2_satellite/scripts ./research/xray_bay/phase2_satellite/scripts
COPY research/xray_bay/phase2_satellite/outputs/matched_bins.parquet \
    ./research/xray_bay/phase2_satellite/outputs/matched_bins.parquet
COPY data/xray/green_bay_boundary.geojson ./data/xray/green_bay_boundary.geojson

ENV PYTHONPATH=/app/scripts
ENV XRAY_LIVE_CACHE_DIR=/var/cache/xray-live
ENV XRAY_LIVE_OUTPUT_DIR=/var/lib/xray-live
ENV PYTHONUNBUFFERED=1

VOLUME ["/var/cache/xray-live"]

CMD ["python", "scripts/refresh_xray_live.py", "--watch"]
