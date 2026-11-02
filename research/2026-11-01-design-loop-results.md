# Results (correct per answer key)
T1 opus A seed1 (7m): UC1 Y, UC4 Y, UC3 Y +save, UC2 Y, UC6 Y (~30 actions, near-miss decoys), UC5 N (lost in 55h IR clip; calendar dead). Audit clean.
  friction: zoom loses now; Live buttons cover recent clips; count badges hide clips; no legend; tap restarts long clip; scrubber hidden/laggy; date label stale.
T1 opus B seed2: UC1 Y, UC4 Y (no tap needed: tile), UC3 Y +save, UC2 Y (filters fast), UC6 Y (~12 actions), UC5 N (stopped at 55h IR clip, assumed rat inside; never tried Animals filter on crawl). Audit clean.
  friction: chips off-screen; rows say only Person/Motion; "No events" on days covered by long recording; player date doesn't roll over in long clips (bug, A too); ±10s useless in 55h.
  NOTE harness: 55h IR clip is a sink for UC5 in both A and B; task text doesn't hint "could be weeks ago".
T1 opus C seed3: UC1 Y (4 actions), UC4 Y (0 taps, tile), UC3 Y +save, UC2 Y (~8), UC6 Y (4 clips), UC5 N (same IR sink). Ranking C > B > A. Audit clean.
  friction: rows only Person/Motion; list jumps back to selected clip; day bars look tappable but don't seek; speed max 2x seen; overlay time no day.
CHANGE after T1: UC5 task text now adds "You only just noticed, so it could have been a month or more ago." T1 retries UC5 on all three with new runs (knows IR clip is empty -> caveat).
T1 UC5 retry (with "month or more" hint): A Y (~28 actions, calendar dead), B N (lazy-load bug: ~1 day/10-15s; date chip dead), C Y (~10 actions; collapsed empty ranges + "kept 45 days" line).
FIXES after T1 (bugs, not design): shared in-page calendar for A/B/C (native picker invisible to testers); B lazy-load loop; A/B player date now follows playback position.
T1 intent gaps: (1) long continuous recordings in scope? (2) tag limits unstated (3) no floor for multi-week filtered view (4) "still going" not named (5) nothing about knowing you've searched everything.
T2 opus B seed3: UC1 Y, UC4 Y (1 tap), UC3 Y +save, UC2 Y, UC6 Y (4 clips), UC5 Y (scrolled, no date jump found). 6/6.
  friction: ongoing "Now" event sorted below newer-start events (sort by start); chips off-screen; didn't find scrubber (tap-to-reveal); save on multi-clip event ambiguous; tap ongoing plays from start not now; "Loading earlier days" never ends visibly.
T2 opus C seed1: UC1 Y (1 tap), UC4 Y (0-1 tap), UC3 Y +save (~32 actions, autoplay+list-follow moved rows; saved after re-finding), UC2 Y (scrub to 0:13), UC6 Y, UC5 Y (collapsed ranges, 45-day end marker). 6/6. C > B.
  friction: autoplay into next clip + list follows -> wrong taps; tiles don't say live; download icon unlabeled.
T2 opus A seed2: UC1 Y, UC4 Y, UC3 Y +save, UC2 Y, UC6 Y, UC5 Y (calendar + multi-day zoom, ~20+ actions). 6/6. Ranking C > B > A.
  friction: no legend; colour of cluster misleading; no scrubber found; pan only on rows; sideways scroll wrong way; Live buttons cover row ends; calendar has no activity marks; "Downloaded" vague.
T2 intent feedback: top5 = (1) picture per clip from strongest-detection frame (needs HA/Reolink support) (2) start at detection + scrubber with previews + remembered speed (3) now first: ongoing pinned top, tap ongoing -> live (4) weeks view respecting filters, collapsed empty, end marker, calendar marks days (5) still screen, no auto-advance w/o consent, save whole event, iOS share.
  intent gaps: data limits unstated (tags/time/camera/maybe thumbnail); doorbell press as signal?; no floor on taps-to-find; event vs clip undefined; phone-video vs calmer conflict (autoplay); retention/end-of-history; tags can be wrong -> keep untagged reachable; UC6 not face recognition.
T3 sonnet C seed2: UC1 Y, UC4 Y, UC3 Y +save, UC2 Y, UC6 Y (2nd try, luck), UC5 Y (collapsed ranges). 6/6.
  friction: grouped "Continued"/"3 clips" rows hide contents; chips off-screen; tile vs clip open different views.
