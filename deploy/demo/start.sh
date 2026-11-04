#!/bin/bash
# Start the API and page, then serve both on $PORT. Stop everything if any one of them dies.
set -eu

if [ -z "${INTERNAL_API_TOKEN:-}" ]; then
    echo "INTERNAL_API_TOKEN must be set, so the public site doesn't expose /v1/trace/last and /v1/metrics." >&2
    exit 1
fi

uvicorn app.main:app --host 127.0.0.1 --port 8000 &
API_URL=http://127.0.0.1:8000 streamlit run ui/streamlit_app.py \
    --server.address 127.0.0.1 --server.port 8501 --server.headless true \
    --browser.gatherUsageStats false --server.enableCORS false --server.enableXsrfProtection false &
caddy run --config /app/deploy/Caddyfile --adapter caddyfile &

wait -n
exit 1
