# camera-card

A Home Assistant dashboard card for our Reolink cameras: recent recordings as a scrolling list,
one-tap playback, live view, and a camera grid. Start with the [product intent](docs/intent.md).

`alerts/` turns a vision model's answers about a camera's pictures into the sentence a phone alert
says ("A man is leaving through the gate."). `alerts/example.yaml` shows a household's settings;
`uv run alerts/test_message.py` checks the wording rules. Nothing sends alerts from here yet.

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

Use it as the only card in a panel view. `bin/dev-push` tags the committed card as a
release candidate and installs it on the Home Assistant host (which restarts, ~1 min). It reads
where to deploy from a gitignored `.dev-push.env`; run it once to see what that file needs.
