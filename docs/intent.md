# Camera card: product intent

A Home Assistant dashboard card that answers one question fast, on a phone:
**"what happened on our cameras, and what's happening now?"**

It is purpose-built for one home: a Reolink NVR with six cameras, viewed mostly
on iPhones (Safari and the HA app), sometimes on a desktop browser. It replaces
our fork of Advanced Camera Card, whose general-purpose features kept getting in
the way (see family-infra #299).

## What it's for

- **See activity at a glance.** One row per camera on a shared timeline, with a
  mark for every recording. Busy and quiet stretches are obvious without
  tapping anything.
- **Watch a recording in one tap.** Tapping a camera's row plays the recording
  nearest the tap, from its start, in a player above the timeline. No precise
  aiming at small marks.
- **Jump to live.** Every camera row ends in a clear "Live" control just past
  the "now" line. It switches the player to that camera's live feed.
- **Keep a clip.** One obvious Download button saves the recording that's
  playing.
- **Filter by what was detected.** People, vehicles, animals, other.
- **Browse back in time.** Drag the timeline to go to earlier days, and pinch
  or scroll to zoom from a full day down to minutes.

## How it should feel

- **Fast.** The timeline is fully drawn within 5 seconds of opening (aim for 2),
  or 10 seconds on the first open after an HA restart. Older days appear within
  2 seconds of scrolling to them. A tapped recording starts within 5 seconds.
  New recordings show up within 2 minutes.
- **Smooth on an iPhone.** Dragging the timeline follows your finger.
- **Plays without fuss.** Recordings autoplay muted. The phone's own player
  controls stay hidden until you tap the video, and nothing we draw covers them.
- **Stable layout.** Switching recordings or cameras never makes the page jump
  or resize.

## Non-goals

- Other camera brands or NVRs, multiple homes, or any configuration a different
  household would need. The cameras can be listed in the card's config, but
  nothing more general than that.
- PTZ control, two-way audio, doorbell calls, snapshots, a thumbnail gallery,
  folder browsing, or a visual config editor.
- Scrubbing inside a recording from the timeline. The player's own seek bar
  does that.
- Replacing the per-camera live cards elsewhere on the dashboard.

## Signs it's malfunctioning

- The timeline is blank, partial, or still loading after 5 seconds.
- A tap on a camera row does nothing, plays the wrong camera, or starts
  mid-recording.
- A recording stays on a spinner, needs a Play press on an iPhone, or shows an
  error over a recording that is in fact playing.
- Marks disappear or merge differently after the page has been open a while.
- Our controls cover the phone player's controls, or the player pops its
  controls up on its own.
- Dragging the timeline stutters on an iPhone.

## Dependencies we keep

- **The server side stays as it is.** Our patched Reolink integration in
  family-infra fetches recordings (via the NVR's "download cut"), caches each
  day's recording list, and supplies detection tags. The card only reads from
  it through Home Assistant.
- **Deployment.** family-infra's Ansible installs the card from a pinned
  release, as it does today.
