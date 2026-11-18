# Local workbench candidate validation

Baseline: public commit `4ce034cb300816d5b87e1f177d7a94b523a113f2`. The deterministic core and existing CLI policy are unchanged. This candidate adds the local visual inspector, not real hardware support. Independent review and publication are pending.

## Reproduced automated checks

- Linux/Python 3.12: `python -m unittest discover -s tests -v`: **62 tests, zero skips** (48 existing plus 14 new workbench tests).
- `python -m compileall -q glance_replay tests` and `node --check glance_replay/assets/app.js` passed.
- Real loopback HTTP tests cover both schemas against the existing engine, fixed assets, content/security headers, wrong Host/Origin/token, cross-site requests, duplicate framing/auth headers, unsupported content types, oversized inputs, transfer encoding, malformed JSON and hostile header values.
- Built a wheel offline with installed setuptools, installed into a fresh virtual environment, then outside the source tree started its server and fetched all six asset/session routes successfully.
- Static frontend checks prohibit dangerous rendering sinks and remote assets. These are not a substitute for browser tests.

## Actual desktop browser acceptance

Performed with the supported managed local preview and a real Chromium browser on 2026-11-18, using synthetic data only:

1. Loaded schema 1; replay produced 12 events and PASS. Event 4 displayed `Break time`, timer priority over lesson, and matching assertion evidence. Next event and first-event navigation changed the display correctly.
2. Loaded schema 2; previous results cleared, then 17-event replay. Event 9 showed battery 0, powered false, empty queue and offline network.
3. Edited to invalid JSON; source remained, fixed failure message appeared, old result cleared to NOT RUN.
4. Imported a workspace JSON file containing literal `<img src=x onerror=alert(1)>` notification text with no assertions. It replayed as NO ASSERTIONS, displayed literal truncated text rather than an image/script, and exported a report. The downloaded file's source hash matched the imported bytes and contained 12 trace events.
5. Reloaded after the final session-token refresh change, loaded and replayed schema 1 again; visually inspected the two-column desktop layout and event 4 screen.

One initial import from a temporary path failed to provide readable browser file contents; the application retained the existing source and reported failure. The same synthetic file imported successfully from the supported workspace path. This is not claimed as universal filesystem compatibility.

## Limits

No real glasses, camera/microphone capture, Bluetooth, ASR, companion phone, vendor SDK or physical display was tested. No mobile viewport, Firefox/WebKit, Windows/macOS runtime, assistive-technology audit, human usability study, hosted CI or load test was run. Rapid cancellation/stale-response protection is implemented, but delayed-response cancellation races have not been exercised in a real browser. The UI reports discrete states, not elapsed real time. It cannot establish full production readiness or overall completion of the original project topic.