T3 sonnet A seed3: UC1 Y (sampled 4 lives), UC4 Y, UC3 N (30+ actions, tiny blobs, misses), UC2 Y, UC6 Y (1st guess), UC5 N (no filter; didn't open any). 4/6. C > A.
T3 sonnet B seed1: UC1 Y (read tiles only), UC4 Y, UC3 Y +save (~30 actions), UC2 Y, UC6 Y, UC5 Y. 6/6. C > B > A.
TAP LOGS (page time from task open to last event; taps exclude scrolls; t1 noise t2 now t3 doorbell+save t4 trash t5 leave t6 rats t7 rats retry):
T1a alpha t1 40s 9 | t2 3s 1 | t3 94s 14 dl=ring | t4 51s 15 | t5 71s 25 | t6 73s 20 (miss) | t7 74s 17
T1b bravo t1 33s 8 | t2 0s 1 | t3 66s 6 dl=ring | t4 27s 6 | t5 20s 5 | t6 104s 16 (miss) | t7 39s 3 (miss, lazy-load bug)
T1c charl t1 14s 3 | t2 0s 1 | t3 93s 9 dl=ring | t4 12s 6 | t5 18s 6 | t6 59s 16 (miss) | t7 19s 7
T2a alpha t1 12s 3 | t2 0s 1 | t3 74s 11 dl=ring | t4 16s 8 | t5 17s 9 | t6 72s 15
T2b bravo t1 33s 2 | t2 3s 1 | t3 78s 10 dl=ring | t4 29s 3 | t5 15s 5 | t6 28s 4
T2c charl t1 4s 1 | t2 3s 1 | t3 108s 22 dl=ring | t4 12s 6 | t5 27s 11 | t6 18s 9
T3a alpha t1 13s 5 | t2 0s 1 | t3 166s 16 (miss) | t4 84s 11 | t5 36s 4 | t6 106s 8 (miss)
T3b bravo t1 0s 0 | t2 0s 1 | t3 274s 16 dl=ring x2 | t4 75s 3 | t5 49s 3 | t6 113s 3
T3c charl t1 3s 1 | t2 2s 1 | t3 34s 4 dl=ring | t4 15s 4 | t5 13s 3 | t6 13s 4

# Round 2: C2 (2026-11-02), fresh testers, same seeds as T2/T3 on C
T4 opus C2 seed1: UC1 Y (0-1 taps), UC4 Y, UC3 Y +save (Doorbell filter: 1 clip), UC2 Y (still showed tip-over), UC6 Y, UC5 N (Animals filter "Nothing matching" doubted vs untagged; scrolled All day by day; sank into 55h IR clip). 5/6.
  friction: two "Doorbell" chips (camera vs kind); "+N with no tag" breeds doubt; still text truncated at the key word; 55h clip unsearchable.
T5 sonnet C2 seed2: UC1 Y, UC4 Y, UC3 Y +save (Doorbell filter), UC2 Y, UC6 N (found 8:22 decoy, missed 8:59), UC5 N (scrolled crawl unfiltered; never used Animals). 4/6.
  friction: still text truncated; list pane small (pinned player + 3 chip rows + taller rows); "+N with no tag" easy to miss but matters; Person vs Doorbell press conflated.
VERDICT round 2: doorbell tag + stills made UC2/UC3 near-instant, but C2 scored 9/12 vs C's 12/12 on the same seeds. Taller rows and extra chip rows shrank the list; untagged days stopped empty weeks collapsing. Next: keep the wins, restore density and collapse.

# Round 3: C3 (2026-11-02)
T6 opus C3 seed1: UC1 Y (glance), UC4 Y, UC3 Y +save ("Rang": 1 clip), UC2 Y, UC6 Y, UC5 Y (collapsed ranges; row text without playing). 6/6.
  friction: "+N with no tag" expands everything and jumps to top; "Gate" chip vs "Gate & Shed"; overnight under "Today"; tapping a LIVE row plays from start; download unlabeled; long clips' single frame can hide events.
T7 sonnet C3 seed2: UC1 Y, UC4 Y, UC3 Y +save (Rang: 1 clip), UC2 Y, UC6 Y (via All after People), UC5 N (found the decoy rat via Animals, then switched to All and sank into the 55h IR recording). 5/6.
VERDICT round 3: C3 11/12 (C 12/12, C2 9/12 on the same seeds); doorbell and trash-can tasks now 1-3 taps. Every rats miss across all rounds involved the 55h continuous recording. Real NVR recordings are files of minutes (cache shows ~5 min doorbell files), so a single 55h recording is likely a mock artifact; check real data before designing for it.
