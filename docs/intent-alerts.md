# Alerts: product intent

Part of the [product intent](intent.md). This is how we judge whether a change
to alerting moves it forward or backward.

**Who and why:** someone in the household with a phone in their pocket, at
home or away. The question is "do I need to look at this?", answered without
opening anything.

## Better means

- **Fewer pushes about nothing.** Less of what arrives turns out to be
  shadows, traffic, or an empty frame.
- **Less missed.** Fewer real visitors, pests, or open doors that never reach
  the phone.
- **More said in the push.** More often, reading the alert is enough and the
  footage stays closed.
- **More honest about doubt.** A vague alert that is right beats a specific
  one that is wrong.
- **Sooner.** Less time between the event and the push.
- **Less hand-tuning.** Staying accurate takes less of the household's time
  as cameras, seasons, and visitors change.
- **Cheaper.** Fewer paid model calls for the same result.
- **Less to it.** Fewer settings and moving parts, as long as nothing above
  gets worse.

## Floors

A change that breaks one of these is a regression, whatever else it improves:

- If the model is down or slow, a plain alert still arrives.
- Someone at the door is never kept waiting while footage is examined.
- Nothing is stated as fact below its confidence bar.

## Not progress

- The model watching continuously, or replacing the cameras' own detection.

## Fixed constraints

These hold today. A use case blocked by one is a reason to weigh the work to
lift it, not a dead end.

- An alert starts only when a camera's own detection fires. What the camera
  never notices, nobody hears about.
- The model sees a few still pictures from around that moment, not video.
- Describing an alert needs a paid model, and reaching the phone needs a push
  service.
