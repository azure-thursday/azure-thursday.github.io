# azure-thursday.github.io
Azure Thursday Website

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

## Sveltia CMS: sign-in

### Access token (current setup)

No OAuth service or configuration change is needed for token sign-in:

1. Open `/admin/` and choose **Sign In Using Access Token**.
2. Use the **GitHub user settings page** link in the dialog to create a
   fine-grained personal access token.
3. Select **azure-thursday** as the resource owner and limit repository access
   to **azure-thursday.github.io**. Choose an expiration, such as 30 days.
4. Grant **Repository permissions > Contents: Read and write**.
   Metadata read access is added automatically. Our current direct-to-main
   workflow does not need Pull requests or Workflows permissions.
   If editorial review is enabled later, add **Pull requests: Read and write**.
5. Generate the token and paste it only into Sveltia's **Personal Access Token**
   field. Do not share it in chat, commit it, or put it in the CMS configuration.
6. Sign in and open an event to confirm repository access. Publishing an intended
   edit commits it to remote `main` and triggers the Hugo deployment workflow.

The token cannot grant more access than your GitHub account already has. If the
organization requires token approval, an owner must approve it before it can
write repository content. Sveltia stores the token in the browser's local
storage; use a trusted browser, and revoke the token in GitHub when no longer
needed or if it is exposed. Create a replacement when it expires.

### GitHub OAuth (optional)

The **Sign In with GitHub** button needs an OAuth authenticator. GitHub Pages
cannot run that service itself. Until it is configured, use **Sign In Using
Access Token**, or **Work with Local Repository** when editing locally.

Use the official [Sveltia CMS Authenticator](https://github.com/sveltia/sveltia-cms-auth)
on Cloudflare Workers:

1. [Deploy the authenticator to Cloudflare](https://deploy.workers.cloudflare.com/?url=https://github.com/sveltia/sveltia-cms-auth).
   Record its HTTPS Worker URL.
2. [Create a GitHub OAuth app](https://github.com/settings/applications/new).
   Use `Azure Thursday Content Manager` as the name, the site's public URL as
   the homepage, and **the Worker URL followed by `/callback`** as the
   authorization callback URL. Do not use the site's `/admin/` URL as the callback.
3. In the Worker's **Settings > Variables and Secrets**, configure:
   - `GITHUB_CLIENT_ID`: the OAuth app's client ID.
   - `GITHUB_CLIENT_SECRET`: the generated client secret, stored as an encrypted
     secret. Never put it in this repository or share it in chat.
   - `ALLOWED_DOMAINS`: `www.azurethursday.com,azurethursday.com,azure-thursday.github.io`.
     For local OAuth testing, also add `127.0.0.1,localhost`. These are hostnames,
     without schemes, paths or ports. Avoid wildcard access.
   Leave `GITHUB_ALLOW_WORKFLOW_SCOPE` unset; content editing does not need it.
   Save and deploy the Worker configuration.
4. Set `backend.base_url` in [the CMS configuration](src/static/admin/config.yml)
   to the Worker's HTTPS origin, without `/callback` or `/auth`. Commit and deploy
   this site change.
5. Open `/admin/`, choose **Sign In with GitHub**, and authorize the app. If the
   GitHub organization restricts OAuth apps, an organization owner must approve
   its access. Editors still need permission to write to this repository.
6. Verify an event loads in the editor, then publish an intended content change
   and confirm the GitHub commit and successful Hugo deployment.

OAuth authenticates GitHub access; it does not change the content architecture.
Both GitHub login methods target the remote `main` branch, even from a local
Hugo preview. **Work with Local Repository** instead edits the folder you select;
those changes must be committed and pushed separately.

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
