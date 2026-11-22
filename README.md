# camera-card

A Home Assistant dashboard card for our Reolink cameras: recent recordings as a scrolling list,
one-tap playback, live view, and a camera grid. Start with the [product intent](docs/intent.md).

`alerts/` writes the sentence a phone alert says ("A man is leaving through the gate.") from
what a vision model sees in a camera's pictures. Home Assistant runs
`python3 alerts/describe.py SETTINGS.yaml CAMERA TRIGGER PICTURE...` and sends what it prints;
`alerts/example.yaml` shows a household's settings. Each run with pictures is one paid model
call, up to the settings' `daily_limit`. `uv run alerts/test_message.py` checks the wording rules
and costs nothing.

An event nobody is alerted about can still be described so the card can show it: the same
command with `--unpushed` first prints a sentence only when the camera's `describe` setting
covers the event, and nothing otherwise. Exit status 3 means the day's limit was just reached
and the printed line is the warning to send.

Both need `custom_components/reolink`: Home Assistant's own Reolink integration with our changes
on top, which plays NVR clips, keeps the recording lists fast, and serves what the card and alerts
ask for. Copy the folder into Home Assistant's `config/custom_components/` and restart; it takes the
place of the built-in integration, and deleting it brings the built-in one back. It is a copy of one
Home Assistant release (`"version"` in its `manifest.json`), so after upgrading Home Assistant run
`bin/integration-refresh <new version>` to carry our changes onto that release. Where Home Assistant
changed the same code we did, it stops and names the file to decide on. `bin/integration-refresh
--diff` shows everything that is ours.

```yaml
type: custom:camera-card
# optional: per NVR channel
names: {3: Gate & Shed}
entities: {0: camera.garage_fluent}
```

To link straight to a camera's live view, add `?live=<camera entity>` to the dashboard URL, e.g.
`homeassistant://navigate/dashboard-cameras/0?live=camera.backyard_fluent`.

The card is two files served side by side: `card/camera-card.js` and `card/hls.min.js`, the clip
player for browsers other than Safari.

The card shows every time as the clock at the house (Home Assistant's timezone), and names that zone
beside a time whenever the phone's clock reads differently. `node card/test_time.mjs` checks it.

Use it as the only card in a panel view. `bin/dev-push` tags the committed card as a
release candidate and installs it on the Home Assistant host (which restarts, ~1 min). It reads
where to deploy from a gitignored `.dev-push.env`; run it once to see what that file needs.
