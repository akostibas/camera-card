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

It needs our patched copy of Home Assistant's Reolink integration (not in this repo yet), which
serves `/api/reolink/recordings`, `/api/reolink/still` and `/api/reolink/play`, and a tagged release
installed on the Home Assistant host.

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

Use it as the only card in a panel view. `bin/dev-push` tags the committed card as a
release candidate and installs it on the Home Assistant host (which restarts, ~1 min). It reads
where to deploy from a gitignored `.dev-push.env`; run it once to see what that file needs.
