# Street questions: what to ask about passersby (camera-card#14)

2026-11-27. Six labeled street recordings from 2026-11-26 (bin/testdata, labels checked by Sonnet and the owner), the same 16 pictures production sends, one Gemini call per recording. "Missed" = a real activity not reported; "invented" = one reported that didn't happen. Script: alerts/experiments/street_questions.py.

| Questions | Missed | Invented |
|---|---|---|
| Today's: one yes/no per activity | 1 | 5 |
| Same, high resolution | 1 | 3 |
| "How many people were doing X" per activity | most | n/a (rarely answered 0) |
| One "mainly doing" choice + "also" choice | 2 | 0 |
| Yes/no "is X clearly visible", with a veto for shadow | 0 | 4 |
| One choice per person (first, second, third) | 3 | 0 |
| **Four choices: what's held, where they go, pace, smoking** | **0** | **0** |
| Same four, cropped to the sidewalk | 1 | 0 |

- Independent yes/no questions invite yes: 55–75% confidence on things that weren't there (a dog, a stroller). Choices that are mutually exclusive and include "nothing / unclear" fix it.
- The four-choice set scored 0/0 on all four repeats, including at high and ultra-high resolution: resolution isn't the limit.
- Smoking was always "too backlit to tell"; no recording with smoking yet, so it's set aside.
- Not yet tested: dogs, strollers, mixed groups (one choice per question may under-report a group doing two things).
