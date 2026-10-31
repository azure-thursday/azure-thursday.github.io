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
Registration, artwork, venue and sessions can be added later. Authentication
options are described in [the CMS configuration](src/static/admin/config.yml).

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

The old `src/data/event.json` and `src/data/sessions.json` have been replaced by
the event pages. Hugo still generates `/json/event.json`, `/json/sessions.json`
and `/sessions/next.ics` from the same highlighted event for existing consumers.
With no upcoming event these return `{}`, `{"sessions":[]}` and an empty calendar
respectively, and the homepage shows a planning message.

### Validating changes

Build with `hugo --source src`. To test event selection at a specific instant:

```
hugo --source src --clock 2026-11-06T00:00:00+01:00
```

Run the event regression tests with Python 3 and Hugo on `PATH`:

```
python -m unittest discover -s tests -p "test_events.py"
```
