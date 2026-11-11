from __future__ import annotations

import argparse
import ipaddress
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlsplit


PAGE = Path(__file__).with_name("iphone_cockpit.html")
STATIC_FILES = {
    "/manifest.json": (Path(__file__).with_name("manifest.json"), "application/manifest+json; charset=utf-8"),
    "/sw.js": (Path(__file__).with_name("sw.js"), "text/javascript; charset=utf-8"),
    "/icon.svg": (Path(__file__).with_name("icon.svg"), "image/svg+xml"),
    "/apple-touch-icon.png": (Path(__file__).with_name("apple-touch-icon.png"), "image/png"),
}


class CockpitHandler(BaseHTTPRequestHandler):
    server_version = "XenomindCockpit/1.0"
    page_path: ClassVar[Path] = PAGE

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path in ("/", "/index.html", "/iphone_cockpit.html"):
            file_path = self.page_path
            content_type = "text/html; charset=utf-8"
        elif path in STATIC_FILES:
            file_path, content_type = STATIC_FILES[path]
        else:
            self.send_error(404, "Not found")
            return

        try:
            content = file_path.read_bytes()
        except OSError as error:
            self.send_error(500, f"Could not read the requested app resource: {error}")
            return

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; manifest-src 'self'; worker-src 'self'; "
            "object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def local_ipv4_addresses() -> list[str]:
    addresses = {
        result[4][0]
        for result in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    }
    return sorted(
        address
        for address in addresses
        if ipaddress.ip_address(address).is_private
        and not ipaddress.ip_address(address).is_loopback
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Serve the Xenomind iPhone cockpit on your local network."
    )
    parser.add_argument("--host", default="0.0.0.0", help="Interface to bind (default: all local interfaces).")
    parser.add_argument("--port", type=int, default=8765, help="Local port (default: 8765).")
    args = parser.parse_args()

    if not PAGE.is_file():
        parser.error(f"Cockpit page not found: {PAGE}")

    server = ThreadingHTTPServer((args.host, args.port), CockpitHandler)
    server.daemon_threads = True
    print("XENOMIND iPhone cockpit is serving one static page only.")
    print("Open one of these URLs in Safari on the same Wi-Fi:")
    if args.host in ("0.0.0.0", "::"):
        addresses = local_ipv4_addresses()
        if addresses:
            for address in addresses:
                print(f"  http://{address}:{server.server_port}/")
        else:
            print(f"  Find this PC's Wi-Fi IPv4 address, then open http://<address>:{server.server_port}/")
    else:
        print(f"  http://{args.host}:{server.server_port}/")
    print("Keep this window open while using the cockpit. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping XENOMIND cockpit server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
