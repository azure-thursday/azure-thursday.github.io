import argparse
from copy import deepcopy
from datetime import date
from http.client import HTTPException
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlsplit
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
    paths = set()
    for entry in manifest["events"]:
        event_id = entry["id"]
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("Banner event id must be a nonempty string.")
        page = (content / entry["source"]).resolve()
        if not page.is_relative_to(content):
            raise ValueError("Banner manifest source must be inside the content directory.")
        params, _ = json.JSONDecoder().raw_decode(
            page.read_text(encoding="utf-8").lstrip()
        )
        if (
            not isinstance(entry["eventDate"], str)
            or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", entry["eventDate"])
        ):
            raise ValueError(f"Event {event_id} requires eventDate in YYYY-MM-DD format.")
        date.fromisoformat(entry["eventDate"])
        if params["eventDate"] != entry["eventDate"]:
            raise ValueError(f"Event {entry['id']} changed after the Hugo build.")
        path = banner_path(params.get("headerImageUrl"), event_id)
        normalized_path = os.path.normcase(str(path))
        if normalized_path in paths:
            raise ValueError(
                f"Multiple upcoming events would overwrite {path.as_posix()}; "
                "each event requires a distinct headerImageUrl."
            )
        paths.add(normalized_path)
        if not isinstance(params.get("title"), str) or not params["title"].strip():
            raise ValueError(f"Event {event_id} requires a nonempty title.")
        if params.get("timeZone", "Europe/Amsterdam") != "Europe/Amsterdam":
            raise ValueError(f"Event {event_id} only supports timeZone Europe/Amsterdam.")
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
        if len(sessions) > 3:
            raise ValueError(f"Event {event_id} has {len(sessions)} sessions; maximum is 3.")
        for session in sessions:
            if not isinstance(session, dict):
                raise ValueError(f"Event {entry['id']} sessions must contain objects.")
            if not isinstance(session.get("title"), str) or not session["title"].strip():
                raise ValueError(f"Event {event_id} requires a nonempty session title.")
            session.setdefault("speakers", [])
            if not isinstance(session["speakers"], list):
                raise ValueError(f"Event {entry['id']} speakers must be an array.")
            if len(session["speakers"]) > 2:
                raise ValueError(
                    f"Event {event_id} session {session['title']} has "
                    f"{len(session['speakers'])} speakers; maximum is 2."
                )
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
            (path, {"schemaVersion": 1, "event": event, "sessions": sessions})
        )
    return requests


def banner_path(header_url, event_id):
    if not isinstance(header_url, str) or not header_url.startswith("/"):
        raise ValueError(f"Event {event_id} requires a root-relative PNG headerImageUrl.")
    url = urlsplit(header_url)
    decoded = unquote(url.path, errors="strict")
    segments = decoded[1:].split("/")
    if (
        url.scheme or url.netloc or url.query or url.fragment
        or not decoded.startswith("/") or decoded.startswith("//")
        or any(part in ("", ".", "..") for part in segments)
        or any(char in decoded for char in '\\:*?"<>|')
        or any(ord(char) < 32 for char in decoded)
        or PurePosixPath(decoded).suffix.lower() != ".png"
    ):
        raise ValueError(
            f"Event {event_id} headerImageUrl must be a local PNG path without "
            "queries, fragments or unsafe path segments."
        )
    return Path(*segments)


def response_failure(path, response):
    message = f"{path.as_posix()}: Function returned HTTP {response.status}."
    try:
        body = response.read().decode("utf-8", errors="replace")
    except (URLError, TimeoutError, OSError, HTTPException) as error:
        return BannerGenerationError(
            f"{message} Could not read the problem response ({type(error).__name__})."
        )
    return BannerGenerationError(f"{message}\n{body}")


def generate_banners(requests, output, endpoint):
    if not requests:
        print("No upcoming events; no banners to generate.")
        return
    endpoint_url = urlsplit(endpoint)
    if endpoint_url.scheme != "https" or not endpoint_url.hostname:
        raise ValueError("BANNER_FUNCTION_URL must be an absolute HTTPS endpoint.")
    root = output.resolve()
    destinations = []
    seen = set()
    for path, payload in requests:
        target = (root / path).resolve()
        if not target.is_relative_to(root):
            raise ValueError(f"Banner path {path} escapes the Hugo output directory.")
        if target in seen:
            raise ValueError(f"Multiple upcoming events would overwrite {path}.")
        seen.add(target)
        destinations.append((path, target, payload))
    opener = build_opener(NoRedirects())
    for path, target, payload in destinations:
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
                    raise response_failure(path, response)
                if response.headers.get("Content-Type") != "image/png":
                    raise BannerGenerationError(f"{path.as_posix()}: expected image/png.")
                image = response.read(MAX_IMAGE_BYTES + 1)
        except HTTPError as error:
            with error:
                raise response_failure(path, error) from None
        except (URLError, TimeoutError, OSError, HTTPException) as error:
            raise BannerGenerationError(
                f"{path.as_posix()}: Function request failed ({type(error).__name__})."
            ) from None
        if len(image) > MAX_IMAGE_BYTES:
            raise BannerGenerationError(f"{path.as_posix()}: banner exceeds 20 MiB.")
        if not image.startswith(PNG_SIGNATURE) or len(image) <= len(PNG_SIGNATURE):
            raise BannerGenerationError(f"{path.as_posix()}: response is not a PNG.")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(image)
            temporary.replace(target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        print(f"Generated {path.as_posix()}")


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
