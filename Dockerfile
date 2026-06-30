FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MATERIAL_LAB_DATA_DIR=/data

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
COPY docker-entrypoint.sh ./docker-entrypoint.sh
RUN useradd --create-home --uid 1000 materiallab && mkdir -p /data && chown -R materiallab:materiallab /app /data && sed -i 's/\r$//' /app/docker-entrypoint.sh && chmod +x /app/docker-entrypoint.sh
USER materiallab
EXPOSE 8080
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
