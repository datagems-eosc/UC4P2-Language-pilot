FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY src /app/src
COPY data /app/data

ENV PYTHONPATH=/app
ENV QDMR_BACKEND=dspy
ENV QDMR_MODEL_NAME_OR_PATH=""
ENV PORT=8080

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "8080"]
