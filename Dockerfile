FROM python:3.14-slim

# "dev" for local work (tests, ruff), "prod" on the server.
ARG REQUIREMENTS=dev

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libmagic1 libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/ requirements/
RUN pip install --no-cache-dir -r requirements/${REQUIREMENTS}.txt

# The app never runs as root. Uploaded files live in /app/storage, which is
# a volume - creating it here gives the volume the right owner.
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/storage /app/staticfiles \
    && chown app:app /app/storage /app/staticfiles

COPY --chown=app:app . .

USER app
