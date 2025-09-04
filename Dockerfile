FROM python:3.10-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kod
COPY src/ ./src

ENV PYTHONPATH=/app/src