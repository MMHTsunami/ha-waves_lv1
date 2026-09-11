# Waves LV1 → Home Assistant Custom Component Port Plan

Port the reverse-engineered OSC-over-TCP protocol from `bitfocus/companion-module-waves-lv1` into an async Python `waves_lv1` custom component.

## Core Decisions & Architecture
- **No `media_player` Platform:** All audio parameters are handled via standard HA platforms (`number`, `switch`, `button`, `select`, `sensor`, `text`).
- **Dynamic Entity Generation:** Entities are generated on the fly as the LV1 reports its topology.
- **Push-Based Dispatcher:** Uses `async_dispatcher_send` per track/signal instead of a polling `DataUpdateCoordinator`.
- **zDNS Discovery:** Multicast UDP discovery (`225.1.1.1:13337`) is included in the Config Flow.
- **Service Controls:** Fader ramps (`waves_lv1.fade_fader`) and raw OSC (`waves_lv1.send_raw_osc`) are implemented as custom HA services.
- **Entity Defaulting:** High-cardinality entities (e.g., EQ bands, matrix sends) set `entity_registry_enabled_default = False` to avoid cluttering the default UI.
- **VU Meters:** Deferred to Phase 7.

---

## Execution Phases

### Phase 0 — Setup & Scaffolding [COMPLETED]
- [x] Scaffold `custom_components/waves_lv1/`: `manifest.json` (`domain: waves_lv1`, `iot_class: local_push`, `config_flow: true`), `const.py` (domain, defaults, OSC addresses), `hacs.json`, `strings.json`, `translations/en.json`.
- [x] Create stubbed `__init__.py` with `async_setup_entry` / `async_unload_entry`.
- [x] **Verification:** Pass `python -m script.hassfest` or standard HACS validation action.

### Phase 1 — Core OSC & TCP Client [COMPLETED]
- [x] **`protocol/osc.py`:** Port `osc.ts` (`encode_message`/`decode_message` for OSC types `i, f, h, d, s, b, T, F, N, I` with 4-byte padding).
- [x] **`protocol/tcp_client.py`:** Port `osc-tcp.ts` (`OscTcpClient` with `asyncio.open_connection`, framing `[4B BE len][8B header][OSC payload]`, stream reassembly loop, auto `/pong` reply to `/ping`, `MyFOH` handshake batch, reconnect with backoff).
- [x] **Unit Tests:** `pytest` unit tests for OSC round-trip encoding/decoding and TCP framing reassembly against mock streams.

### Phase 2 — Discovery Client [COMPLETED]
- [x] **`protocol/discovery.py`:** Port `zdns-discover.ts` (`asyncio.DatagramProtocol` joining multicast `225.1.1.1:13337`, parsing `/zDNS` messages, subnet IP ranking).
- [x] **Unit Tests:** `pytest` test for parsing captured `/zDNS` sample packets.

### Phase 3 — Config & Options Flow [COMPLETED]
- [x] **`config_flow.py`:** Port `config.ts` (Discovery dropdown + manual host/port override, port `0` auto-discovery, TCP handshake validation before entry creation). Options Flow deferred — no settings beyond host/port yet.
- [x] **Verification:** Integration imports cleanly against a real `homeassistant` core install; JSON metadata (`manifest.json`/`strings.json`/`translations/en.json`) validated.

### Phase 4 — Coordinator & State Engine [COMPLETED]
- [x] **`protocol/models.py`:** Dataclasses mirroring `main.ts` state (`ChannelState`, `SendState`, `UserKeyInfo`, `FlipTarget`, `DetectedTopology`).
- [x] **`protocol/tracks.py`:** Port `tracks.ts` group table (`0` Input through `12` DCA), slug generation, and `enumerate_tracks()`.
- [x] **`coordinator.py`:** `LV1Coordinator` managing connection, port re-discovery, `/Notify/*` handler dispatch, push state updates via `async_dispatcher_send`. Dynamic entity callbacks deferred to Phase 5 platforms.
- [x] **`entity.py`:** Base `LV1Entity` with device info and unique ID pattern `{group}_{ch}_{prop}`.
- [x] **Unit Tests:** `pytest-homeassistant-custom-component`-backed tests for `/Notify/...` state handling and dispatcher signals (`tests/test_coordinator.py`), plus pure-logic tests for topology helpers (`tests/test_tracks.py`).

### Phase 5 — Entity Platforms & Services
- [x] **`switch.py`:** Mute, solo, send-on, mute groups (1-8), phantom power (+48V), polarity, plugin bypass/enable, spill, talkback engage.
- [x] **`number.py`:** Faders, pan, width, send gain, send pan, preamp gain, digital trim, EQ bands (freq/gain/Q).
- [x] **`select.py`:** Scene recall by name, aux focus (`/Set/AuxId`), flip-sends via user keys.
- [x] **`button.py`:** Scene next/prev, tap tempo, clear solos, user key presses, state refresh, re-scan discovery.
- [x] **`sensor.py`:** Track names, hex colors, current scene, tempo, flip state, user key info, channel totals.
- [x] **`text.py`:** Track renaming (`/Set/TrackName` with optimistic local updates).
- [x] **Services:** Implement `waves_lv1.fade_fader` and `waves_lv1.send_raw_osc` in `services.yaml` and `__init__.py`.

### Phase 6 — Integration Polish
- [x] **`diagnostics.py`:** Diagnostic dump for coordinator state.
- [x] **Repairs:** Connection/handshake repair flow handlers.
- [x] **Registry Hygiene:** Verify high-cardinality entities default to disabled.

### Phase 7 (Deferred Milestone) — VU Meters
- [x] **`sensor.py` (Meters):** Track VU sensors from `/Notify/Meters` with throttled/coalesced updates (~0.8 Hz batching).
- [x] **Validation:** Confirm the LV1 meter parser handles both raw triplets and count-prefixed payloads without blowing up on mixed OSC numerics.

### Phase 8 - Custom Home Assistant Audio Mixer Card Instructions

#### Tech Stack Rules
- Target Environment: Home Assistant Frontend Dashboard (Lovelace Card).
- Framework: Use standard Lit (`lit-element` or modern vanilla JavaScript web components) as per modern Home Assistant standards.
- UI Design: Implement a vertical "audio channel strip" layout. Each strip must have a label, a vertical visual fader slider, a visual volume DB/percentage meter indicator, and a mute button.
-Fader slider must
- Styling: Use Home Assistant CSS variables (`--primary-text-color`, `--card-background-color`, etc.) to ensure theme compatibility.

#### Home Assistant Core Integration
- Every reactive state update relies on the global `hass` object (`this.hass`).
- To fetch an entity state, use: `this.hass.states['media_player.example']` or `this.hass.states['number.example']`.
- To mutate state / move a fader, use `this.hass.callService(domain, service, data)`. 

#### Code Architecture
- Must include a `setConfig(config)` method to handle Lovelace yaml inputs.
- Must include a static `getStubConfig()` method to provide dashboard preview defaults.
- Must include a static `getConfigForm()` method to provide form editor.