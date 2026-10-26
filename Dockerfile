# Cube Labeler web app: builds web/dist and serves it with nginx on port 80.
# TLS is left to the reverse proxy in front (Web Serial needs the page on https).
#
#   docker build -t cube-labeler-web .
#   docker run -d -p 8080:80 cube-labeler-web
#
# Set GOOGLE_CLIENT_SECRET (and PUBLIC_URL) to keep people signed in to Google Drive; see
# docs/google-sign-in.md. Without them the page signs in to Drive for an hour at a time.
#
# GitHub Actions publishes it as ghcr.io/mctobe/cube-labeler-web (see web-image.yml).

# The build stage only produces static files, so it runs natively even for other platforms
FROM --platform=$BUILDPLATFORM python:3.12-slim AS build
WORKDIR /src
COPY constraints.txt .
RUN pip install --no-cache-dir pillow -c constraints.txt
COPY assets/icon.ico assets/icon.ico
COPY assets/icons/ assets/icons/
COPY core/ core/
COPY ui/__init__.py ui/templates.py ui/
COPY web/ web/
RUN python web/build.py

FROM nginx:1.27-alpine
# python3 runs the Google Drive sign-in helper; it uses only the standard library
RUN apk add --no-cache python3
COPY web/docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY web/drive_auth.py /opt/cube-labeler/drive_auth.py
COPY --chmod=755 web/docker/drive-auth.sh /docker-entrypoint.d/90-drive-auth.sh
COPY --from=build /src/web/dist /usr/share/nginx/html
EXPOSE 80
# 127.0.0.1, not localhost: busybox wget may try ::1 first, and nginx only listens on IPv4 here
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
