# Build stage: compilers are needed only to build wheels, never at runtime.
FROM python:3.14-slim AS build

# "dev" for local work (tests, ruff), "prod" on the server.
ARG REQUIREMENTS=dev

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/ /requirements/
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r /requirements/${REQUIREMENTS}.txt


# Runtime stage: only what the app needs to run.
FROM python:3.14-slim

ARG REQUIREMENTS=dev

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/ requirements/
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels \
        -r requirements/${REQUIREMENTS}.txt \
    && rm -rf /wheels

# The app never runs as root. Uploaded files live in /app/storage, which is
# a volume - creating it here gives the volume the right owner.
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/storage /app/staticfiles \
    && chown app:app /app/storage /app/staticfiles

COPY --chown=app:app . .

USER app
