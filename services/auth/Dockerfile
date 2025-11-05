FROM python:3.11-slim

WORKDIR /app

# curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

# deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# app code
COPY app ./app

EXPOSE 8000
# set PYTHONPATH just in case
ENV PYTHONPATH=/app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
