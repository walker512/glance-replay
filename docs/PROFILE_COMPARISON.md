# Compare hypothetical capability configurations offline

Run one ordered event stream and initial state against 2–8 named profiles using
the existing Glance Replay engine. This CLI describes a fictional app policy,
not actual glasses, SDKs, microphone/camera access, voice recognition, network
behavior, energy measurements or device compatibility. No adapter, model,
subprocess or network request is invoked by comparison itself.

## First comparison

From the checkout:

```sh
python -m glance_replay.compare build examples/profile-comparison.json --out NEW_COMPARISON --require-all-pass
python -m glance_replay.compare verify NEW_COMPARISON --require-all-pass
```

The original synthetic example contrasts online-only voice, an offline/background
companion, and a profile without a camera. It observes a first trace difference
at event 2, background queue differences, and a later camera denial. All three
sets of **independent** expectations pass. Differences are not regressions or a
device ranking. No actual camera, voice, phone app or network is used.

The new directory contains:

- `source.json`: original input bytes, not only a hash;
- `comparison.json`: every reconstructed replay, per-event differing fields,
  reported outcome/denial codes, independent assertion results, all profile pairs
  and each pair's first observable divergence;
- `comparison.txt`: a plain UTF-8 summary with JSON-escaped dynamic text. Open as
  **plain text**, not HTML/Markdown. It is not a general link sanitizer.

## Input contract

The outer format has exactly `schema` (integer 1), `replay_schema` (integer 1 or
2), `initial`, `events`, and `configurations`. `initial` and the ordered `events`
are shared. Each of 2–8 configurations has exactly:

```json
{
  "id": "NamedHypothesis",
  "profile": {
    "columns": 16,
    "rows": 2,
    "queue_limit": 3,
    "low_battery_percent": 10,
    "capabilities": {
      "camera": true,
      "microphone": true,
      "offline_voice": true,
      "background_companion": true
    }
  },
  "assertions": [
    {"after_event": 0, "expect": {"result": "waited"}}
  ]
}
```

This fragment is for a schema 2 scenario whose event 0 is `wait`; consult the
complete example instead of copying it into an unrelated event stream. IDs must
be unique existing-engine identifiers (letter followed by up to 47 letters,
digits, `_`, `.` or `-`). Identical profiles with different IDs are allowed.
Each configuration must explicitly provide its own `assertions` list; `[]`
means **no_assertions**, not success. Independent expectations let different
capabilities have different correct outcomes. Changing an assertion changes the
question being tested, not the simulated trace.

Every assembled scenario passes the unchanged engine's full validation. The
selected `replay_schema` fixes which profile/initial/event/assertion fields are
supported: schema 1 has the original notification settings, not platform
capabilities; schema 2 adds the existing hypothetical platform model. Existing
single-scenario JSON, old replay bundles and all original CLI/workbench entry
points remain unchanged. Old scenarios are not silently converted into this new
outer format; copying the explicit fields is required.

## Read the results correctly

- Events and configurations retain input order. Equal timestamps retain list
  order. Unsorted event times are rejected, not reordered.
- `different_fields` compares exact typed trace values at the same event index,
  not arbitrary textual similarity. Per-pair indices cover all differing events;
  `first_divergence: null` means no observable **trace** difference for this input.
  It does not mean profiles or capabilities are identical: `profiles_identical`
  reports that separately. Hidden internal state and untested inputs are not
  evaluated.
- `rejection_reason` is the existing engine's first `denied_*` outcome code, not
  a new causal inference or a list of every possible blocking condition.
  `dropped_capacity` remains a distinct result, not relabeled as a permission
  denial. The full traces and original profiles provide context.
- Each run is `pass`, `fail`, or `no_assertions`. Per-event assertion status can
  be `no_assertions` even if other events made the run pass. Two identical failed
  traces remain failed; equal output is not success. This tool does not infer
  regression/improvement across profiles with different intended capabilities.
- Default exit 0 means build/consistency verification completed. Optional
  `--require-all-pass` returns 3 unless **every** configuration has at least one
  assertion and all its assertions pass. It does not require every event to have
  an assertion. Invalid input/evidence or filesystem failure returns 2 without
  echoing input text. An assertion failure is still a valid comparison artifact.

## Integrity, privacy and limits

Verification rereads the preserved original source, replays each configuration,
rebuilds the comparisons and plain text, then compares exact output bytes.
Unknown versions, missing/extra files, leaf links, changed output and typed
value substitution are rejected. This detects inconsistency; someone who edits
the source and recomputes all outputs can make another valid bundle. There are
no signatures or proof of original execution/device behavior. Keep a trusted
original if you need independent provenance.

**All notification text, profiles, initial state, events and assertions are
retained.** No anonymization is performed. Reports and hashes may expose or link
private information. Use authorized/synthetic inputs and a private stable parent.
New directories request 0700 and members 0600 on POSIX, and are exclusive. Windows
ACL privacy is not established. Existing data is never overwritten or chmodded.
Parent-directory links and hostile same-account replacement are not an isolation
boundary. A concurrent creator of the destination is refused; publication is not
transactional. A later write failure can leave a private partial directory which
will not verify; inspect it and use a fresh output path. No recursive cleanup,
crash durability or general resource sandbox is provided.

Input: at most 1 MiB, 2–8 configurations and 1–500 events with the existing per-field
limits. Each serialized member is capped at the existing 8 MiB output limit,
checked before creating the destination. Some combinations within individual
limits may exceed the combined report bound and are rejected, never truncated.
No external dependency or service is introduced.

## Tests and scope

Run `python -m unittest discover -s tests -v`. Added tests cover identical profiles,
independent assertions, offline voice, background queue retention, camera
capabilities/permissions, equal-time ordering, capacity/grid differences, both
replay schemas, exact types, tampered bundles, output preflight, private creation,
links, concurrent creation and partial writes. These are synthetic local model
and real CLI tests. No browser access or new Windows/macOS/native-device test is
claimed. This increment does not complete the full smart-glasses product theme.

## Aggregate export for manual review

After building a comparison bundle, use a new output file outside that bundle:

```sh
python -m glance_replay.compare export-summary NEW_COMPARISON --out comparison-counts.json
```

Use the same bundle path you passed to `build --out`. This opt-in command verifies
the complete source bundle by local recomputation before writing. It is silent
on success and does not modify the bundle. It refuses existing files and
symlinks. Use a trusted output parent directory; on POSIX the permissions
requested at creation are 0600 (the umask may make them more restrictive).
A write failure can leave a partial output; trust only a successful command and
inspect the file before sharing. Windows ACL privacy and hostile parent-directory
replacement are not covered.

The deterministic schema 1 JSON exposes only total events, the number of events
with a trace difference across any profiles, and each profile's passed and
failed assertion counts and count of outcomes starting with `denied_`.
Dropped items are not counted as denials. Zero assertions is not a pass.
Profiles are named `profile-1`, `profile-2`, and so on in source order. Original
profile and event IDs, payloads, timestamps, frame content, reasons, URLs and
hashes are not included.

This is **not anonymization**: counts and order are still potentially revealing,
especially when people know the scenario or compare multiple summaries. Review
before sharing. It is not replay evidence, proof of origin, or a test of real
devices. Keep the private full bundle for recomputation and troubleshooting.
