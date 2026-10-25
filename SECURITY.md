# Credential-safe automation

Scheduled Arabic (سكينة يومية) and English (Daily Serenity) publishing continues with the same existing GitHub Actions Secrets, schedules and API calls. This change does not rotate credentials, change repository visibility or grant account permissions.

## Account connection is now local only

`serenity-connect`, `tiktok-connect`, and `youtube-reauth` now show instructions only. They do not accept codes/tokens, exchange credentials, or write secrets. GitHub workflow inputs and summaries are not a secure credential handoff; masking after submission does not remove retained event data.

From a private, trusted local terminal, install `requirements.txt` and run one of:

- `python tools/setup_meta.py`
- `python tools/setup_tiktok.py`
- `python tools/setup_youtube.py`

Do not pass credentials on the command line. The tools prompt privately and refuse CI/non-interactive execution. Supply a new private output file **outside the checkout**; it is created exclusively with mode 0600. Transfer the selected values to the existing Actions Secrets using GitHub Settings on your trusted device, then delete the local file. Do not upload the file or paste its contents into chat/issues/workflow inputs. Meta returns the available pages: choose the intended page rather than replacing every account. Use existing `EN_` secret names for Daily Serenity; use the existing unprefixed names for Arabic reels. For long videos the existing Arabic YouTube prefix is `AR_`.

The local YouTube helper requires an OAuth Desktop client and a registered loopback-compatible redirect. It requests upload/read-only scope as before; it is **not** a replacement for granting new playlist scope. If reconnecting a web-client or playlist-enabled account, use its provider-approved local OAuth flow and preserve required scope/channel binding. Never reuse the removed public workflow input route. Reconnection does not run automatically as part of this change.

## Diagnostics and artifacts

Provider response bodies, token fingerprints, exception text/tracebacks, and OAuth error descriptions are omitted from public diagnostics. Publishing errors in generated history contain an exception class only; HTTP status remains where safely available. TikTok's existing refresh-secret handoff remains local to the runner and is explicitly excluded from artifacts. Media/caption artifacts remain enabled.

These safeguards prevent future output paths after merge. They do not erase historical logs, artifacts, summaries, commits, or cached copies, or invalidate previously exposed credentials. Historical cleanup and credential rotation require a separate authorized action.

## Offline validation

`python -m unittest discover -s tests -v`

`python -m compileall -q src scripts tools`

Tests use synthetic canaries and mocked HTTP; no publishing, OAuth exchange or secret updates occur.
