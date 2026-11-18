# Glance Replay

**Replay one hypothetical smart-glasses notification app without connecting a device.**

Define connection/wear/permission events, notifications, TTLs and gestures. Inspect the app's character-grid screens and queue transitions, then gate a regression on explicit expected states. A request to use a camera/microphone is only a permission-state exercise: no image or audio is captured.

This is a deterministic application-policy prototype, **not a hardware emulator, vendor SDK adapter or simulator for arbitrary existing glasses apps**. Its rules are specified below, not inferred from any manufacturer's behavior. The optional local browser workbench inspects discrete replay states; it is not a real-time device display or connection.

## Local visual workbench

Python 3.11+, no runtime dependencies. From this checkout:

```sh
python -m glance_replay.workbench --port 8765
```

Open the printed `http://127.0.0.1:8765/` address. Load either synthetic example or import a JSON scenario, edit it, and choose **Replay scenario**. Scrub through events to inspect the screen, queue, battery/companion/network state and actual-versus-expected assertions. Editing the source invalidates old results. Invalid input retains the source and clears the result. Cancel stops waiting and discards the response; it does not promise interruption of an already executing bounded server computation.

Download source/report for inspection. A downloaded report alone is **not** a CLI-verifiable bundle: use the CLI below with the downloaded source to build and verify the complete evidence directory. PASS means only that all supplied assertions passed, not device compatibility; no assertions is explicitly not a pass.

After `python -m pip install .`, `glance-workbench` provides the same interface, including bundled assets. Stop with Ctrl-C. The server binds only IPv4 loopback, requires the exact printed Host and same-origin requests, and protects POST with a per-process token. No remote hosting or reverse proxy is supported. It is a single-user local tool, not authentication against malicious local processes/browser extensions, a multi-tenant service or a resource-exhaustion sandbox. Do not expose its port. The server keeps imports in memory and does not write them to disk; browser downloads may contain all supplied text and follow your browser's storage settings. No cloud API or API key is needed.

## Run the synthetic scenario

Python 3.11+, no runtime dependencies:

```sh
python -m glance_replay replay examples/notification-day.json --out replay-result --require-pass
python -m glance_replay verify replay-result --require-pass
python -m unittest discover -s tests -v
```

Use a new output directory. Inspect `frames.txt` and `report.json`. The example demonstrates a higher-priority timer preempting a lesson notification, tap cycling, exact expiry, denied camera access without a declared permission, clearing notifications when the glasses are removed, and a later **simulated** allowed camera request. It performs no actual camera access.

Optional installation: `python -m pip install .`, then use `glance-replay` instead of `python -m glance_replay`. Setuptools is required to build. No package-registry release is implied.

## Scenario contract (schema 1)

A scenario has exactly `schema`, `profile`, `initial`, `events` and `assertions`. The example file is a complete editable template.

- `schema`: integer 1.
- `profile`: `columns` 4–80, `rows` 1–8, `queue_limit` 1–32. These are **hypothetical character/code-point bounds**, not pixels or specifications for a real glasses model.
- `initial`: explicit boolean `connected` and `worn`, plus a unique list of declared permissions: `notifications`, `camera`, `microphone`. The queue always begins empty.
- `events`: 1–500 events in nondecreasing `at_ms` order, between 0 and 86,400,000 inclusive. Equal timestamps are processed in file order, not simultaneously.
- `assertions`: up to 500 objects containing `after_event` (zero-based event index) and nonempty `expect` fields.

Common events:

```json
{"at_ms": 0, "type": "connect"}
{"at_ms": 0, "type": "wear"}
{"at_ms": 0, "type": "grant", "permission": "notifications"}
{"at_ms": 100, "type": "notify", "id": "lesson", "text": "Lesson begins", "priority": 1, "ttl_ms": 1000}
{"at_ms": 200, "type": "tap"}
{"at_ms": 300, "type": "dismiss"}
{"at_ms": 400, "type": "capture", "resource": "camera"}
{"at_ms": 500, "type": "remove"}
```

Other events are `disconnect`, `revoke` with a permission, and `wait`. Capture resources are only `camera` or `microphone`. Unknown fields/types are rejected. Notification IDs must be unique across the entire scenario, even after the notification expires. Priorities are integers 0–9; TTL is 1–3,600,000 ms. Text is 1–400 Unicode code points, with newlines allowed but control/format characters rejected.

## Exact notification-app policy

1. Before each event, notifications with `expires_ms <= at_ms` expire. If the active item expired, the highest-ranked survivor becomes active. No time advances except through supplied events; add a `wait` to inspect a later time. Nothing is predicted after the final event.
2. A notification is accepted only when connected, worn and granted `notifications`. A rejected arrival is dropped, not queued for a future reconnect. Denial precedence is disconnected, then not worn, then missing permission.
3. Queue order is descending priority, then original event order (FIFO ties). On overflow, retain the highest-ranked `queue_limit` items. The new arrival itself may be dropped. Removals are visible in the trace.
4. A new strictly higher-priority arrival than the selected item triggers selection of the highest-ranked queued item. Otherwise the user's current selection remains, unless evicted. Equal priority does not preempt.
5. Tap cycles through ranked items; dismiss removes the selected item and selects the highest-ranked survivor. Gestures on an empty queue are explicit no-ops.
6. Disconnect, remove, and notification-permission revocation purge the queue and screen. Reconnection, wearing again or regranting permission does not resurrect old notifications. Other permission revocations do not erase notifications.
7. Permission declarations persist across connection/wear changes. This is an explicit prototype choice, not an OS or SDK promise. Grant/revoke events change only model state.
8. Capture requests use the same connection/wear gate plus their specific resource permission. Success is named `simulated_capture_allowed`, returns no sensor data and invokes no camera, microphone, file recorder, Bluetooth stack or network API.

