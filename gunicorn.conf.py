# gunicorn.conf.py
import multiprocessing as mp
import os

# Bind to address and port
bind = os.getenv("BIND", "0.0.0.0:8076")

# Worker class - using Uvicorn worker for ASGI apps
worker_class = "uvicorn.workers.UvicornWorker"

# Number of worker processes
workers = int(os.getenv("WEB_CONCURRENCY", mp.cpu_count() * 2 + 1))

# Thread count per worker
threads = int(os.getenv("THREADS", "1"))

# Parameters for worker processes
timeout = int(os.getenv("TIMEOUT", "120"))
graceful_timeout = int(os.getenv("GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.getenv("KEEPALIVE", "5"))

# If True, the application will be loaded once in the master process and
preload_app = True

# Limit maximum requests per worker to mitigate memory leaks
max_requests = int(os.getenv("MAX_REQUESTS", "1000"))
max_requests_jitter = int(os.getenv("MAX_REQUESTS_JITTER", "100"))

# Whitelisted IPs for X-Forwarded-For header
forwarded_allow_ips = os.getenv("FORWARDED_ALLOW_IPS", "127.0.0.1")

# Logs
accesslog = "-" if os.getenv("ACCESS_LOG", "1") == "1" else None
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info")
capture_output = True
