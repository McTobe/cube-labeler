#!/bin/sh
# Starts the Google Drive sign-in helper (web/drive_auth.py) before nginx, and starts it
# again if it ever stops. The official nginx image runs every script in /docker-entrypoint.d/.
(
  while true; do
    python3 /opt/cube-labeler/drive_auth.py
    echo "drive-auth: stopped, starting again in 5 s" >&2
    sleep 5
  done
) &
