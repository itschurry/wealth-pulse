#!/bin/sh
python3 /app/api_server.py &
exec nginx -g "daemon off;"
