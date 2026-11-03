# camera-card

A Home Assistant dashboard card for our Reolink cameras: recent recordings as a scrolling list,
one-tap playback, live view, and a camera grid. Start with the [product intent](docs/intent.md).

It needs the family-infra Reolink override (#299), which serves `/api/reolink/recordings`,
`/api/reolink/still` and `/api/reolink/play`, and family-infra installing a tagged release on cherry.

```yaml
type: custom:camera-card
# optional: per NVR channel
names: {3: Gate & Shed}
entities: {0: camera.garage_fluent}
```

Use it as the only card in a panel view. `bin/dev-push` tags the committed card as a
release candidate and has family-infra install it on cherry (Home Assistant restarts, ~1 min).
