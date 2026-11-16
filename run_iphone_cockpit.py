from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen


PAGE = Path(__file__).with_name("iphone_cockpit.html")
STATIC_FILES = {
    "/IOS_SHORTCUTS.md": (Path(__file__).with_name("IOS_SHORTCUTS.md"), "text/markdown; charset=utf-8"),
    "/manifest.json": (Path(__file__).with_name("manifest.json"), "application/manifest+json; charset=utf-8"),
    "/sw.js": (Path(__file__).with_name("sw.js"), "text/javascript; charset=utf-8"),
    "/voice_command_parser.js": (Path(__file__).with_name("voice_command_parser.js"), "text/javascript; charset=utf-8"),
    "/icon.svg": (Path(__file__).with_name("icon.svg"), "image/svg+xml"),
    "/apple-touch-icon.png": (Path(__file__).with_name("apple-touch-icon.png"), "image/png"),
}
MAX_LYRIC_REQUEST_BYTES = 4096
MAX_LYRIC_CHARACTERS = 50000
LYRIC_RATE_LIMIT_SECONDS = 15
LYRIC_REQUESTS: dict[str, float] = {}
LYRIC_REQUESTS_LOCK = threading.Lock()


def youtube_video_id(value: str) -> str:
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower().removeprefix("www.")
        if parsed.scheme != "https" or host not in {
            "youtube.com", "m.youtube.com", "music.youtube.com",
            "youtube-nocookie.com", "youtu.be",
        }:
            return ""
        if host == "youtu.be":
            video_id = parsed.path.strip("/").split("/", 1)[0]
        else:
            video_id = parse_qs(parsed.query).get("v", [""])[0]
            if not video_id:
                match = re.match(r"^/(?:shorts|embed|live)/([^/?]+)", parsed.path)
                video_id = match.group(1) if match else ""
        return video_id if re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id) else ""
    except ValueError:
        return ""


def extract_gemini_text(result: dict) -> str:
    if not isinstance(result, dict):
        return ""
    output_text = result.get("output_text")
    if isinstance(output_text, str):
        return output_text.strip()
    lines = []
    for step in result.get("steps", []):
        if not isinstance(step, dict) or step.get("type") != "model_output":
            continue
        for item in step.get("content", []):
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                lines.append(item["text"])
    return "\n".join(lines).strip()


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
            "default-src 'none'; script-src 'self' 'unsafe-inline'; "
            "style-src 'unsafe-inline'; img-src 'self' data:; "
            "connect-src 'self'; manifest-src 'self'; worker-src 'self'; "
            "object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/api/transcribe-lyrics":
            self.send_error(404, "Not found")
            return
        origin = self.headers.get("Origin")
        if origin:
            try:
                origin_url = urlsplit(origin)
                request_host = self.headers.get("Host", "")
                if (
                    origin_url.scheme != "http"
                    or not origin_url.netloc
                    or origin_url.netloc.lower() != request_host.lower()
                    or origin_url.path not in ("", "/")
                    or origin_url.query
                    or origin_url.fragment
                ):
                    self.send_json(403, {"message": "Requests must come from this XENOMIND page."})
                    return
            except ValueError:
                self.send_json(403, {"message": "Requests must come from this XENOMIND page."})
                return
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            self.send_json(415, {"message": "Send the request as JSON."})
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_json(400, {"message": "The request could not be read."})
            return
        if content_length <= 0 or content_length > MAX_LYRIC_REQUEST_BYTES:
            self.send_json(413, {"message": "The request is too large or empty."})
            return
        try:
            body = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_json(400, {"message": "The request could not be read."})
            return
        if not isinstance(body, dict):
            self.send_json(400, {"message": "The request could not be read."})
            return

        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            self.send_json(503, {
                "message": "The lyric generator is not configured. Set GEMINI_API_KEY in the server environment and restart it."
            })
            return
        video_id = youtube_video_id(str(body.get("videoUrl", "")))
        if not video_id:
            self.send_json(400, {"message": "Use a public YouTube video link."})
            return

        client_ip = self.client_address[0]
        now = time.monotonic()
        with LYRIC_REQUESTS_LOCK:
            previous = LYRIC_REQUESTS.get(client_ip)
            if previous is not None and now - previous < LYRIC_RATE_LIMIT_SECONDS:
                self.send_json(429, {"message": "Please wait a few seconds before generating another lyric draft."})
                return
            LYRIC_REQUESTS[client_ip] = now
            if len(LYRIC_REQUESTS) > 5000:
                oldest_ip = min(LYRIC_REQUESTS, key=LYRIC_REQUESTS.get)
                LYRIC_REQUESTS.pop(oldest_ip, None)

        language_hint = re.sub(r"[\x00-\x1f\x7f]", " ", str(body.get("languageHint", ""))).strip()[:100]
        prompt = "\n".join(part for part in [
            "Create a working lyric transcription draft for musicians rehearsing this song.",
            "Transcribe only words that are actually sung or spoken in the audio, in their original language and in the order heard.",
            "Do not summarize, translate, complete missing lines from memory, or add explanations, speaker labels, or music descriptions.",
            "Keep repeated lyrics repeated. Put each vocal phrase on its own line.",
            "Mark words you cannot confidently hear as [unclear] rather than guessing.",
            "Language or pronunciation hint from the band: " + language_hint if language_hint else "",
        ] if part)
        request_data = json.dumps({
            "model": "gemini-3.8-flash",
            "store": False,
            "input": [
                {"type": "text", "text": prompt},
                {"type": "video", "uri": f"https://www.youtube.com/watch?v={video_id}"},
            ],
            "generation_config": {"thinking_level": "low", "max_output_tokens": 16000},
        }).encode("utf-8")
        upstream_request = Request(
            "https://generativelanguage.googleapis.com/v1beta/interactions",
            data=request_data,
            headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
            method="POST",
        )
        try:
            with urlopen(upstream_request, timeout=55) as upstream:
                result = json.loads(upstream.read().decode("utf-8"))
        except HTTPError as error:
            message = (
                "The lyric generator is at its request limit. Try again later." if error.code == 429
                else "This video could not be analyzed. Check the link and make sure the video is public." if error.code in (400, 404)
                else "The lyric generator's server key is invalid or does not have API access." if error.code in (401, 403)
                else "The lyric generator is temporarily unavailable. Try again later."
            )
            self.send_json(429 if error.code == 429 else 502, {"message": message})
            return
        except (TimeoutError, URLError):
            self.send_json(504, {"message": "The video took too long to analyze. Try again or use a shorter video."})
            return
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_json(502, {"message": "The lyric generator returned an unreadable response."})
            return

        if not isinstance(result, dict):
            self.send_json(502, {"message": "The lyric generator returned an unreadable response."})
            return
        if result.get("status") and result["status"] != "completed":
            self.send_json(502, {"message": "The lyric draft did not finish. Try again or use a shorter video."})
            return
        lyrics = extract_gemini_text(result)
        if not lyrics:
            self.send_json(422, {"message": "No clear vocals were detected in this video."})
            return
        if len(lyrics) > MAX_LYRIC_CHARACTERS:
            self.send_json(422, {"message": "The lyric draft is too long for one note. Use a shorter video."})
            return
        self.send_json(200, {"lyrics": lyrics})

    def send_json(self, status: int, body: dict) -> None:
        content = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
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
    print("XENOMIND iPhone cockpit and local lyric-generation endpoint are running.")
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
