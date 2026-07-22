FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 1000 botuser

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot/ bot/
COPY scripts/ scripts/
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER botuser
ENTRYPOINT ["/entrypoint.sh"]
