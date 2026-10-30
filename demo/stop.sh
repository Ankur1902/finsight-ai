#!/bin/sh
# Stop the demo API and web servers started for recording.
for p in $(pgrep -f "uvicorn demo"); do [ "$p" != "$$" ] && kill "$p" 2>/dev/null; done
for p in $(pgrep -f "next start"); do [ "$p" != "$$" ] && kill "$p" 2>/dev/null; done
# next-server child processes do not match "next start"; free the port directly.
for p in $(ss -ltnp 2>/dev/null | grep -E ':(3000|8000) ' | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | sort -u); do kill "$p" 2>/dev/null; done
exit 0
