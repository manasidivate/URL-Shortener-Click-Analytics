#!/usr/bin/env sh
set -eu

python init_db.py
exec supervisord -n -c supervisord.conf
