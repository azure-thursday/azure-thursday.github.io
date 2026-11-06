# azure-thursday.github.io
Azure Thursday Website

The site stays static: Hugo builds the pages and GitHub Pages hosts them.
Sveltia CMS edits content in GitHub; no application server or database is needed.

## Getting started
### Prerequisites
- Download and install Go: https://go.dev/dl/
- Download and install Hugo: https://gohugo.io/installation/
- Set up Hugo module by running this in the terminal in the root of the Hugo project
```
hugo mod init github.com/azure-thursday/azure-thursday.github.io
```

### Running Hugo
- Run Hugo static website generation by running this in the terminal in the root (/src) of the Hugo project
```
hugo
```

### View site locally
- Run the Hugo site locally by running this in the terminal in the root (/src) of the Hugo project
```
hugo serve
```

## Planning events

Open `/admin/` on the site and select **Events** in Sveltia CMS. Create an event,
set its event date, then turn off **Draft** when it is ready to advertise.
Registration, venue and sessions can be added later. Before publishing, set a
unique PNG `headerImageUrl`, such as `/images/header/2026-12-03.png`; deployment
generates the artwork at that path. Authentication options are described in
[the CMS configuration](src/static/admin/config.yml).

Each event is stored in [src/content/events](src/content/events) as a Markdown
page with JSON front matter. Use `eventDate: "YYYY-MM-DD"`, **not** Hugo's reserved
`date` or `publishDate`: those can hide future pages until their publication date.
Keep `layout: "event"` and `outputs: ["HTML", "Calendar"]`. Published events are
visible immediately, even when their event dates are months away.

- The earliest published event on or after today in **Europe/Amsterdam** gets the
  homepage registration button, artwork and sessions. It stays highlighted through
  its event day; drafts never enter the spotlight, list or calendar.
- The homepage previews the next three later events. `/events/` lists every
  upcoming event in date order, with individual event pages for sharing.
  The homepage's **Upcoming events** section sits below the sessions and above
  the sponsors, with date tiles, venue details and links to each event and the
  full event list. The list's banner cards use two columns from 768px wide and
  one column on smaller screens.
- `/events/index.ics` is a subscribable upcoming-event calendar. Each event also
  has its own `index.ics` download. Subscribe using the full site URL in your
  calendar app; downloading/importing a file is a one-time copy, not a subscription.
- Set both `startsAt` and `endsAt` to ISO timestamps with explicit UTC offsets
  when event times are known, e.g. `2026-11-05T18:00:00+01:00`. The start must fall
  on `eventDate` in Amsterdam and the end must be later. Use `+02:00` during Dutch
  summer time. Without both timestamps, the calendar advertises an all-day
  placeholder rather than guessing times from the talks.
- Past event pages remain shareable but drop out of the upcoming list. The
  existing `/events/past/` recordings archive and its CMS collections are
  unchanged; adding recordings to that archive remains an editorial step.
  Monthly archive JSONs in `src/data` use `MM-YYYY.json` filenames matching their
  event dates. Add each key to `pasteventsindex.json` in newest-first order and
  register the file in the CMS's **Past Event Sessions** collection.

The deployment workflow rebuilds daily as well as on pushes so the spotlight
advances without an edit. GitHub scheduled runs can be delayed and can be disabled
after 60 days of inactivity in public repositories; monitor Actions and use
**Run workflow** if needed. Calendar clients control how frequently subscriptions
refresh.

Hugo generates `/json/event.json`, `/json/sessions.json` and `/sessions/next.ics`
from the highlighted event. During deployment, the workflow overwrites the two
JSON feeds with the manually maintained `src/data/event.json` and
`src/data/sessions.json` files after the build. Update both data files when
changing the event advertised to existing JSON consumers; they do not roll over
automatically. Event pages still control the homepage and calendars, independently
of these JSON overrides. Local Hugo builds do not apply the deployment overrides.
With no upcoming event the homepage shows a planning message and the generated
calendar is empty.

### Generating event banners

The Pages deployment workflow POSTs one request per published upcoming event
to the banner Function after Hugo builds and before uploading the artifact.
It uses Hugo's event selection, including the current event through its day in
Europe/Amsterdam, and never uses the two manually maintained JSON feeds.

Configure this repository Actions secret:

- `BANNER_FUNCTION_URL`: the full HTTPS POST endpoint, e.g.
  `https://azurethursdaybanner.azurewebsites.net/api/banners/v1`.

The Function endpoint is anonymous; requests do not include an authentication
header or require a Function key.

The request is `{"schemaVersion":1,"event":{...},"sessions":[...]}`. Event fields
include `id` (the event filename without `.md`), `title`, ISO `eventDate`,
`timeZone: "Europe/Amsterdam"` and any supplied registration URL, location,
timestamps and summary. Session and speaker fields retain their source names;
relative speaker photo URLs become absolute URLs using the Pages base URL.
There may be at most three sessions per event and two speakers per session;
invalid counts, empty titles and unsupported event time zones fail before
any requests are sent. Empty sessions and speaker arrays remain supported.
The Function must return HTTP 200 with `Content-Type: image/png` and raw PNG
bytes, not JSON, base64 or a storage URL. Each request has a 120-second timeout
and responses are limited to 20 MiB. Redirects and failed or invalid responses
fail deployment; existing banners are not silently used as a fallback.
Non-200 responses log the full problem body, including its error `code` and
`correlationId`, to help diagnose generation and speaker-photo failures.

Generated images are saved at each event's required `headerImageUrl` inside
the deployment artifact. Use a root-relative PNG path, such as
`/images/header/2026-12-03.png`. Paths must not contain traversal segments,
queries or fragments, and must be distinct for every upcoming event.
Multiple events in the same month are supported. Existing monthly filenames
remain valid as long as no other upcoming event uses the same path.
Missing paths and collisions fail before any requests are sent.
No images are committed back to GitHub, and local Hugo builds continue to use
the checked-in artwork. With no upcoming events no Function requests are made.

Speaker photos must already be accessible at their HTTPS URLs when generation
runs; photos first introduced in the pending deployment are not yet available
on the live site. Publish those photos beforehand or extend the Function
contract to support uploaded image data.

### Validating changes

Build with `hugo --source src`. To test event selection at a specific instant:

```
hugo --source src --clock 2026-11-06T00:00:00+01:00
```

Run the event regression tests with Python 3 and Hugo on `PATH`:

```
python -m unittest discover -s tests -p "test_events.py"
```

Run the event and banner-generation tests together:

```
python -m unittest discover -s tests -p "test_*.py"
```
