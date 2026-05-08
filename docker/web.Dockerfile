FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings.local

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libldap2-dev \
    libsasl2-dev \
    && rm -rf /var/lib/apt/lists/*

 # Create app user before copying files
RUN useradd --create-home --shell /bin/bash app

WORKDIR /app

# Ensure app user has ownership of /app before copying
RUN chown -R app:app /app

COPY --chown=app:app requirements/ /app/requirements/
RUN pip install -r requirements/dev.txt

COPY --chown=app:app . /app/

# Ensure staticfiles and media directories exist with proper permissions
RUN mkdir -p /app/staticfiles /app/media && chown -R app:app /app/staticfiles /app/media

USER app

EXPOSE 8000

CMD ["/usr/local/bin/python", "-m", "gunicorn", "config.wsgi:application", "-w", "4", "-b", "0.0.0.0:8000", "--access-logfile", "-", "--error-logfile", "-"]
