#!/bin/sh
cd "$(dirname "$0")/../frontend"
FINSIGHT_API_URL=http://127.0.0.1:8000 exec npx next start -p 3000
