# ---- Modis-VIIRS hot spot dashboard -------------------------------------
# Build:  docker build -t modis-viirs .
# Run:    docker run --rm -p 8000:8000 modis-viirs   ->  http://127.0.0.1:8000
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first so this layer stays cached while you edit the code.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Application code.
COPY compare.py app.py ./
COPY templates ./templates
COPY static ./static
COPY sample-data ./sample-data

# Where the analysis writes combined.csv / calendar.csv / calendar.png,
# and where uploaded CSVs are kept.
RUN mkdir -p /app/outputs /app/uploads

EXPOSE 8000

# gunicorn instead of the Flask dev server; --threads lets the browser fetch
# the report and the CSV downloads at the same time.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--timeout", "120", "--access-logfile", "-", "app:app"]
