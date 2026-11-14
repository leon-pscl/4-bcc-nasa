# Stage 1: build the frontend
FROM node:22-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python runtime (no Node, no node_modules)
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY firecal/ ./firecal/
COPY app.py ./
COPY config/ ./config/
COPY --from=frontend-build /app/frontend/dist ./frontend/dist/
ENV DATA_RAW=/app/data/raw DATA_PROCESSED=/app/data/processed
EXPOSE 8000
CMD ["python", "-m", "flask", "--app", "app", "run", "--host", "0.0.0.0", "--port", "8000"]
