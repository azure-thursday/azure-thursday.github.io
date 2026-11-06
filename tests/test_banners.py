from email.message import Message
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError


spec = importlib.util.spec_from_file_location(
    "generate_banners",
    Path(__file__).resolve().parents[1] / "scripts" / "generate_banners.py",
)
banners = importlib.util.module_from_spec(spec)
spec.loader.exec_module(banners)


class BannerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "content" / "events").mkdir(parents=True)
        self.manifest = {"events": []}

    def event(self, event_id, day, **extra):
        params = {
            "title": "Azure Thursday",
            "eventDate": day,
            "sessions": [
                {
                    "title": "Workshop",
                    "startTime": "18:45",
                    "speakers": [{"name": "Speaker", "imageUrl": "/images/speaker.png"}],
                }
            ],
        }
        params.update(extra)
        source = f"events/{event_id}.md"
        (self.root / "content" / source).write_text(
            json.dumps(params) + "\n\nEvent details", encoding="utf-8"
        )
        self.manifest["events"].append(
            {"id": event_id, "eventDate": day, "source": source}
        )

    def prepare(self):
        return banners.prepare_requests(
            self.root, self.manifest, "https://www.azurethursday.com"
        )

    def response(self, image=banners.PNG_SIGNATURE + b"test", content_type="image/png"):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.headers = Message()
        response.headers["Content-Type"] = content_type
        response.read.return_value = image
        return response

    def test_payload_and_monthly_filenames(self):
        self.event("december", "2026-12-03", location="Utrecht")
        self.event("january", "2027-01-07", sessions=[])
        requests = self.prepare()
        self.assertEqual([item[0] for item in requests], ["12-2026.png", "01-2027.png"])
        payload = requests[0][1]
        self.assertEqual(payload["schemaVersion"], 1)
        self.assertEqual(payload["event"]["id"], "december")
        self.assertEqual(payload["event"]["location"], "Utrecht")
        self.assertEqual(payload["event"]["timeZone"], "Europe/Amsterdam")
        self.assertEqual(payload["sessions"][0]["startTime"], "18:45")
        self.assertEqual(
            payload["sessions"][0]["speakers"][0]["imageUrl"],
            "https://www.azurethursday.com/images/speaker.png",
        )
        self.assertEqual(requests[1][1]["sessions"], [])

    def test_collisions_and_incorrect_header_paths_fail(self):
        self.event("first", "2026-12-03")
        self.event("second", "2026-12-10")
        with self.assertRaisesRegex(ValueError, "overwrite 12-2026.png"):
            self.prepare()
        self.manifest["events"].clear()
        self.event("wrong-path", "2026-12-03", headerImageUrl="/images/other.png")
        with self.assertRaisesRegex(ValueError, "must use headerImageUrl"):
            self.prepare()

    def test_source_path_cannot_escape_content(self):
        self.manifest["events"].append({"source": "../outside.md"})
        with self.assertRaisesRegex(ValueError, "inside the content directory"):
            self.prepare()

    def test_http_speaker_photos_fail(self):
        self.event(
            "december", "2026-12-03",
            sessions=[{"title": "Talk", "speakers": [{"imageUrl": "http://example.com/p.png"}]}],
        )
        with self.assertRaisesRegex(ValueError, "HTTPS speaker"):
            self.prepare()

    def test_unannounced_speakers_and_invalid_session_shapes(self):
        self.event("december", "2026-12-03", sessions=[{"title": "Talk"}])
        self.assertEqual(self.prepare()[0][1]["sessions"][0]["speakers"], [])
        for sessions in ({}, ["Talk"], [{"title": "Talk", "speakers": {}}]):
            self.manifest["events"].clear()
            self.event("december", "2026-12-03", sessions=sessions)
            with self.subTest(sessions=sessions):
                with self.assertRaises(ValueError):
                    self.prepare()

    @patch.object(banners, "build_opener")
    def test_one_post_per_event_and_output_replacement(self, build_opener):
        self.event("december", "2026-12-03")
        self.event("january", "2027-01-07")
        opener = build_opener.return_value
        image = banners.PNG_SIGNATURE + b"new banner"
        opener.open.return_value = self.response(image)
        output = self.root / "public"
        target = output / "images" / "header"
        target.mkdir(parents=True)
        (target / "12-2026.png").write_bytes(b"old banner")
        banners.generate_banners(self.prepare(), output, "https://example.com/api/banners/v1")
        self.assertEqual(opener.open.call_count, 2)
        for call in opener.open.call_args_list:
            request = call.args[0]
            self.assertEqual(request.get_method(), "POST")
            self.assertIsNone(request.get_header("X-functions-key"))
            self.assertIsNone(request.get_header("Authorization"))
            self.assertEqual(request.get_header("Content-type"), "application/json")
            self.assertEqual(request.get_header("Accept"), "image/png")
            self.assertEqual(json.loads(request.data)["schemaVersion"], 1)
            self.assertEqual(call.kwargs["timeout"], 120)
        for filename in ("12-2026.png", "01-2027.png"):
            self.assertEqual((target / filename).read_bytes(), image)
        self.assertEqual(len(list(target.iterdir())), 2)

    @patch.object(banners, "build_opener")
    def test_failed_responses_preserve_existing_banner(self, build_opener):
        self.event("december", "2026-12-03")
        output = self.root / "public"
        target = output / "images" / "header"
        target.mkdir(parents=True)
        banner = target / "12-2026.png"
        banner.write_bytes(b"existing")
        opener = build_opener.return_value
        for response, message in [
            (self.response(content_type="application/json"), "expected image/png"),
            (self.response(b"not png"), "not a PNG"),
            (self.response(banners.PNG_SIGNATURE), "not a PNG"),
            (self.response(banners.PNG_SIGNATURE + b"x" * banners.MAX_IMAGE_BYTES), "exceeds"),
        ]:
            with self.subTest(message=message):
                opener.open.return_value = response
                with self.assertRaisesRegex(banners.BannerGenerationError, message):
                    banners.generate_banners(
                        self.prepare(), output, "https://example.com/api/banners/v1"
                    )
                self.assertEqual(banner.read_bytes(), b"existing")
        response = self.response()
        response.status = 202
        opener.open.return_value = response
        with self.assertRaisesRegex(banners.BannerGenerationError, "expected HTTP 200"):
            banners.generate_banners(
                self.prepare(), output, "https://example.com/api/banners/v1"
            )
        for error, message in [
            (HTTPError("https://example.com?code=secret", 500, "error", {}, None), "HTTP 500"),
            (URLError("secret endpoint"), "request failed"),
            (TimeoutError(), "request failed"),
        ]:
            opener.open.side_effect = error
            with self.assertRaisesRegex(banners.BannerGenerationError, message) as caught:
                banners.generate_banners(
                    self.prepare(), output, "https://example.com/api/banners/v1"
                )
            self.assertNotIn("secret", str(caught.exception))
            self.assertEqual(banner.read_bytes(), b"existing")

    @patch.object(banners, "build_opener")
    def test_empty_selection_does_not_require_secrets(self, build_opener):
        banners.generate_banners([], self.root / "public", "")
        build_opener.assert_not_called()

    def test_https_endpoint_is_required(self):
        self.event("december", "2026-12-03")
        for endpoint in ("", "http://example.com"):
            with self.assertRaisesRegex(ValueError, "HTTPS endpoint"):
                banners.generate_banners(self.prepare(), self.root / "public", endpoint)

    def test_redirects_are_not_followed(self):
        self.assertIsNone(banners.NoRedirects().redirect_request(
            None, None, 302, "Found", {}, "https://other.example.com"
        ))


if __name__ == "__main__":
    unittest.main()
