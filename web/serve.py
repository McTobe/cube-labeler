#!/usr/bin/env python3
"""
Builds the Cube Labeler web app and serves it on this computer and the local network.

    python web/serve.py [port]

Open the localhost address on this computer. On a phone on the same Wi-Fi, open the network
address; see web/README.md for the Chrome flag that address needs, since it isn't HTTPS.
"""

import functools
import http.server
import socket
import sys
import webbrowser

import build

DEFAULT_PORT = 8000


def lan_addresses() -> list:
    """Addresses other devices on the network can reach this computer at (a PC can have several)."""
    found = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            # No packet is sent: connecting a UDP socket only picks the outgoing interface
            s.connect(("192.168.0.1", 9))
            found.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        found += socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        pass
    return [a for a in dict.fromkeys(found) if not a.startswith("127.")]


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    build.main()

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=build.DIST_DIR)
    try:
        server = http.server.ThreadingHTTPServer(("0.0.0.0", port), handler)
    except OSError as e:
        print(f"Could not start the server on port {port}: {e}")
        print("Is Cube Labeler web already running? Close it, or pass another port.")
        return 1

    local_url = f"http://localhost:{port}/"
    print()
    print(f"  On this computer: {local_url}")
    for address in lan_addresses():
        print(f"  On your phone:    http://{address}:{port}/")
    print()
    print("Press Ctrl+C to stop.")

    webbrowser.open(local_url)
    with server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("Stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
