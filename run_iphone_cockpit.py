from __future__ import annotations

import argparse
import ipaddress
import json
import math
import os
import re
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
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
LYRIC_JOBS: dict[str, dict[str, object]] = {}
LYRIC_JOBS_LOCK = threading.Lock()


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


def extract_description_lyrics(description: str) -> str:
    lines = str(description or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    heading_index = next((index for index, line in enumerate(lines) if re.fullmatch(
        r"\s*(?:official\s+)?(?:song\s+)?lyrics(?:\s*\([^)]*\))?\s*[:\-–—]?\s*", line, re.I
    )), -1)
    if heading_index < 0:
        return ""
    stop_heading = re.compile(
        r"^(?:about|subscribe|stream|listen|follow|credits?|written by|produced by|music video|official video|connect|socials?|more from|find (?:us|me|the artist)|label|management|booking|support|join|watch|buy|available on)\b",
        re.I,
    )
    lyrics: list[str] = []
    blank_lines = 0
    for raw_line in lines[heading_index + 1:]:
        line = raw_line.strip()
        if not line:
            blank_lines += 1
            if blank_lines > 2 and len(lyrics) >= 3:
                break
            if lyrics and lyrics[-1]:
                lyrics.append("")
            continue
        blank_lines = 0
        if re.match(r"^(?:https?://|www\.)", line, re.I) or stop_heading.match(line):
            break
        if re.fullmatch(r"\[?(?:verse|chorus|bridge|intro|outro|pre.?chorus)\s*\d*\]?|\(?(?:verse|chorus|bridge|intro|outro)\)?\s*\d*", line, re.I):
            continue
        lyric_line = re.sub(r"^(?:\d{1,2}:)?\d{1,2}:\d{2}\s+", "", line)
        if lyric_line:
            lyrics.append(lyric_line)
        if len("\n".join(lyrics)) >= MAX_LYRIC_CHARACTERS:
            break
    result = "\n".join(lyrics).strip()[:MAX_LYRIC_CHARACTERS]
    word_count = len(result.split())
    nonempty_lines = sum(bool(line.strip()) for line in result.splitlines())
    return result if nonempty_lines >= 3 and word_count >= 10 else ""


def get_public_youtube_metadata(video_id: str, fallback_api_key: str) -> Optional[dict]:
    api_key = os.environ.get("YOUTUBE_API_KEY", fallback_api_key).strip()
    if not api_key:
        return None
    query = urlencode({"part": "snippet,status", "id": video_id, "key": api_key})
    upstream_request = Request("https://www.googleapis.com/youtube/v3/videos?" + query)
    try:
        with urlopen(upstream_request, timeout=4.5) as upstream:
            data = json.loads(upstream.read().decode("utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("items"), list) or not data["items"]:
            return None
        video = data["items"][0]
        if not isinstance(video, dict):
            return None
        status = video.get("status")
        if not isinstance(status, dict) or status.get("privacyStatus") != "public":
            return None
        snippet = video.get("snippet", {})
        if not isinstance(snippet, dict):
            return None
        return {
            "title": str(snippet.get("title", ""))[:200],
            "channelTitle": str(snippet.get("channelTitle", ""))[:200],
            "lyrics": extract_description_lyrics(str(snippet.get("description", ""))),
        }
    except (HTTPError, TimeoutError, URLError, json.JSONDecodeError, UnicodeDecodeError):
        return None


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

        action = body.get("action", "start")
        if action not in ("start", "poll", "cleanup", "cancel"):
            self.send_json(400, {"message": "This lyric analysis action is not supported."})
            return
        if action != "start":
            self.handle_lyrics_job_action(action, str(body.get("jobToken", "")), api_key)
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
                retry_after_ms = math.ceil((LYRIC_RATE_LIMIT_SECONDS - (now - previous)) * 1000)
                self.send_json(429, {
                    "message": "Please wait a few seconds before generating another lyric draft.",
                    "retryable": True,
                    "retryAfterMs": retry_after_ms,
                })
                return
            LYRIC_REQUESTS[client_ip] = now
            if len(LYRIC_REQUESTS) > 5000:
                oldest_ip = min(LYRIC_REQUESTS, key=LYRIC_REQUESTS.get)
                LYRIC_REQUESTS.pop(oldest_ip, None)

        metadata = get_public_youtube_metadata(video_id, api_key)
        if metadata and metadata.get("lyrics"):
            self.send_json(200, {
                "status": "completed",
                "source": "youtube_description",
                "videoTitle": metadata.get("title", ""),
                "channelTitle": metadata.get("channelTitle", ""),
                "lyrics": metadata["lyrics"],
            })
            return
        lyrics_search_url = ""
        if metadata and metadata.get("title"):
            query = " ".join(part for part in [metadata.get("channelTitle", ""), metadata["title"], "lyrics"] if part)
            lyrics_search_url = "https://www.google.com/search?" + urlencode({"q": query})

        language_hint = re.sub(r"[\x00-\x1f\x7f]", " ", str(body.get("languageHint", ""))).strip()[:100]
        prompt = "\n".join(part for part in [
            "Create a working lyric transcription draft for musicians rehearsing this song.",
            "Transcribe only words that are actually sung or spoken in the audio, in their original language and in the order heard.",
            "Do not summarize, translate, complete missing lines from memory, or add explanations, speaker labels, or music descriptions.",
            "Keep repeated lyrics repeated. Put each vocal phrase on its own line.",
            "Mark words you cannot confidently hear as [unclear] rather than guessing.",
            "Language or pronunciation hint from the band: " + language_hint if language_hint else "",
        ] if part)
        request_body = {
            "model": "gemini-3.8-flash",
            "store": True,
            "background": True,
            "input": [
                {"type": "text", "text": prompt},
                {"type": "video", "uri": f"https://www.youtube.com/watch?v={video_id}"},
            ],
            "generation_config": {"thinking_level": "low", "max_output_tokens": 16000},
        }
        try:
            result = self.gemini_request(api_key, "", "POST", request_body)
        except HTTPError as error:
            try:
                error_body = json.loads(error.read().decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                error_body = {}
            provider_error = error_body.get("error", {}) if isinstance(error_body, dict) else {}
            provider_message = str(provider_error.get("message", "")) if isinstance(provider_error, dict) else ""
            if error.code == 429 and re.search(r"daily|per.day|quota_exceeded|spend limit|billing|credits", provider_message, re.I):
                message = "Gemini's project quota or spend limit is exhausted. Check the active limits and billing for this API key in Google AI Studio."
            elif error.code == 429:
                message = "Gemini returned a 429 request limit. Check the Gemini API limits in Google AI Studio; this may be temporary capacity or a project quota."
            elif error.code in (400, 404):
                message = "This video could not be analyzed. Check the link and make sure the video is public."
            elif error.code in (401, 403):
                message = "The lyric generator's server key is invalid or does not have API access."
            else:
                message = "The lyric generator is temporarily unavailable. Try again later."
            self.send_json(429 if error.code == 429 else 502, {
                "message": message,
                "lyricsSearchUrl": lyrics_search_url,
            })
            return
        except (TimeoutError, URLError):
            self.send_json(504, {"message": "Gemini did not confirm that the analysis was queued. Try again; no lyric draft was returned."})
            return
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_json(502, {"message": "The lyric generator returned an unreadable response."})
            return

        interaction_id = str(result.get("id", "")) if isinstance(result, dict) else ""
        if not re.fullmatch(r"(?:v1|int)_[A-Za-z0-9_-]{6,200}", interaction_id):
            self.send_json(502, {"message": "Gemini did not return a valid background job. Try again later."})
            return
        status = str(result.get("status", ""))
        if status == "completed":
            lyrics = extract_gemini_text(result)
            try:
                self.gemini_request(api_key, "/" + interaction_id, "DELETE")
            except (HTTPError, TimeoutError, URLError):
                pass
            if not lyrics:
                self.send_json(422, {"message": "No clear vocals were detected in this video."})
            elif len(lyrics) > MAX_LYRIC_CHARACTERS:
                self.send_json(422, {"message": "The lyric draft is too long for one note. Use a shorter video."})
            else:
                self.send_json(200, {"status": "completed", "lyrics": lyrics})
            return
        if status not in ("queued", "in_progress"):
            try:
                self.gemini_request(api_key, "/" + interaction_id, "DELETE")
            except (HTTPError, TimeoutError, URLError):
                pass
            self.send_json(502, {"message": "The lyric draft could not be started. Try again later."})
            return
        job_token = secrets.token_urlsafe(32)
        with LYRIC_JOBS_LOCK:
            LYRIC_JOBS[job_token] = {"id": interaction_id, "expires": time.time() + 20 * 60}
        self.send_json(202, {
            "status": status,
            "jobToken": job_token,
            "pollAfterMs": 2500,
            "lyricsSearchUrl": lyrics_search_url,
        })

    def gemini_request(self, api_key: str, path: str, method: str, body: Optional[dict] = None) -> dict:
        request_data = json.dumps(body).encode("utf-8") if body is not None else None
        upstream_request = Request(
            "https://generativelanguage.googleapis.com/v1beta/interactions" + path,
            data=request_data,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
                "Api-Revision": "2026-05-20",
            },
            method=method,
        )
        with urlopen(upstream_request, timeout=12) as upstream:
            response_data = upstream.read()
        if not response_data:
            return {}
        result = json.loads(response_data.decode("utf-8"))
        return result if isinstance(result, dict) else {}

    def handle_lyrics_job_action(self, action: str, job_token: str, api_key: str) -> None:
        expired_job = None
        with LYRIC_JOBS_LOCK:
            job = LYRIC_JOBS.get(job_token)
            if job and float(job.get("expires", 0)) < time.time():
                expired_job = LYRIC_JOBS.pop(job_token, None)
                job = None
        if expired_job:
            expired_id = str(expired_job.get("id", ""))
            if expired_id:
                try:
                    self.gemini_request(api_key, "/" + expired_id + "/cancel", "POST", {})
                except (HTTPError, TimeoutError, URLError):
                    pass
                try:
                    self.gemini_request(api_key, "/" + expired_id, "DELETE")
                except (HTTPError, TimeoutError, URLError):
                    pass
        if not job:
            self.send_json(400, {"message": "This lyric analysis session has expired. Start the import again."})
            return
        interaction_id = str(job["id"])
        path = "/" + interaction_id
        try:
            if action == "cleanup":
                self.gemini_request(api_key, path, "DELETE")
                with LYRIC_JOBS_LOCK:
                    LYRIC_JOBS.pop(job_token, None)
                self.send_json(200, {"deleted": True})
                return
            if action == "cancel":
                try:
                    self.gemini_request(api_key, path + "/cancel", "POST", {})
                except HTTPError:
                    pass
                self.gemini_request(api_key, path, "DELETE")
                with LYRIC_JOBS_LOCK:
                    LYRIC_JOBS.pop(job_token, None)
                self.send_json(200, {"deleted": True})
                return

            result = self.gemini_request(api_key, path, "GET")
        except HTTPError as error:
            if error.code in (429, 500, 502, 503, 504):
                self.send_json(503, {"status": "in_progress", "retryable": True, "retryAfterMs": 4000})
            elif error.code == 404:
                with LYRIC_JOBS_LOCK:
                    LYRIC_JOBS.pop(job_token, None)
                self.send_json(410, {"message": "Gemini no longer has this lyric analysis. Start the import again."})
            else:
                self.send_json(502, {"message": "Gemini could not retrieve this lyric analysis."})
            return
        except (TimeoutError, URLError, json.JSONDecodeError, UnicodeDecodeError):
            self.send_json(503, {"status": "in_progress", "retryable": True, "retryAfterMs": 4000})
            return

        status = str(result.get("status", ""))
        if status in ("queued", "in_progress"):
            self.send_json(202, {"status": status, "pollAfterMs": 3500})
            return
        if status != "completed":
            try:
                self.gemini_request(api_key, path, "DELETE")
            except (HTTPError, TimeoutError, URLError):
                pass
            with LYRIC_JOBS_LOCK:
                LYRIC_JOBS.pop(job_token, None)
            self.send_json(502, {"message": "The lyric draft did not finish. Check the Gemini API limits or try again later."})
            return
        lyrics = extract_gemini_text(result)
        if not lyrics:
            self.gemini_request(api_key, path, "DELETE")
            with LYRIC_JOBS_LOCK:
                LYRIC_JOBS.pop(job_token, None)
            self.send_json(422, {"message": "No clear vocals were detected in this video."})
        elif len(lyrics) > MAX_LYRIC_CHARACTERS:
            self.gemini_request(api_key, path, "DELETE")
            with LYRIC_JOBS_LOCK:
                LYRIC_JOBS.pop(job_token, None)
            self.send_json(422, {"message": "The lyric draft is too long for one note. Use a shorter video."})
        else:
            self.send_json(200, {"status": "completed", "lyrics": lyrics})

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
