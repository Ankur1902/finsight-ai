#!/bin/sh
cd "$(dirname "$0")/.."
FINSIGHT_RETRIEVAL_MODE=lexical exec python -m uvicorn demo.demo_server:app --host 127.0.0.1 --port 8000
