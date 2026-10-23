# Cube Labeler web app: builds web/dist and serves it with nginx on port 80.
# TLS is left to the reverse proxy in front (Web Serial needs the page on https).
#
#   docker build -t cube-labeler-web .
#   docker run -d -p 8080:80 cube-labeler-web

FROM python:3.12-slim AS build
WORKDIR /src
COPY constraints.txt .
RUN pip install --no-cache-dir pillow -c constraints.txt
COPY assets/icon.ico assets/icon.ico
COPY core/ core/
COPY web/ web/
RUN python web/build.py

FROM nginx:1.27-alpine
COPY web/docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/web/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK CMD wget -q -O /dev/null http://localhost/ || exit 1
