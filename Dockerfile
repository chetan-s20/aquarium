# Multi-stage: build the frontend, then serve it from the API (single container).
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ .
RUN VITE_API_BASE="" npm run build

FROM python:3.11-slim
WORKDIR /app/backend
COPY backend/ /app/backend/
COPY --from=frontend-build /app/frontend/dist /app/backend/static
RUN pip install --no-cache-dir --timeout 300 --retries 5 -r requirements.txt
CMD ["sh", "-c", "alembic upgrade head && python scripts/seed.py && uvicorn app.main:app --host 0.0.0.0 --port 8000"]