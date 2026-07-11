# StockOffline web tier — minimal, dependency-light production image.
# The app itself has ZERO third-party deps; only gunicorn (the WSGI server)
# is installed in the image.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    WEB_HOST=0.0.0.0 \
    WEB_PORT=8000

WORKDIR /app/src

# Copy only the source (secrets come from runtime env / secret manager, never baked in)
COPY src/ ./
COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000

# Runs the SAME secure pipeline as the offline tier, behind gunicorn.
CMD ["gunicorn", "web.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4"]
