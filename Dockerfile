FROM python:3.12.8-slim-bookworm AS base
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
COPY requirements.txt requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt && pip check

FROM base AS runner
COPY . .
CMD ["python", "cli.py", "--help"]

FROM base AS dashboard
COPY demo/requirements.lock.txt /tmp/dashboard-requirements.lock.txt
RUN pip install --no-cache-dir -r /tmp/dashboard-requirements.lock.txt && pip check
COPY . .
ENV PYTHONPATH=/app
CMD ["streamlit", "run", "demo/app.py", "--server.address=0.0.0.0", "--server.headless=true"]
