# Security policy

## Reporting a vulnerability

Please don't open a public issue for security problems. Report them privately instead:

- Use **Report a vulnerability** on the [Security tab](https://github.com/McTobe/cube-labeler/security/advisories/new), or
- email **admin@tobezone.com**.

Say what you found, how to reproduce it and which version you used (web image tag or commit). You'll get an answer within a week. This is a hobby project run by one person, so there is no bug bounty.

## Supported versions

Only the latest release gets fixes, in the web version and its Docker image. The Windows desktop app ended with v2.4.0 and gets no more fixes.

## What's in scope

- The web app and the Docker image `ghcr.io/mctobe/cube-labeler-web`, including the Google sign-in helper (`web/drive_auth.py`).

Problems in Google, OpenAI or OpenRouter themselves, or in a reverse proxy you put in front of the image, are out of scope.
