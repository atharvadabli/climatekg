FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libexpat1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY climatekg ./climatekg
COPY baselines ./baselines
COPY config ./config
COPY prompts ./prompts
COPY webapp ./webapp
RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install ".[baselines]"

RUN useradd --create-home --uid 10001 --gid 0 climatekg \
    && chown -R climatekg:0 /app
USER climatekg

EXPOSE 8780
CMD ["python", "-m", "webapp.server", "--host", "0.0.0.0", "--port", "8780"]
