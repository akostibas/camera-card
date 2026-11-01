# Camera card: product intent

Our household's way to answer, from a phone in a few seconds: **"what happened
around the house, and what's happening now?"**

It serves one home: our Reolink cameras, viewed mostly on iPhones (Safari and
the Home Assistant app), sometimes on a desktop. It replaces our fork of
Advanced Camera Card, whose general-purpose features kept getting in the way
(family-infra #299).

## What it's for

- **See activity at a glance.** Without tapping anything, you can tell when and
  where there was activity, and which stretches were quiet.
- **Watch what happened with no fiddling.** Getting from "something happened
  there" to watching it is one effortless action. Nothing needs precise
  aiming, and nothing needs searching inside a recording to find the start.
- **See what's happening now.** Switching from the past to a live view of any
  camera is as easy as watching a recording.
- **Find a specific kind of event.** For example, only the times a person was
  seen.
- **Look back in time.** Reaching an earlier day, or a narrower slice of one, is
  as easy as looking at today.
- **Keep what matters.** A recording worth keeping can be saved off the device
  without any hassle.

## How it should feel

- **Fast.** The day's activity is fully shown within 5 seconds of opening (aim
  for 2), or 10 seconds on the first open after a Home Assistant restart.
  Another day appears within 2 seconds of asking for it. A recording starts
  within 5 seconds of choosing it. New activity shows up within 2 minutes.
- **Native on an iPhone.** It responds to your finger without lag. Video plays
  the way video plays elsewhere on the phone: it starts on its own, and the
  phone's own player controls are never covered and only appear when wanted.
- **Calm.** The page never jumps, resizes, or flashes errors over a recording
  that is actually playing.

## Non-goals

- Serving other households, camera brands, or setups. Our cameras are the only
  case that matters.
- Controlling the cameras: moving them, talking through them, or answering the
  doorbell.
- Replacing the always-on live tiles elsewhere on the dashboard.

## Signs it's malfunctioning

- You open it and can't tell within a few seconds what happened today.
- You meant to watch something and got nothing, the wrong camera, or the
  middle of a recording.
- A recording needs an extra tap to start on an iPhone, or the player's
  controls are covered or pop up on their own.
- What's shown changes on its own after the page has been open a while.
- Getting to live, another day, or a download takes hunting around.
- It's sluggish under your finger on a phone.

## Fixed constraints

- **Recordings come through our patched Reolink integration** in family-infra,
  via Home Assistant. That integration is where fetching, caching, and
  detection tags live. The card doesn't talk to the cameras or the NVR
  directly.
- **family-infra deploys it** from a pinned release, like any other component.
