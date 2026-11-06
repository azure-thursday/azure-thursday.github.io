import argparse
from copy import deepcopy
from datetime import date
from http.client import HTTPException
import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_IMAGE_BYTES = 20 * 1024 * 1024


class BannerGenerationError(Exception):
    pass


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def prepare_requests(source, manifest, site_base_url):
    content = (source / "content").resolve()
    requests = []
    filenames = set()
    for entry in manifest["events"]:
        page = (content / entry["source"]).resolve()
        if not page.is_relative_to(content):
            raise ValueError("Banner manifest source must be inside the content directory.")
        params, _ = json.JSONDecoder().raw_decode(
            page.read_text(encoding="utf-8").lstrip()
        )
        event_date = date.fromisoformat(entry["eventDate"])
        if params["eventDate"] != entry["eventDate"]:
            raise ValueError(f"Event {entry['id']} changed after the Hugo build.")
        filename = event_date.strftime("%m-%Y") + ".png"
        if filename in filenames:
            raise ValueError(
                f"Multiple upcoming events would overwrite {filename}; "
                "monthly banner filenames require one event per month."
            )
        filenames.add(filename)
        expected_url = "/images/header/" + filename
        if params.get("headerImageUrl") not in (None, "", expected_url):
            raise ValueError(
                f"Event {entry['id']} must use headerImageUrl {expected_url}."
            )
        event = {
            "id": entry["id"],
            "title": params["title"],
            "eventDate": entry["eventDate"],
            "timeZone": "Europe/Amsterdam",
        }
        for key in ("meetupRegisterUrl", "location", "startsAt", "endsAt", "summary"):
            if params.get(key):
                event[key] = params[key]
        sessions = deepcopy(params.get("sessions", []))
        if sessions is None:
            sessions = []
        if not isinstance(sessions, list):
            raise ValueError(f"Event {entry['id']} sessions must be an array.")
        for session in sessions:
            if not isinstance(session, dict):
                raise ValueError(f"Event {entry['id']} sessions must contain objects.")
            session.setdefault("speakers", [])
            if not isinstance(session["speakers"], list):
                raise ValueError(f"Event {entry['id']} speakers must be an array.")
            for speaker in session["speakers"]:
                if not isinstance(speaker, dict):
                    raise ValueError(f"Event {entry['id']} speakers must contain objects.")
                if speaker.get("imageUrl"):
                    speaker["imageUrl"] = urljoin(
                        site_base_url.rstrip("/") + "/", speaker["imageUrl"]
                    )
                    image_url = urlsplit(speaker["imageUrl"])
                    if image_url.scheme != "https" or not image_url.hostname:
                        raise ValueError(
                            f"Event {entry['id']} requires HTTPS speaker image URLs."
                        )
        requests.append(
            (filename, {"schemaVersion": 1, "event": event, "sessions": sessions})
        )
    return requests


def generate_banners(requests, output, endpoint):
    if not requests:
        print("No upcoming events; no banners to generate.")
        return
    endpoint_url = urlsplit(endpoint)
    if endpoint_url.scheme != "https" or not endpoint_url.hostname:
        raise ValueError("BANNER_FUNCTION_URL must be an absolute HTTPS endpoint.")
    opener = build_opener(NoRedirects())
    target = output / "images" / "header"
    target.mkdir(parents=True, exist_ok=True)
    for filename, payload in requests:
        request = Request(
            endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "image/png",
            },
            method="POST",
        )
        try:
            with opener.open(request, timeout=120) as response:
                if response.status != 200:
                    raise BannerGenerationError(
                        f"{filename}: expected HTTP 200, received {response.status}."
                    )
                if response.headers.get_content_type() != "image/png":
                    raise BannerGenerationError(f"{filename}: expected image/png.")
                image = response.read(MAX_IMAGE_BYTES + 1)
        except HTTPError as error:
            raise BannerGenerationError(
                f"{filename}: Function returned HTTP {error.code}."
            ) from None
        except (URLError, TimeoutError, OSError, HTTPException) as error:
            raise BannerGenerationError(
                f"{filename}: Function request failed ({type(error).__name__})."
            ) from None
        if len(image) > MAX_IMAGE_BYTES:
            raise BannerGenerationError(f"{filename}: banner exceeds 20 MiB.")
        if not image.startswith(PNG_SIGNATURE) or len(image) <= len(PNG_SIGNATURE):
            raise BannerGenerationError(f"{filename}: response is not a PNG.")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=target, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(image)
            temporary.replace(target / filename)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        print(f"Generated images/header/{filename}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("src"))
    parser.add_argument("--output", type=Path, default=Path("src") / "public")
    args = parser.parse_args()
    try:
        manifest = json.loads(
            (args.output / "json" / "banner-events.json").read_text(encoding="utf-8")
        )
        requests = prepare_requests(
            args.source, manifest, os.environ["BANNER_SITE_BASE_URL"]
        )
        generate_banners(
            requests,
            args.output,
            os.environ.get("BANNER_FUNCTION_URL", ""),
        )
    except (BannerGenerationError, ValueError, KeyError, OSError) as error:
        print(f"Banner generation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
