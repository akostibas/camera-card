# Camera card: product intent

This is how we judge whether a change to the card moves it forward or
backward. It names what we value, not how to deliver it.

**Who and why:** our household, usually on an iPhone (Safari or the Home
Assistant app), sometimes on a desktop. The question is "what happened around
the house, and what's happening now?" It replaces our fork of Advanced Camera
Card (family-infra #299).

## Use cases

Score a change by how it affects these. A change that makes any of them
slower, harder, or less certain is moving backward.

1. **"I heard a noise outside. What was it?"** It happened seconds or minutes
   ago, and it may still be going on. You don't know which camera saw it.
2. **"Something knocked the trash cans over. What happened?"** It happened
   sometime overnight, on a camera you can probably guess. You're looking for
   one event in hours of time.
3. **"Who rang the doorbell this morning?"** One camera, a rough window, and you
   want to see a face.
4. **"What's going on in <place> right now?"** You know where, but nothing has
   necessarily happened there. Answering it shouldn't need any other screen.
5. **"Rats chewed through something in the crawl space. When did they do
   that?"** One camera, but it could have been a month or more ago. You're
   looking for one event across weeks of recordings.
6. **Stretch: "When did <person> leave?"** You're looking for one particular
   person walking out of the gate or front door, among everyone else who came
   and went.

## Better means

- **Less time to understand.** It takes less time to know when and where there
  was activity, and where there wasn't.
- **Less effort to watch.** Getting from "something happened there" to watching
  it takes fewer steps, less precision, and less hunting.
- **Less distance between past and present.** Getting to what a camera sees
  right now is no harder than watching what it saw.
- **Narrowing is easier.** It's easier to focus on one kind of event, such as
  people, or on one stretch of time, including days past.
- **Keeping is easier.** It's easier to save a recording off the device.
- **More at home on a phone.** It feels more like the phone's own apps: faster
  under your finger, video that behaves the way video does elsewhere on the
  phone, and nothing covering the phone's own controls.
- **Calmer.** Less jumping, resizing, flashing, and fewer surprises.
- **Less to it.** Less code, fewer settings, fewer moving parts, as long as
  nothing above gets worse.

## Floors

A change that breaks one of these is a regression, whatever else it improves:

- The day's activity is fully shown within 5 seconds of opening, or 10 seconds
  on the first open after a Home Assistant restart.
- Another day appears within 2 seconds of asking for it.
- A recording starts within 5 seconds of choosing it.
- New activity shows up within 2 minutes.

## Not progress

These don't count as moving forward, and they shouldn't cost anything above:

- Serving other households, camera brands, or setups.
- Controlling the cameras: moving them, talking through them, or answering the
  doorbell.

## Fixed constraints

- Recordings reach the card only through Home Assistant, via our patched
  Reolink integration in family-infra. Fetching, caching, and detection tags
  live there.
- family-infra deploys the card from a pinned release.
