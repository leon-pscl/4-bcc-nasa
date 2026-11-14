# Stage 1: build the frontend
FROM node:22-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npx vite build

# Stage 2: shared Python dependencies (web + pipeline)
FROM python:3.12-slim AS backend-deps
WORKDIR /app
COPY requirements.txt .
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements.txt -r requirements-dev.txt

# Target: web (serve the app). No rasterio: GeoTIFFs are read only by the
# pipeline (add-region / cell_cover build).
FROM backend-deps AS web
COPY firecal/ ./firecal/
COPY app.py ./
COPY config/ ./config/
COPY tests/ ./tests/
COPY sample-data ./sample-data/
COPY frontend/public/mock ./frontend/public/mock/
COPY --from=frontend-build /app/frontend/dist ./frontend/dist/
ENV DATA_RAW=/app/data/raw DATA_PROCESSED=/app/data/processed
EXPOSE 8000
CMD ["python", "-m", "flask", "--app", "app", "run", "--host", "0.0.0.0", "--port", "8000"]

# Target: pipeline (updater / add-region). rasterio + GDAL for reading the
# MCD12Q1 GeoTIFF granules in data/raw/landcover.
FROM backend-deps AS pipeline
# manylinux rasterio wheels bundle GDAL but still link the system expat lib
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir rasterio==1.5.2
COPY firecal/ ./firecal/
COPY app.py ./
COPY config/ ./config/
COPY tests/ ./tests/
COPY sample-data ./sample-data/
ENV DATA_RAW=/app/data/raw DATA_PROCESSED=/app/data/processed
CMD ["python", "-m", "firecal.pipeline", "update", "--all"]
