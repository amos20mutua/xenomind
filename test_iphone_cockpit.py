from __future__ import annotations

from pathlib import Path
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen

from run_iphone_cockpit import CockpitHandler


class IPhoneCockpitServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), CockpitHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_root_serves_cockpit_and_shortcut_handoff(self) -> None:
        with urlopen(self.base_url, timeout=2) as response:
            page = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers.get_content_type(), "text/html")
            self.assertIn("connect-src 'self'", response.headers.get("Content-Security-Policy", ""))

        self.assertIn("XENOMIND", page)
        self.assertIn("shortcuts://x-callback-url/run-shortcut", page)
        self.assertIn("xenomind://run", page)
        self.assertIn("Reminders", page)
        self.assertIn("Photos &amp; Files", page)
        self.assertIn("Home", page)
        self.assertIn("home.classList.add(\"unavailable\")", page)
        self.assertIn('role="tablist" aria-label="Choose a task system"', page)
        self.assertIn('role="tabpanel" aria-labelledby="tab-library" hidden', page)
        self.assertIn('role="tabpanel" aria-labelledby="tab-home" hidden', page)
        self.assertIn('id="tab-notes"', page)
        self.assertIn('role="tabpanel" aria-labelledby="tab-notes" hidden', page)
        self.assertIn('id="note-body"', page)
        self.assertIn('id="toggle-stage"', page)
        self.assertIn('id="notes-count"', page)
        self.assertIn('id="stage-text-smaller"', page)
        self.assertIn('id="stage-text-larger"', page)
        self.assertIn("body.notes-mode .activity-panel", page)
        self.assertIn("function updateNoteMetrics()", page)
        self.assertIn("function setStageTextSize(size)", page)
        self.assertIn("notesCount.textContent", page)
        self.assertIn("--stage-note-size", page)
        self.assertIn('id="stage-wake"', page)
        self.assertIn('id="wake-brain"', page)
        self.assertIn("z-index: 0;", page)
        self.assertIn("width: min(108vw, 680px);", page)
        self.assertIn("transform: translate(-50%, -50%);", page)
        self.assertIn("opacity: .9;", page)
        self.assertIn("drop-shadow(0 0 22px rgba(67,224,205,.22))", page)
        self.assertIn("z-index: 1;", page)
        self.assertIn("Math.min(width * .47, height * .35)", page)
        self.assertIn("brainFramePending = false;", page)
        self.assertIn("function wakeStageDisplay()", page)
        self.assertIn('addEventListener("pointerdown"', page)
        self.assertIn("animation: neural-float 7.4s ease-in-out infinite", page)
        self.assertIn("@keyframes neural-float", page)
        self.assertIn("@media (prefers-reduced-motion: reduce)", page)
        self.assertIn('const notesKey = "xenomind-stage-notes-v1"', page)
        self.assertIn("localStorage.getItem(notesKey)", page)
        self.assertIn("localStorage.setItem(notesKey, JSON.stringify(stageNotes))", page)
        self.assertIn('}, 60000)', page)
        self.assertIn('1000 / 15', page)
        self.assertIn('1000 / 12', page)
        self.assertNotIn('<nav class="bottom-nav"', page)
        self.assertIn('apple-mobile-web-app-capable" content="yes"', page)
        self.assertIn("dispatchToiOS", page)
        self.assertIn("x-success", page)
        self.assertIn('id="intent-input"', page)
        self.assertNotIn("placeholder=", page)
        self.assertIn("reminder-due-wrap", page)
        self.assertIn("SpeechRecognition", page)

    def test_pwa_assets_and_callback_query_are_served(self) -> None:
        for path, content_type, marker in (
            ("/manifest.json", "application/manifest+json", '"display": "standalone"'),
            ("/sw.js", "text/javascript", "XENOMIND"),
            ("/icon.svg", "image/svg+xml", "<svg"),
            ("/apple-touch-icon.png", "image/png", "\x89PNG"),
        ):
            with self.subTest(path=path):
                with urlopen(f"{self.base_url}{path}", timeout=2) as response:
                    raw = response.read()
                    body = raw.decode("latin-1")
                    self.assertEqual(response.status, 200)
                    self.assertIn(content_type, response.headers.get("Content-Type", ""))
                    self.assertIn(marker, body)

        with urlopen(f"{self.base_url}/?handoff=success&id=test", timeout=2) as response:
            self.assertEqual(response.status, 200)

        with urlopen(f"{self.base_url}/index.html?handoff=success&id=test", timeout=2) as response:
            self.assertEqual(response.status, 200)

    def test_server_does_not_expose_other_project_files(self) -> None:
        for path in ("/README.md", "/simulation_core.py", "/README.md?handoff=success&id=test"):
            with self.subTest(path=path):
                with self.assertRaises(HTTPError) as error:
                    urlopen(f"{self.base_url}{path}", timeout=2)

                self.assertEqual(error.exception.code, 404)
                error.exception.close()

    def test_netlify_publishes_root_and_rewrites_home_to_cockpit(self) -> None:
        root = Path(__file__).parent
        netlify_config = (root / "netlify.toml").read_text(encoding="utf-8")
        redirects = (root / "_redirects").read_text(encoding="utf-8")

        self.assertIn('publish = "."', netlify_config)
        self.assertIn("/  /iphone_cockpit.html  200", redirects)


if __name__ == "__main__":
    unittest.main()
