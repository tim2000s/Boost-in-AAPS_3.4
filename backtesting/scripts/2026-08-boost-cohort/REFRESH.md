# Boost cohort refresh


Registry holds 10 sites. Database checked for staleness per user; only the missing window is fetched, in chunks of at most 7 days.


| user | decisions before | last seen | days stale | windows | decisions after | gained | treatments gained | result |
|---|---|---|---|---|---|---|---|---|
| tim | 131,828 | 2026-08-09 | 0 | 1 | 131,872 | +44 | +7 | ok, now 2026-08-09 |
| A | 126,744 | 2026-08-05 | 4 | 1 | 128,223 | +1,479 | +190 | ok, now 2026-08-09 |
| B | 76,045 | 2026-08-05 | 4 | 1 | 77,702 | +1,657 | +323 | ok, now 2026-08-09 |
| C | 39,036 | 2026-08-05 | 4 | 1 | 40,778 | +1,742 | +116 | ok, now 2026-08-09 |
| D | 106,122 | 2026-08-05 | 4 | 1 | 107,575 | +1,453 | +215 | ok, now 2026-08-09 |
| E | | | | | | | | no credentials in registry, skipped |
| F | 116,178 | 2026-08-05 | 4 | 1 | 117,908 | +1,730 | +303 | ok, now 2026-08-09 |
| G | 58,665 | 2026-08-01 | 8 | 2 | 58,665 | +0 | +0 | requests.exceptions.HTTPError: 503 Server Error: Service Unavailable f |
| H | 36,149 | 2026-08-05 | 4 | 1 | 37,627 | +1,478 | +196 | ok, now 2026-08-09 |
| I | 11,047 | 2026-08-05 | 4 | 1 | 15,618 | +4,571 | +221 | ok, now 2026-08-09 |

A user that gains nothing is already current rather than broken; the days-stale column shows which was the case. A user with no credentials in the registry cannot be refreshed from here and is listed so the omission is visible rather than silent.
