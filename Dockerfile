FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    WEBSTALKER_DATA_DIR=/data \
    WEBSTALKER_BIND_HOST=0.0.0.0 \
    WEBSTALKER_BIND_PORT=8000

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        build-essential \
        libxml2-dev \
        libxslt1-dev \
        ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY webstalker ./webstalker

VOLUME ["/data"]

EXPOSE 8000

CMD ["uvicorn", "webstalker.main:app", "--host", "0.0.0.0", "--port", "8000"]
