import json
import os
import re
from html import unescape
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class EventTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hugo = shutil.which(os.environ.get("HUGO_BINARY", "hugo"))
        if not cls.hugo:
            raise RuntimeError("Install Hugo or set HUGO_BINARY to its executable.")
        cls.temp = tempfile.TemporaryDirectory(prefix="azure-thursday-events-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.source = cls.root / "src"
        repo = Path(__file__).resolve().parents[1]
        shutil.copytree(
            repo / "src",
            cls.source,
            ignore=shutil.ignore_patterns("static", "public", "resources", ".hugo_build.lock"),
        )
        cls.fixture(
            "2026-12-03",
            title="December event",
            eventDate="2026-12-03",
            startsAt="2026-12-03T18:00:00+01:00",
            endsAt="2026-12-03T21:00:00+01:00",
            summary="Plan, learn; share\n" + "Azure café " * 20,
            location="Utrecht, Netherlands",
        )
        cls.fixture("2027-01-07", title="January event", eventDate="2027-01-07")
        cls.fixture(
            "2026-11-01-draft",
            title="Unannounced draft",
            eventDate="2026-11-01",
            draft=True,
        )
        cls.fixture("2026-09-03", title="Expired event", eventDate="2026-09-03")
        cls.outputs = {}
        for name, clock, flags in [
            ("before", "2026-10-31T21:36:48+01:00", []),
            ("during", "2026-11-05T23:59:59+01:00", []),
            ("after", "2026-11-06T00:00:00+01:00", []),
            ("empty", "2027-01-08T00:00:00+01:00", []),
            ("drafts", "2026-10-31T21:36:48+01:00", ["--buildDrafts"]),
            ("utc-boundary", "2026-11-05T23:00:00Z", []),
            ("minified", "2026-10-31T21:36:48+01:00", ["--minify"]),
            ("last", "2027-01-07T12:00:00+01:00", []),
        ]:
            output = cls.root / name
            cls.build(output, clock, flags)
            cls.outputs[name] = output

    @classmethod
    def fixture(cls, slug, **params):
        values = dict(layout="event", outputs=["HTML", "Calendar"], draft=False)
        values.update(params)
        (cls.source / "content" / "events" / (slug + ".md")).write_text(
            json.dumps(values, ensure_ascii=False), encoding="utf-8"
        )

    @classmethod
    def build(cls, output, clock, flags=(), check=True):
        result = subprocess.run(
            [
                cls.hugo,
                "--source", str(cls.source),
                "--destination", str(output),
                "--baseURL", "https://www.azurethursday.com/",
                "--clock", clock,
                *flags,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if check and result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        return result

    def read(self, case, path):
        return (self.outputs[case] / path).read_text(encoding="utf-8")

    def test_current_event_and_compatibility_outputs(self):
        home = self.read("before", "index.html")
        self.assertIn('datetime="2026-11-05"', home)
        self.assertIn("/images/header/11-2026.png", home)
        self.assertIn("AVM Is Great. Here", home)
        self.assertIn("316792750", home)
        self.assertIn("/events/2026-11-05/index.ics", home)
        event = json.loads(self.read("before", "json/event.json"))
        self.assertEqual(event["nextEventDate"], "05/11/2026")
        sessions = json.loads(self.read("before", "json/sessions.json"))["sessions"]
        self.assertEqual(len(sessions), 2)
        self.assertEqual(sessions[0]["slug"], "avm-is-great")
        self.assertEqual(
            self.read("before", "sessions/next.ics"),
            self.read("before", "events/2026-11-05/index.ics"),
        )

    def test_ordering_and_drafts(self):
        for case in ("before", "drafts"):
            listing = self.read(case, "events/index.html")
            self.assertLess(listing.index("November 2026"), listing.index("December event"))
            self.assertLess(listing.index("December event"), listing.index("January event"))
            self.assertNotIn("Unannounced draft", listing)
            self.assertNotIn("Expired event", listing)
            self.assertNotIn("Unannounced draft", self.read(case, "index.html"))
            calendar = self.read(case, "events/index.ics")
            self.assertEqual(calendar.count("BEGIN:VEVENT"), 3)
            self.assertNotIn("Unannounced draft", calendar)
            self.assertNotIn("Expired event", calendar)

    def test_current_sponsors(self):
        home = self.read("before", "index.html")
        self.assertIn('alt="Logo Heroes"', home)
        self.assertIn('alt="Logo Sopra Steria"', home)
        self.assertIn('src="/images/bbtg-logo.svg" alt="Logo BBTG"', home)
        self.assertNotIn('alt="Logo XPRTZ"', home)
        self.assertNotIn('alt="Logo Rubicon"', home)

    def test_past_event_index_covers_monthly_jsons(self):
        data = self.source / "data"
        entries = json.loads((data / "pasteventsindex.json").read_text(encoding="utf-8"))["events"]
        keys = [entry["key"] for entry in entries]
        monthly_keys = {path.stem for path in data.glob("*.json") if re.fullmatch(r"\d{2}-\d{4}", path.stem)}
        self.assertEqual(set(keys), monthly_keys)
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(keys, sorted(keys, key=lambda key: (key[3:], key[:2]), reverse=True))
        self.assertEqual(keys[:2], ["10-2026", "05-2026"])
        archive = self.read("before", "events/past/index.html")
        self.assertEqual(archive.count('<div class="past-event">'), len(keys))
        previous = -1
        for key in keys:
            sessions = json.loads((data / (key + ".json")).read_text(encoding="utf-8"))["sessions"]
            self.assertTrue(sessions, key)
            title = '<div class="past-event-title">' + sessions[0]["meetup"] + "</div>"
            position = archive.index(title)
            self.assertGreater(position, previous)
            previous = position
            for session in sessions:
                self.assertIn(session["title"], unescape(archive))

    def test_homepage_upcoming_events_section(self):
        for case in ("before", "drafts"):
            home = self.read(case, "index.html")
            section = re.search(
                r'<section class="container-fluid events-section homepage-upcoming-events"[^>]*>(.*?)</section>',
                home,
                re.DOTALL,
            )
            self.assertIsNotNone(section)
            self.assertIn('href="/events/2026-12-03/"', section[1])
            self.assertIn("3 December 2026", section[1])
            self.assertIn("Utrecht, Netherlands", section[1])
            self.assertNotIn("November", section[1])
            self.assertIn('href="/events/"', section[1])
            self.assertIn("All upcoming events", section[1])
            self.assertEqual(section[1].count('<article class="upcoming-event-preview">'), 2)
            self.assertLess(home.index('<h2 class="sessions-title">Sessions</h2>'), section.start())
            self.assertLess(section.start(), home.index("Our sponsors"))
            self.assertNotIn("Plan ahead", home)
            self.assertNotIn("upcoming-event-teaser", home)
        home = self.read("after", "index.html")
        section = re.search(
            r'<section class="container-fluid events-section homepage-upcoming-events"[^>]*>(.*?)</section>',
            home,
            re.DOTALL,
        )
        self.assertIsNotNone(section)
        self.assertIn('href="/events/2027-01-07/"', section[1])
        self.assertIn("7 January 2027", section[1])
        self.assertNotIn("upcoming-event-location", section[1])
        for case in ("last", "empty"):
            home = self.read(case, "index.html")
            self.assertNotIn('class="upcoming-event-preview"', home)
            self.assertIn("More event dates will be announced soon.", home)
            self.assertIn('href="/events/"', home)

    def test_amsterdam_midnight_rollover_and_session_isolation(self):
        during = json.loads(self.read("during", "json/event.json"))
        self.assertEqual(during["nextEventDate"], "05/11/2026")
        for case in ("after", "utc-boundary"):
            event = json.loads(self.read(case, "json/event.json"))
            self.assertEqual(event["nextEventDate"], "03/12/2026")
            home = self.read(case, "index.html")
            self.assertNotIn("AVM Is Great", home)
            self.assertNotIn("316792750", home)
            self.assertNotIn("/images/header/11-2026.png", home)
            self.assertEqual(json.loads(self.read(case, "json/sessions.json")), {"sessions": []})
            self.assertEqual(self.read(case, "events/index.ics").count("BEGIN:VEVENT"), 2)

    def test_placeholder_and_persistent_past_detail(self):
        listing = self.read("before", "events/index.html")
        self.assertIn("AVM Is Great", listing)
        details = self.read("before", "events/2027-01-07/index.html")
        self.assertIn("Sessions and speakers will be announced", details)
        self.assertNotIn(">Register</a>", details)
        self.assertIn("AVM Is Great", self.read("after", "events/2026-11-05/index.html"))
        self.assertIn("past-event", self.read("before", "events/past/index.html"))

    def test_minified_deployment_preserves_feeds(self):
        for path in ("events/index.ics", "sessions/next.ics"):
            self.assertEqual(
                (self.outputs["before"] / path).read_bytes(),
                (self.outputs["minified"] / path).read_bytes(),
            )
        for path in ("json/event.json", "json/sessions.json"):
            self.assertEqual(
                json.loads(self.read("before", path)),
                json.loads(self.read("minified", path)),
            )

    def test_summer_time_and_midnight(self):
        summer_path = self.source / "content" / "events" / "summer.md"
        try:
            self.fixture(
                "summer",
                title="Summer event",
                eventDate="2027-07-01",
                startsAt="2027-07-01T18:00:00+02:00",
                endsAt="2027-07-01T21:00:00+02:00",
            )
            output = self.root / "summer"
            self.build(output, "2027-07-01T21:59:59Z")
            calendar = (output / "events" / "index.ics").read_text()
            self.assertIn("DTSTART:20270701T160000Z", calendar)
            self.assertIn("DTEND:20270701T190000Z", calendar)
            self.build(output, "2027-07-01T22:00:00Z")
            self.assertNotIn("BEGIN:VEVENT", (output / "events" / "index.ics").read_text())
        finally:
            summer_path.unlink(missing_ok=True)

    def test_no_upcoming_events(self):
        home = self.read("empty", "index.html")
        self.assertIn("Our next event is being planned", home)
        self.assertNotIn("Next event:", home)
        self.assertNotIn("AVM Is Great", home)
        self.assertEqual(json.loads(self.read("empty", "json/event.json")), {})
        self.assertEqual(json.loads(self.read("empty", "json/sessions.json")), {"sessions": []})
        for path in ("sessions/next.ics", "events/index.ics"):
            calendar = self.read("empty", path)
            self.assertIn("BEGIN:VCALENDAR", calendar)
            self.assertNotIn("BEGIN:VEVENT", calendar)

    def test_calendar_wire_format(self):
        calendar = (self.outputs["before"] / "events/index.ics").read_bytes()
        self.assertTrue(calendar.endswith(b"\r\n"))
        self.assertNotIn(b"\n", calendar.replace(b"\r\n", b""))
        self.assertTrue(all(len(line) <= 75 for line in calendar.split(b"\r\n")))
        text = calendar.decode("utf-8").replace("\r\n ", "")
        self.assertIn("DTSTART;VALUE=DATE:20261105", text)
        self.assertIn("DTEND;VALUE=DATE:20261106", text)
        self.assertIn("DTSTART:20261203T170000Z", text)
        self.assertIn("DTEND:20261203T200000Z", text)
        self.assertIn(r"DESCRIPTION:Plan\, learn\; share\nAzure café", text)
        self.assertIn(r"LOCATION:Utrecht\, Netherlands", text)
        uids = [line for line in text.splitlines() if line.startswith("UID:")]
        self.assertEqual(len(uids), len(set(uids)))
        self.assertIn("UID:2026-11-05@azurethursday.com", text)

    def test_invalid_dates_and_times_fail_explicitly(self):
        bad_path = self.source / "content" / "events" / "invalid.md"
        for params, message in [
            (dict(eventDate="03/12/2026"), "requires eventDate"),
            (dict(eventDate="2026-12-03", startsAt="2026-12-03T18:00:00+01:00"), "requires both"),
            (
                dict(eventDate="2026-12-03", startsAt="2026-12-03T18:00:00", endsAt="2026-12-03T21:00:00"),
                "offset-aware",
            ),
            (
                dict(eventDate="2026-12-03", startsAt="2026-12-03T21:00:00+01:00", endsAt="2026-12-03T18:00:00+01:00"),
                "end after start",
            ),
        ]:
            with self.subTest(params=params):
                try:
                    self.fixture("invalid", title="Invalid event", **params)
                    result = self.build(self.root / "invalid", "2026-10-31T12:00:00+01:00", check=False)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(message, result.stdout + result.stderr)
                finally:
                    bad_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
