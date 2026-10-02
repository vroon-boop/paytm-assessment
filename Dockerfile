FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py init_db.py schema.sql ./
EXPOSE 8000
CMD ["sh", "-c", "python init_db.py && exec gunicorn --bind 0.0.0.0:${PORT} --workers 2 --threads 8 --timeout 120 app:app"]
