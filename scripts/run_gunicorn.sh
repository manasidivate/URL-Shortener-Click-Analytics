#!/usr/bin/env sh
set -eu

case "${PORT-}" in
  ''|*[!0-9]*)
    printf '%s\n' 'PORT must be a positive integer.' >&2
    exit 64
    ;;
esac

if [ "$PORT" -le 0 ]; then
  printf '%s\n' 'PORT must be a positive integer.' >&2
  exit 64
fi

exec gunicorn --workers 1 --bind "0.0.0.0:${PORT}" 'app:create_app()'
