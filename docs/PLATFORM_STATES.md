# Hypothetical cross-device application state

Schema 2 supplements the existing **one notification-app prototype** with conditions from a possible paired-glasses workflow. All profile values and behaviors are assumptions, not specifications for a named manufacturer or an unreleased product. This remains an offline deterministic simulator; it does not emulate arbitrary binaries, Bluetooth, network traffic, a physical battery, an acoustic microphone or a companion-app UI.

Run `examples/platform-day.json` using the same `replay` and `verify` commands. The original schema-1 fixture and its locked report/frame hashes retain the same output. Schema-2 fields are mandatory when schema is 2, and are rejected in schema 1; no configuration is silently inferred.

## Additional contract

Schema 2 retains `schema`, `profile`, `initial`, `events`, `assertions`. The base display/queue profile and all existing limits still apply.

Add to `profile`:

```json
{
  "low_battery_percent": 10,
  "capabilities": {
    "camera": true,
    "microphone": true,
    "offline_voice": false,
    "background_companion": false
  }
}
```

`low_battery_percent` is an integer 0–99. All capabilities are exact booleans. Camera/microphone declarations affect permission exercises, not sensor creation. `offline_voice` declares whether fixed recognized intents can be processed without a network in this prototype. `background_companion` allows this app's notification/voice bridge to operate while the companion is backgrounded; it makes no claim about an actual phone OS.

Add to `initial`:

```json
{"battery_percent": 80, "phone_app": "foreground", "network": "online"}
```

Battery is an integer 0–100; phone state is `foreground`, `background` or `stopped`; network is `online` or `offline`. Existing `connected`, `worn` and permission declarations are still required. These are independent modeled conditions: `connected=true` can coexist with battery zero or offline network. `powered` is derived only from battery greater than zero, not an assertion that physical radio hardware is operating.

New events:

```json
{"at_ms": 100, "type": "battery", "percent": 10}
{"at_ms": 200, "type": "network", "state": "offline"}
{"at_ms": 300, "type": "phone_app", "state": "background"}
{"at_ms": 400, "type": "voice", "command": "next"}
```

Every schema-2 `notify` additionally requires `origin: "local"` or `"remote"`. Local means delivered from the companion without needing this modeled network; remote means its arrival needs `online`. This is a manually declared origin, not observed routing.

Voice commands are exactly `next`, `dismiss`, `capture_camera` or `capture_microphone`. They represent **already recognized intents supplied by the scenario author**. There is no raw recording, recognizer, wake word, language understanding, error rate, latency or confidence model. Arbitrary phrases and command strings are rejected. Do not call these tests real speech-recognition validation.

## State transitions and exact precedence

All original priority, queue-capacity, TTL, gesture, connection/wear, permission-purge and text-grid rules remain. Equal timestamps execute in file order. TTL expiration happens before every event, including rejected input and battery/phone/network changes.

- A battery event assigns an explicit percentage, with **no inferred drain or charging curve**. Zero immediately purges the notification queue and screen. Restoring battery does not resurrect removed or rejected arrivals. Sensor exercises and voice intents are denied at or below the declared low-battery percentage; ordinary notifications still work when battery is nonzero. Physical tap/dismiss on an empty powered-off queue are simply no-ops, not real input hardware behavior.
- A companion event changing to `stopped`, or `background` when background support is false, purges the queue and screen. Returning to foreground does not restore old data. Backgrounding with support true preserves the queue.
- A network event never purges already accepted notifications, which represent cached content. New remote arrivals are denied offline; local arrivals can still pass the other gates. A rejected arrival is not deferred and does not appear on reconnect.
- Permissions, declared connection and wear state persist across battery, network and companion changes. Grant/revoke/connect/wear events can update these declarations even when powered off. This is test configuration behavior, not proof of OS permission or physical connection behavior.

The shared base gate checks, in order: powered off (schema 2 only), disconnected, not worn, unsupported resource (camera/microphone), missing permission, then low battery (camera/microphone only). It returns the first denial. Notification arrivals use the base notification gate, then companion availability, then network availability if remote.

Voice intents first need the microphone base gate, then companion availability, then online network unless `offline_voice=true`. Only if that succeeds does `next` act like tap, `dismiss` act like dismiss, or a capture intent undergo the **target resource's own base gate**. Thus microphone permission does not authorize camera use. A denied voice event does not cycle, dismiss or capture; normal TTL expiry still occurs first. Trace `event` stays `voice`, and `voice_command` records the supplied intent. Result is the underlying hypothetical action (`cycled`, `dismissed`, `no_notification`, `simulated_capture_allowed`) or its explicit denial.

A direct `capture` event represents the prototype's local/manual sensor request, and does not require companion foreground state or network. A voice-triggered capture does require the preceding microphone/companion/network voice gate. Neither captures data or accesses actual hardware. This distinction is a declared policy choice, not a vendor recommendation.

## Assertions, output and scope

Schema-2 assertions additionally accept `battery_percent`, `powered`, `phone_app`, `network`, and `voice_command` (null for non-voice events). Expected types and enumerations are strict. New denial results are `denied_powered_off`, `denied_low_battery`, `denied_unsupported_resource`, `denied_companion` and `denied_network`; state updates return `battery_changed`, `phone_app_changed` and `network_changed`. Existing result names remain valid.

`report.json` includes every new state at every event; `frames.txt` prints these conditions next to each character-grid frame. All scenario input bytes and notification text are still copied to the result bundle. This is not redaction, secure storage, an authenticated test history or permission to publish a person's messages. The original size, special-file, no-overwrite and recomputation rules remain. A valid result with no assertions is still `no_assertions`, never pass. `--require-pass` treats failed or absent assertions as exit 3.

The example covers offline remote rejection/local arrival, blocked voice, unsupported background companion clearing, low-battery and powered-off denials, restoration without old content and a later permitted **simulated** voice camera intent. Tests also cover strict resource/microphone gates, capability matrices and type-sensitive new assertions. This improves explicit application-state rehearsal but does not complete a visual desktop simulator, real speech/phone integration or arbitrary-app/device compatibility.