These conservative clearing rules help exercise a prototype but do not prove that a real device clears buffers or enforces permissions. There is no continuous sensor stream, physical power-consumption/load/latency model, optics, gaze, gesture recognition, image understanding, physical interaction or safety certification.

## Character-grid output

The active notification text is split at newlines, then hard-wrapped by Unicode **code-point count** to the declared column count. At most the declared number of rows is retained; overflow replaces the last visible cell with `…` and sets `truncated: true`.

This is not pixel/font layout, visual-angle simulation, grapheme-aware shaping, East Asian terminal-width calculation or accessibility/readability validation. Emoji sequences and combining characters may split. Use an actual device's renderer/emulator and human testing for real display quality. `frames.txt` is a textual state trace, not a photographed/rendered optical display.

## Assertions and regression gates

`expect` may name `connected`, `worn`, `permissions`, `active`, `queue`, `screen` and/or `result`. Comparison is exact and type-sensitive. Permissions are sorted alphabetically; queue IDs follow ranking; screen is a list of rendered text rows. Only the named fields are checked. Every assertion records its actual and expected values; an empty assertion set yields `no_assertions`, not a pass.

```json
{"after_event": 4, "expect": {"active": "timer", "queue": ["timer", "lesson"]}}
```

Exit 0 normally means replay generation or deterministic recomputation completed, not that assertions passed. With `--require-pass`, assertion failure **or no assertions** exits 3. Invalid input, mismatched output and filesystem errors exit 2.

The Python `replay(raw_json_bytes)` function exposes the same validated engine for local tests. It does not load plugins, run scripts or adapt an arbitrary external app. If you change the policy implementation, rerun your scenarios and review any changed output; no vendor compatibility follows.

## Evidence and privacy

A result directory contains exactly:

- `source.json`: complete original scenario bytes, including notification text.
- `report.json`: profile, source hash, every event's state, expired/removed IDs, screens and assertions.
- `frames.txt`: human-readable event and screen sequence.

`verify` reconstructs both outputs from the bundled source. It checks internal consistency, not authenticity, policy adequacy or hardware observations. Coordinated replacement of inputs and outputs can pass. Keep an external trusted signature/hash if provenance matters.

The replay engine uses no telemetry, network, Bluetooth, live notification feed, environment reading or actual sensor access. The optional workbench uses local HTTP only; it makes no external service requests. The bundled examples are original synthetic text. **Your supplied notification text appears in output files**; use synthetic or authorized data, and inspect it before sharing. Errors do not echo supplied contents. No private reporting destination is designated; keep secrets out of public issues.

Inputs are bounded to 1 MiB, JSON depth is bounded, duplicate keys/floats/non-finite numbers/malformed Unicode are rejected, and regular non-symlink files are required. The file guard is not a sandbox against hostile parent-directory changes. Outputs are serialized and checked against an independent 8 MiB per-file bound before creating a new directory. Existing directories are never overwritten; an I/O failure can leave a partial directory that must not be treated as complete.

## Existing projects and comparison boundary

- [OpenG1 SDK](https://github.com/gabrielevierti/openg1-sdk) documents a G1 API and emulator with a hardware-oriented development workflow.
- [xg.glass](https://github.com/hkust-spark/xg-glass-sdk) provides broader device APIs and simulator workflows.
- [OpenLens](https://github.com/SriBYJU/OpenLens) describes a broader smart-glasses simulation and benchmarking workbench.

Primary repository documentation was inspected; these runtimes were not executed for a comparison. This project does not claim to outperform them, implement their APIs or offer a novel permission/notification model. Choose the appropriate actual vendor/SDK emulator when device behavior or application compatibility matters. The narrow utility here is an explicit, inspectable event-policy regression loop with no hardware requirements.

## Validation

Historical schema-1 validation: 30 public tests executed on Linux/Python 3.12. Coverage includes priority/FIFO/eviction, exact TTL boundaries, hand-picked gesture and lifecycle traces, mocked permission denial/allowance, display truncation, 100 seeded incremental notification-retention scenarios against a separate ranking oracle, strict inputs, maximum 500-event self-verifying output, byte preservation, tampering, bounded file handling and CLI exit codes.

No real glasses, vendor SDK, optical rendering, Windows/macOS, hosted CI or human usability trial was tested. The camera/microphone tests assert only synthetic states, not actual captures. FIFO/symlink tests can skip on unsupported systems; skips are not passes.

MIT license. Original code and synthetic scenarios by walker512. No upstream competitor implementation or private notification data is bundled.

## Companion, battery, network and recognized voice intents (schema 2)

The optional [platform-state scenario](docs/PLATFORM_STATES.md) extends the same notification-app policy with declared battery percentage, companion-app foreground/background/stopped state, online/offline network and hypothetical camera/microphone/offline-voice/background capabilities. `voice` events contain **already recognized, fixed command intents**, not audio or a speech-recognition result. There is no live phone UI or vendor/device integration.

```sh
python -m glance_replay replay examples/platform-day.json --out platform-review --require-pass
python -m glance_replay verify platform-review --require-pass
```

Schema 1 remains supported without new fields and retains the locked example's original report/frame bytes. All original 30 tests are unchanged; the published 0.2 suite has 48 tests, run locally on Linux/Python 3.12 with zero skips. New cases cover battery clearing/recovery, local versus remote notification arrivals, companion/background capability changes, microphone and target-resource voice gates, offline voice declarations, strict assertions and actual CLI replay/verify. That release had no browser, device, ASR, cross-platform or human usability validation. See [workbench validation](docs/WORKBENCH_VALIDATION.md) for the new candidate and its remaining limits.
