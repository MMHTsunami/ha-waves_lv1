I am building a custom Home Assistant Lovelace card using LitElement (`audio-fader-card.js`) designed explicitly for my Waves eMotion LV1 mixing system.

I need you to write the complete LitElement JavaScript class matching the layout, behavior, and styling of the provided eMotion LV1 channel strip image.

### 1. Dynamic Entity Derivation
The card should only require a single input in YAML: `fader_entity: number.waves_lv1_192_168_0_176_ch1_fader`.
All other required entities must be automatically derived by replacing `_fader` with the appropriate suffix:
- Label text: `sensor.<prefix>_track_name`
- Label background color: `sensor.<prefix>_color` (returns a HEX code like `#FFE169`)
- Mute toggle: `switch.<prefix>_mute`
- VU Meter level: `sensor.<prefix>_vu`

If any derived state object is missing, handle it gracefully with sensible defaults (e.g., fallback label to "CH", default dark grey background, muted state `off`, VU meter `min`).

### 2. Physical Layout & Aesthetics (Matching LV1 Screenshot)
- Vertical ordering (top to bottom):
  1. **Channel Label**: Light grey/custom color block with bold black text.
  2. **MUTE Button**: Dark, rounded rectangle button with grey outline and white "MUTE" text when inactive; red background when active (`on`).
  3. **dB Value Readout**: Centered cyan/light-blue bold monospace text (`10.0`, `-Infinity` / `-∞`, etc.).
  4. **Fader Scale & Track**: 
     - Metallic silver/grey fader cap with a crisp white center horizontal indicator line and subtle vertical gradient.
     - Center dual-track slot where the background acts as a live segment-driven or CSS-gradient VU meter.
     - Left and right scale markings (+10, +5, 0, -5, -10, -20, -30, -50, -60, -∞).

### 3. Integrated Track VU Meter
- The twin vertical tracks in the center of the fader scale represent the live VU level read from `sensor.<prefix>_vu`.
- Map the VU meter height dynamically to the logarithmic fader scale breakpoints.
- Use a CSS linear-gradient or dynamic height mask to render the color ranges along the logarithmic scale:
  - **Green**: Below -10 dB
  - **Yellow**: -10 dB to +5 dB
  - **Red**: +5 dB to +10 dB

### 4. Logarithmic Fader Mapping
Map track position percentage (`0%` to `100%`) to the eMotion LV1 scale breakpoints:
- `100%` -> +10 dB
- `88%`  -> +5 dB
- `74%`  -> 0 dB
- `61%`  -> -5 dB
- `49%`  -> -10 dB
- `36%`  -> -20 dB
- `24%`  -> -30 dB
- `12%`  -> -50 dB
- `5%`   -> -60 dB
- `0%`   -> -144 dB (min)

### 5. Interaction & Service Calls
- Pointer drag (`pointerdown`, `pointermove`, `pointerup`): During pointer movement, only update internal drag position and trigger `this.requestUpdate()` for fluid visual tracking without calling Home Assistant services.
- On `pointerup`, clamp the calculated dB value strictly between `-144.0` and `10.0`, round to `step: 0.1`, format explicitly as a JS `Number`, and call `this.hass.callService("number", "set_value", { entity_id: config.fader_entity, value: finalVal })`.
- MUTE button click: Fires `this.hass.callService("switch", "toggle", { entity_id: derivedMuteEntity })`.

Provide clean, complete ES module code importing `LitElement`, `html`, and `css` from `https://unpkg.com/lit-element@2.4.0/lit-element.js?module`.