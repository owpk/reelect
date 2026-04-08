FROM node:20-slim AS frontend
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY api/ ./api/
COPY --from=frontend /frontend/dist ./static

# saved_videos is mounted as a volume at runtime
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
