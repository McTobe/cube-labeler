# Google sign-in: staying signed in, and letting anyone sign in

Cube Labeler web syncs icons, templates and settings through the user's own Google Drive.
Out of the box Google gives the page a token that works for an hour, and then sync pauses
until the user clicks **Continue with Google**. The Docker image can do better: give it the
OAuth client's secret, and each person signs in once per device and stays signed in.

## How it works

The image runs a small helper (`web/drive_auth.py`, Python standard library only) beside
nginx, which passes `/auth/` to it.

1. **Sign in with Google** opens a small window at `/auth/start`, which sends the user to
   Google asking for the `drive.file` scope with offline access.
2. Google sends them back to `/auth/callback` with a one-time code. The helper swaps it, with
   the client secret, for a refresh token, and puts that in a cookie in the user's browser:
   encrypted and signed with a key made from the secret, `HttpOnly`, `Secure`, `SameSite=Lax`,
   and only sent to `/auth/`. The window tells the app it worked and closes.
3. Whenever the app needs to talk to Drive and its one-hour token is about to run out, it
   POSTs to `/auth/token`. The helper uses the refresh token to get a new one from Google and
   hands it to the page. No click is needed.
4. **Sign out** POSTs to `/auth/signout`, which asks Google to cancel the refresh token and
   removes the cookie.

The helper stores nothing on the server, so there is no database or volume, and any number
of people can sign in. Backups still go straight from the browser to Google Drive. Without
the secret (for example `python web/serve.py` on your PC) the app signs in the hourly way,
as before.

| Variable | What it is |
|---|---|
| `GOOGLE_CLIENT_SECRET` | The OAuth client's secret. Required to stay signed in. Keep it out of the repository. |
| `PUBLIC_URL` | The address people open the app at, such as `https://print.tobezone.com`. Google sends them back to `PUBLIC_URL/auth/callback`. If it is empty, the helper works it out from the `Host` and `X-Forwarded-*` headers. |
| `GOOGLE_CLIENT_ID` | Only if you use another OAuth client than the one in `web/js/gdrive.js`. |

Replacing the secret signs everyone out (their cookies no longer open), and they sign in once more.

## Setting it up

### 1. Google Cloud Console: the OAuth client

1. Open <https://console.cloud.google.com/>, pick the **Cube Labeler** project, and go to
   **Google Auth Platform › Clients** (older menus: **APIs & Services › Credentials**).
2. Open the **Cube Labeler web** client.
3. Under **Authorized redirect URIs**, add `https://print.tobezone.com/auth/callback`.
   Keep the JavaScript origins as they are (`https://print.tobezone.com`, `http://localhost:8000`).
4. Under **Client secrets**, copy the secret. If it is hidden (Google only shows new secrets
   once), click **Add secret** and copy the new one. Save.

Don't paste the secret into a chat, an issue or the repository.

### 2. Dockge: give the container the secret

In the Cube Labeler stack, add the two variables to the compose file:

```yaml
services:
  cube-labeler-web:
    image: ghcr.io/mctobe/cube-labeler-web:latest
    environment:
      GOOGLE_CLIENT_SECRET: ${GOOGLE_CLIENT_SECRET}
      PUBLIC_URL: https://print.tobezone.com
    ports:
      - "8080:80"
    restart: unless-stopped
```

and put the secret in the stack's **.env** box (Dockge shows it under the compose file):

```
GOOGLE_CLIENT_SECRET=GOCSPX-...
```

Press **Save** and then **Update** once an image with the helper is out. The container log
then says `staying signed in to Google Drive is on`.

### 3. Publish the consent screen, so anyone can sign in

While the app is in **Testing**, only the test users you listed can sign in, and Google also
cancels their refresh tokens after 7 days. Publishing fixes both. Cube Labeler only asks for
`drive.file`, which Google counts as non-sensitive, so publishing needs no review.

1. **Google Auth Platform › Branding**:
   - App name **Cube Labeler**, your email as the user support email and developer contact.
   - App home page: `https://print.tobezone.com/about.html` (a plain page that explains the app;
     Google's check doesn't run the app itself, so the main page looks empty to it)
   - Privacy policy: `https://print.tobezone.com/privacy.html`
   - Authorized domains: `tobezone.com`
   - Leave the logo empty. Adding a logo makes Google want to verify the brand first.
   - Brand verification is optional with only `drive.file`. Without it the consent screen shows
     the domain instead of the name "Cube Labeler". To get it verified, the About and privacy
     pages above are what Google's check looks at; then click **Verify branding**. The domain
     also has to be verified in [Google Search Console](https://search.google.com/search-console)
     with the same Google account.
2. **Google Auth Platform › Data access**: the only scope listed should be
   `.../auth/drive.file`. Don't add more.
3. **Google Auth Platform › Audience**: click **Publish app** and confirm. The status changes
   from *Testing* to *In production*.

People signing in see the Google consent screen with "Cube Labeler wants to see, edit, create
and delete only the specific Google Drive files you use with this app".

### 4. Sign in again on each device, once

Devices that were signed in the hourly way show **Paused** once their last token runs out.
Click **Continue with Google** in the Sync box: from then on that device stays signed in.

## If something goes wrong

- **"redirect_uri_mismatch" from Google:** the redirect URI in step 1 must match `PUBLIC_URL`
  exactly, with `https://` and no trailing slash before `/auth/callback`.
- **Sync keeps asking to sign in again:** check the container log for `drive-auth` lines. If it
  says the helper is off, the secret did not reach the container. If the app is still in
  Testing, sign-ins last 7 days.
- **"The browser blocked the Google window":** allow pop-ups for the site. On a phone the
  sign-in opens as a new tab and closes itself when done.
- People can remove Cube Labeler's access any time at
  <https://myaccount.google.com/connections>.
