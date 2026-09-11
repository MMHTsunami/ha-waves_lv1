# ha-waves_lv1
Wave eMotion LV1 control integration for Home Assistant. emulates tablet app MyFoH for control of LV1 via OSC over TCP.

## Waves eMotion LV1 integration

This custom integration connects Home Assistant to a Waves eMotion LV1 mixer over its local OSC-over-TCP control interface. It maintains a persistent connection, receives LV1 state and meter updates, and sends control changes back to the mixer without polling the device.

### Setup

Install the `waves_lv1` directory in Home Assistant's `custom_components` directory and restart Home Assistant. Add **Waves eMotion LV1** from **Settings > Devices & services > Add integration**. The setup flow first tries to discover LV1 devices on the local network using the LV1 discovery protocol. A host and port can also be entered manually. The connection is checked with a real LV1 handshake before the integration is added.

During setup, choose the entity groups to create. The available groups include input channels, groups, auxes, mains, matrices, DCAs, aux sends, mute groups, user keys, scenes, and global mixer state. The selection can be changed later from the integration's options. Track entities expose names, colors, gain/fader values, pan, width, mute/solo controls, and live VU meter sensors where applicable.

The integration is designed for local control and push updates. It automatically reconnects when the LV1 connection is interrupted and refreshes entity availability as the connection changes. Entity names are based on the LV1 group and channel, so multiple configured mixers remain distinguishable by their Home Assistant device.

### Services

- `waves_lv1.fade_fader` smoothly ramps a track output or input-to-aux send gain to a target dB value. Set `target` to `out` or `send`, provide the zero-based `group` and `channel`, and provide `aux` when targeting a send.
- `waves_lv1.send_raw_osc` sends a typed OSC message for controls that are not covered by the built-in entities. Arguments use tokens such as `i:0`, `d:-6.0`, `s:Hello`, `T`, or `F`.

Both services accept an optional `entry_id` when more than one LV1 mixer is configured. Fader gains use the LV1 range from `-144.0` dB to `10.0` dB.

## Lovelace audio fader card

The repository includes a vertical LV1 channel-strip card at `www/audio-fader-card.js`.
Copy that file to Home Assistant's `/config/www/audio-fader-card.js`, then register it as a Lovelace resource with the URL `/local/audio-fader-card.js` and resource type `JavaScript module`. Add a card with only the fader entity configured:

```yaml
type: custom:audio-fader-card
fader_entity: number.waves_lv1_192_168_0_176_ch1_fader
```

The card derives the track name, color, mute, and VU entities from the configured fader entity. Dragging updates the visual position locally and sends one `number.set_value` call when released; the MUTE button toggles the derived switch entity.
