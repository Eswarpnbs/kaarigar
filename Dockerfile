FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY requirements.txt .
RUN pip install -r requirements.txt
# ADK + OpenTelemetry at the exact versions tested locally (ADK's declared OTel limit is stricter than needed)
COPY requirements-adk.txt .
RUN pip install --no-deps -r requirements-adk.txt
COPY . .
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
