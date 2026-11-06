from email.message import Message
from contextlib import redirect_stderr
import importlib.util
from io import BytesIO, StringIO
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
            "headerImageUrl": f"/images/header/{event_id}.png",
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

    def test_payload_and_configured_paths(self):
        self.event("december", "2026-12-03", location="Utrecht")
        self.event("january", "2027-01-07", sessions=[])
        requests = self.prepare()
        self.assertEqual(
            [path.as_posix() for path, _ in requests],
            ["images/header/december.png", "images/header/january.png"],
        )
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

    def test_duplicate_configured_paths_fail_before_any_posts(self):
        self.event("first", "2026-12-03", headerImageUrl="/images/header/shared.png")
        self.event("second", "2026-12-10", headerImageUrl="/images/header/shared.png")
        with self.assertRaisesRegex(ValueError, "overwrite images/header/shared.png"):
            self.prepare()

    def test_encoded_alias_paths_are_duplicates(self):
        self.event("first", "2026-12-03", headerImageUrl="/images/header/same.png")
        self.event("second", "2026-12-10", headerImageUrl="/images/header/%73ame.png")
        with self.assertRaisesRegex(ValueError, "overwrite images/header/same.png"):
            self.prepare()

    def test_missing_and_unsafe_header_paths_fail(self):
        for path in (
            None, "", "images/header/test.png", "https://example.com/test.png",
            "//example.com/test.png", "/images/../test.png", "/images/%2e%2e/test.png",
            "/images/header/test.png?download=1", "/images/header/test.png#fragment",
            "/images/header/test.jpg", "/images\\header\\test.png", "/images/C:/test.png",
            "/images//test.png", "/images/header/%00test.png",
        ):
            with self.subTest(path=path):
                self.manifest["events"].clear()
                self.event("invalid", "2026-12-03", headerImageUrl=path)
                with self.assertRaises(ValueError):
                    self.prepare()
        self.manifest["events"].clear()
        self.event("missing", "2026-12-03")
        page = self.root / "content" / "events" / "missing.md"
        params, _ = json.JSONDecoder().raw_decode(page.read_text())
        del params["headerImageUrl"]
        page.write_text(json.dumps(params))
        with self.assertRaisesRegex(ValueError, "requires a root-relative PNG"):
            self.prepare()

    def test_session_and_speaker_limits_and_titles(self):
        for extra, message in [
            ({"sessions": [{"title": "Talk", "speakers": []}] * 4}, "maximum is 3"),
            (
                {"sessions": [{"title": "Talk", "speakers": [{"name": "Speaker"}] * 3}]},
                "maximum is 2",
            ),
            ({"title": " "}, "nonempty title"),
            ({"sessions": [{"title": " ", "speakers": []}]}, "nonempty session title"),
            ({"sessions": [{"speakers": []}]}, "nonempty session title"),
            ({"timeZone": "UTC"}, "only supports timeZone Europe/Amsterdam"),
        ]:
            with self.subTest(extra=extra):
                self.manifest["events"].clear()
                self.event("invalid", "2026-12-03", **extra)
                with self.assertRaisesRegex(ValueError, message):
                    self.prepare()
        self.manifest["events"].clear()
        self.event(
            "boundary", "2026-12-03",
            sessions=[
                {"title": f"Talk {i}", "speakers": [{"name": "First"}, {"name": "Second"}]}
                for i in range(3)
            ],
        )
        sessions = self.prepare()[0][1]["sessions"]
        self.assertEqual([session["title"] for session in sessions], ["Talk 0", "Talk 1", "Talk 2"])
        self.assertEqual(
            [speaker["name"] for speaker in sessions[0]["speakers"]], ["First", "Second"]
        )

    def test_source_path_cannot_escape_content(self):
        self.manifest["events"].append({"id": "outside", "source": "../outside.md"})
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
        self.event("later-december", "2026-12-10", sessions=[])
        opener = build_opener.return_value
        image = banners.PNG_SIGNATURE + b"new banner"
        opener.open.return_value = self.response(image)
        output = self.root / "public"
        target = output / "images" / "header"
        target.mkdir(parents=True)
        (target / "december.png").write_bytes(b"old banner")
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
        payloads = [json.loads(call.args[0].data) for call in opener.open.call_args_list]
        self.assertEqual(
            [payload["event"]["id"] for payload in payloads], ["december", "later-december"]
        )
        self.assertEqual(payloads[1]["sessions"], [])
        for filename in ("december.png", "later-december.png"):
            self.assertEqual((target / filename).read_bytes(), image)
        self.assertEqual(len(list(target.iterdir())), 2)

    @patch.object(banners, "build_opener")
    def test_failed_responses_preserve_existing_banner(self, build_opener):
        self.event("december", "2026-12-03")
        output = self.root / "public"
        target = output / "images" / "header"
        target.mkdir(parents=True)
        banner = target / "december.png"
        banner.write_bytes(b"existing")
        opener = build_opener.return_value
        for response, message in [
            (self.response(content_type="application/json"), "expected image/png"),
            (self.response(content_type="image/png; charset=UTF-8"), "expected image/png"),
            (self.response(content_type="IMAGE/PNG"), "expected image/png"),
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
        with self.assertRaisesRegex(banners.BannerGenerationError, "HTTP 202"):
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
    def test_full_problem_body_is_logged_and_main_fails(self, build_opener):
        self.event("december", "2026-12-03")
        output = self.root / "public"
        (output / "json").mkdir(parents=True)
        (output / "json" / "banner-events.json").write_text(json.dumps(self.manifest))
        target = output / "images" / "header"
        target.mkdir(parents=True)
        banner = target / "december.png"
        banner.write_bytes(b"existing")
        for status in (400, 413, 415, 500, 502, 504):
            problem = {
                "title": "Banner generation failed", "status": status,
                "code": "SpeakerImageDownloadFailed", "detail": "Photo could not be downloaded.",
                "correlationId": f"test-correlation-{status}",
            }
            body = json.dumps(problem).encode()
            error = HTTPError(
                "https://example.com/api/banners/v1", status, "error",
                {"Content-Type": "application/problem+json"}, BytesIO(body),
            )
            build_opener.return_value.open.side_effect = error
            logs = StringIO()
            with self.subTest(status=status), patch.dict(
                banners.os.environ,
                {
                    "BANNER_SITE_BASE_URL": "https://www.azurethursday.com",
                    "BANNER_FUNCTION_URL": "https://example.com/api/banners/v1",
                },
            ), patch.object(
                banners.sys, "argv",
                ["generate_banners.py", "--source", str(self.root), "--output", str(output)],
            ), redirect_stderr(logs):
                self.assertEqual(banners.main(), 1)
                self.assertIn(body.decode(), logs.getvalue())
                self.assertIn(f"HTTP {status}", logs.getvalue())
                self.assertEqual(banner.read_bytes(), b"existing")
            self.assertTrue(error.closed)

    @patch.object(banners, "build_opener")
    def test_invalid_input_fails_main_before_any_posts(self, build_opener):
        self.event("invalid", "2026-12-03", sessions=[{"title": "Talk"}] * 4)
        output = self.root / "public"
        (output / "json").mkdir(parents=True)
        (output / "json" / "banner-events.json").write_text(json.dumps(self.manifest))
        logs = StringIO()
        with patch.dict(
            banners.os.environ, {"BANNER_SITE_BASE_URL": "https://www.azurethursday.com"},
        ), patch.object(
            banners.sys, "argv",
            ["generate_banners.py", "--source", str(self.root), "--output", str(output)],
        ), redirect_stderr(logs):
            self.assertEqual(banners.main(), 1)
        self.assertIn("maximum is 3", logs.getvalue())
        build_opener.assert_not_called()

    @patch.object(banners, "build_opener")
    def test_output_paths_cannot_escape_or_alias(self, build_opener):
        for requests, message in [
            ([(Path("..") / "outside.png", {})], "escapes the Hugo output"),
            ([(Path("same.png"), {}), (Path("same.png"), {})], "overwrite"),
        ]:
            with self.subTest(requests=requests):
                with self.assertRaisesRegex(ValueError, message):
                    banners.generate_banners(
                        requests, self.root / "public", "https://example.com/api/banners/v1"
                    )
                build_opener.assert_not_called()

    @patch.object(banners, "build_opener")
    def test_nested_encoded_paths_and_repeat_generation(self, build_opener):
        self.event(
            "december", "2026-12-03",
            headerImageUrl="/images/header/December%20meetup/banner.png",
        )
        output = self.root / "public"
        output.mkdir()
        unrelated = output / "unrelated.png"
        unrelated.write_bytes(b"untouched")
        for content in (b"first", b"second"):
            image = banners.PNG_SIGNATURE + content
            build_opener.return_value.open.return_value = self.response(image)
            banners.generate_banners(
                self.prepare(), output, "https://example.com/api/banners/v1"
            )
            self.assertEqual(
                (output / "images" / "header" / "December meetup" / "banner.png").read_bytes(),
                image,
            )
            self.assertEqual(unrelated.read_bytes(), b"untouched")
        self.assertEqual(build_opener.return_value.open.call_count, 2)

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
