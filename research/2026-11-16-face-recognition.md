# 2026-11-16: Naming known people at the doorbell (tested, then shelved)

**TL;DR:** A free face matcher running entirely at home named about 4 in 5
known faces at the doorbell and gave nobody the wrong name. We shelved it
anyway: only about 1 clip in 13 has a usable face, and the alerts' plain
descriptions ("A man is leaving through the gate.") already say enough. Pick
it up again for a specific use case, not for "names" in general.

No photos, names or face data are in this repo, and none ever left the home
network during the test. The prototype scripts are kept privately.

## What we tested

A month of doorbell clips (about 1,050), one close-up face pulled from each
where there was one. That gave 80 usable faces. 79 were named by hand: 56
belonged to four known people, 23 to strangers. The matcher was then scored
against those names.

## Results

| Matcher | Known faces named | Wrong name | Strangers named as known |
|---|---|---|---|
| InsightFace `buffalo_l`, full library | 45 of 56 | 0 | 0 of 23 |
| Same models, slim matcher (ONNX Runtime + numpy + Pillow only) | 44 of 54 | 0 | 1 of 22 |

- About half a second per image on the small home server that runs Home
  Assistant, with results identical to a laptop.
- The cut-off was chosen on these same faces, so real use will be a little
  worse. The margin is thin.

## Lessons

**Matching**

- **Require agreement, not the single closest photo.** A name counted only
  when a person's three best reference photos all cleared the cut-off (0.30).
  Trusting the one closest photo named a delivery driver as a household
  member.
- **The score is a similarity, not a probability.** It ran from roughly 0 to
  0.6 here. Don't show it as a percentage.
- **There is a natural "maybe" band.** A high bar named 29 known faces and no
  strangers. The band just below it added 21 more known faces and the one
  stranger. That maps to "X" above the bar and "maybe X" inside the band.
- **Nothing is trained.** Reference photos sit in one folder per person;
  adding or removing a person is adding or removing photos.

**Reference photos**

- **Shots from the camera itself matter most.** Named doorbell faces did most
  of the work for people who use the door often.
- **A photo library fills the gap** for people the camera rarely sees. About
  20 library photos per person made them recognisable.

**Coverage**

- **Most clips have no usable face.** About 1 in 13 did. The rest can only
  ever be plain alerts.
- **Repeat strangers don't group.** Only one repeat visitor turned up as a
  cluster in a month, so "the same neighbour again" is not available cheaply.
- **Faces can't say what someone is doing.** One stranger wore a courier's
  vest; only a model that looks at the whole frame can use that.

**Running it inside Home Assistant**

- Home Assistant's container (Alpine, its own Python) has no published build
  of ONNX Runtime. It built from source inside that container in about 20
  minutes (v1.32.0), after applying the same small flatbuffers fix Alpine's
  own package uses.
- Owning that build is a standing cost: it must track Home Assistant's Python
  version, and if it breaks, names silently vanish from alerts.
- The engine would run in Home Assistant's own process: a few hundred MB more
  memory, and a crash in it restarts Home Assistant.

**Doing the experiment**

- Pulling one face per clip from the recorder takes hours. Make it resumable.
- Hand-naming went quickly once faces were pre-sorted into "probably known"
  and "look-alike" piles on a single page.
- Keep the clips behind the named faces as a test set. Any change to the
  matcher can then be re-scored in a couple of minutes.

## Where it would have lived

Proposed, never accepted: inside the Reolink integration, so there is one
thing to install and remove, and alerts still go out unnamed if the engine is
missing. Considered and not chosen:

- **A separate matcher service.** Uses the published engine and can't take
  Home Assistant down, but is a second thing to install and remember.
- **An off-site vision model.** Nothing to maintain, but household photos
  leave the house.
- **The dashboard card.** Runs only while a dashboard is open, so it can't
  send alerts.

An untested split that keeps photos at home: the home server answers "is this
someone known?", and only frames of unknown people go to the off-site model.

## Never tested

- Button presses only. The test covered every doorbell event, mostly people
  passing or arriving. Someone pressing the button stands at the lens, so
  rings should do better than 1 in 13.
- Any camera other than the doorbell. Faces further away will do worse.
- Speed inside Home Assistant itself, and whether the engine's helper
  packages clash with Home Assistant's own.

## Why shelved, and when to come back

The alerts already describe who is doing what well enough to judge whether to
look ("A woman is walking to the back building."), and the push carries a
picture, so a glance settles who it is. Names would have changed few alerts
for real upkeep.

Come back by use case. Ask what should get more reliable, then pick the
cheapest thing that moves it:

- **"Who is ringing the doorbell?"** First re-score only the button-press
  clips to get a real hit rate. Faces are a candidate here.
- **"Was that a package delivery, and from whom?"** Faces don't help. This is
  a whole-frame question for the model that already writes the descriptions.
- **Anything else:** state the use case first, then check it against the
  coverage limits above before building.
