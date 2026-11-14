FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libsndfile1 libglib2.0-0 ca-certificates \
    && rm -rf /var/lib/apt/lists/* && useradd --uid 10001 --create-home app
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=app:app server.py coordinator.py providers.py voice.py transit_speech.py memory.py obstacles.py ./
COPY --chown=app:app static/ static/
RUN mkdir /data && chown app:app /data
ENV HOST=0.0.0.0 PORT=8765 BACKEND_DATA_DIR=/data PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 XDG_CACHE_HOME=/tmp/cache
USER app
EXPOSE 8765
CMD ["python", "server.py"]
