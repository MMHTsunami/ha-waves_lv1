import { LitElement, html, css } from "https://unpkg.com/lit-element@2.4.0/lit-element.js?module";

const SCALE = [
  { position: 0, db: -144 },
  { position: 5, db: -60 },
  { position: 12, db: -50 },
  { position: 24, db: -30 },
  { position: 36, db: -20 },
  { position: 49, db: -10 },
  { position: 61, db: -5 },
  { position: 74, db: 0 },
  { position: 88, db: 5 },
  { position: 100, db: 10 },
];

const MARKS = [
  { label: "+10", position: 100 },
  { label: "+5", position: 88 },
  { label: "0", position: 74 },
  { label: "-5", position: 61 },
  { label: "-10", position: 49 },
  { label: "-20", position: 36 },
  { label: "-30", position: 24 },
  { label: "-50", position: 12 },
  { label: "-60", position: 5 },
  { label: "-∞", position: 0 },
];

const clamp = (value, minimum, maximum) => Math.min(maximum, Math.max(minimum, value));

class AudioFaderCard extends LitElement {
  static properties = {
    hass: {},
    config: {},
    _dragPosition: { state: true },
  };

  static styles = css`
    :host {
      display: block;
      --fader-width: 156px;
      --track-height: 390px;
      --muted-color: #d32626;
      --meter-green: #37bd67;
      --meter-yellow: #e2c33a;
      --meter-red: #e34d42;
      color: var(--primary-text-color, #e8e8e8);
      font-family: var(--paper-font-body1_-_font-family, sans-serif);
    }

    .card {
      box-sizing: border-box;
      width: var(--fader-width);
      min-height: 520px;
      padding: 8px 10px 12px;
      overflow: hidden;
      background: var(--card-background-color, #202124);
      border: 1px solid var(--divider-color, #494949);
      border-radius: 4px;
      user-select: none;
    }

    .label {
      display: flex;
      align-items: center;
      justify-content: center;
      height: 38px;
      overflow: hidden;
      color: #111;
      background: #52565b;
      font-size: 14px;
      font-weight: 800;
      letter-spacing: 0;
      text-align: center;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .mute {
      width: 100%;
      height: 31px;
      margin: 9px 0 8px;
      padding: 0;
      color: #f5f5f5;
      background: #292b2d;
      border: 1px solid #777b7f;
      border-radius: 5px;
      cursor: pointer;
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 0.08em;
    }

    .mute[aria-pressed="true"] {
      background: var(--muted-color);
      border-color: #ff7777;
    }

    .readout {
      height: 30px;
      color: #77d9ed;
      font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
      font-size: 17px;
      font-weight: 800;
      line-height: 30px;
      text-align: center;
    }

    .scale {
      position: relative;
      height: var(--track-height);
      margin-top: 8px;
    }

    .mark {
      position: absolute;
      width: 34px;
      color: var(--secondary-text-color, #a5a8aa);
      font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
      font-size: 10px;
      line-height: 14px;
      transform: translateY(50%);
    }

    .mark.left { left: 0; text-align: right; }
    .mark.right { right: 0; text-align: left; }

    .track-wrap {
      position: absolute;
      top: 0;
      right: 39px;
      bottom: 0;
      left: 39px;
      cursor: ns-resize;
      touch-action: none;
    }

    .track {
      position: absolute;
      top: 0;
      bottom: 0;
      width: 7px;
      overflow: hidden;
      background: #111416;
      border: 1px solid #575b5e;
      border-radius: 5px;
      box-shadow: inset 0 0 3px #000;
    }

    .track.left { left: 10px; }
    .track.right { right: 10px; }

    .meter {
      position: absolute;
      right: 0;
      bottom: 0;
      left: 0;
      height: var(--meter-height);
      background: linear-gradient(to top, var(--meter-green) 0 49%, var(--meter-yellow) 49% 88%, var(--meter-red) 88% 100%);
    }

    .cap {
      position: absolute;
      left: 50%;
      z-index: 1;
      width: 50px;
      height: 20px;
      background: linear-gradient(to bottom, #f1f2f2 0%, #a8aaab 32%, #717477 55%, #d9dada 100%);
      border: 1px solid #313437;
      border-radius: 3px;
      box-shadow: 0 1px 3px #000, inset 0 1px #fff;
      pointer-events: none;
      transform: translate(-50%, 50%);
    }

    .cap::after {
      position: absolute;
      top: 8px;
      right: 5px;
      left: 5px;
      height: 2px;
      background: #fff;
      box-shadow: 0 0 1px #111;
      content: "";
    }
  `;

  constructor() {
    super();
    this._dragPosition = null;
    this._dragging = false;
  }

  setConfig(config) {
    if (!config || typeof config.fader_entity !== "string") {
      throw new Error("audio-fader-card requires a fader_entity");
    }
    this.config = { ...config };
  }

  static getStubConfig() {
    return { fader_entity: "number.waves_lv1_192_168_0_176_ch1_fader" };
  }

  static getConfigForm() {
    return {
      schema: [
        {
          name: "fader_entity",
          selector: { entity: { domain: "number" } },
        },
      ],
    };
  }

  render() {
    if (!this.config) return html``;

    const entities = this._entities;
    const faderState = this._state(entities.fader);
    const faderDb = this._dragging && this._dragPosition !== null
      ? this._positionToDb(this._dragPosition)
      : this._numberState(faderState, -144);
    const position = this._dragging && this._dragPosition !== null
      ? this._dragPosition
      : this._dbToPosition(faderDb);
    const vu = this._numberState(this._state(entities.vu), -144);
    const meterPosition = this._dbToPosition(vu);
    const color = this._safeColor(this._state(entities.color)?.state);
    const name = this._state(entities.name)?.state || "CH";
    const muted = this._state(entities.mute)?.state === "on";

    return html`
      <article class="card">
        <div class="label" style="background-color: ${color}" title="${name}">${name}</div>
        <button class="mute" aria-pressed="${muted}" @click=${this._toggleMute}>MUTE</button>
        <div class="readout">${this._formatDb(faderDb)}</div>
        <div class="scale">
          ${MARKS.map((mark) => html`
            <span class="mark left" style="top: ${100 - mark.position}%">${mark.label}</span>
            <span class="mark right" style="top: ${100 - mark.position}%">${mark.label}</span>
          `)}
          <div class="track-wrap" @pointerdown=${this._startDrag} @pointermove=${this._moveDrag} @pointerup=${this._endDrag} @pointercancel=${this._endDrag}>
            <div class="track left"><div class="meter" style="--meter-height: ${meterPosition}%"></div></div>
            <div class="track right"><div class="meter" style="--meter-height: ${meterPosition}%"></div></div>
            <div class="cap" style="bottom: ${position}%"></div>
          </div>
        </div>
      </article>
    `;
  }

  get _entities() {
    const prefix = this.config.fader_entity.replace(/^number\./, "").replace(/_fader$/, "");
    return {
      fader: this.config.fader_entity,
      name: `sensor.${prefix}_track_name`,
      color: `sensor.${prefix}_color`,
      mute: `switch.${prefix}_mute`,
      vu: `sensor.${prefix}_vu`,
    };
  }

  _state(entityId) {
    return this.hass?.states?.[entityId];
  }

  _numberState(state, fallback) {
    const value = Number(state?.state);
    return Number.isFinite(value) ? clamp(value, -144, 10) : fallback;
  }

  _safeColor(value) {
    return /^#[0-9a-f]{6}$/i.test(value || "") ? value : "#52565b";
  }

  _formatDb(value) {
    return value <= -143.95 ? "-∞" : value.toFixed(1);
  }

  _dbToPosition(db) {
    const value = clamp(Number(db), -144, 10);
    for (let index = 1; index < SCALE.length; index += 1) {
      const lower = SCALE[index - 1];
      const upper = SCALE[index];
      if (value <= upper.db) {
        return lower.position + ((value - lower.db) / (upper.db - lower.db)) * (upper.position - lower.position);
      }
    }
    return 100;
  }

  _positionToDb(position) {
    const value = clamp(Number(position), 0, 100);
    for (let index = 1; index < SCALE.length; index += 1) {
      const lower = SCALE[index - 1];
      const upper = SCALE[index];
      if (value <= upper.position) {
        return lower.db + ((value - lower.position) / (upper.position - lower.position)) * (upper.db - lower.db);
      }
    }
    return 10;
  }

  _positionFromEvent(event) {
    const bounds = event.currentTarget.getBoundingClientRect();
    return clamp(((bounds.bottom - event.clientY) / bounds.height) * 100, 0, 100);
  }

  _startDrag(event) {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    this._dragging = true;
    this._dragPosition = this._positionFromEvent(event);
    this.requestUpdate();
  }

  _moveDrag(event) {
    if (!this._dragging) return;
    this._dragPosition = this._positionFromEvent(event);
    this.requestUpdate();
  }

  _endDrag(event) {
    if (!this._dragging) return;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    const position = this._dragPosition ?? 0;
    const finalVal = Number(clamp(this._positionToDb(position), -144, 10).toFixed(1));
    this._dragging = false;
    this._dragPosition = null;
    this.requestUpdate();
    this.hass?.callService("number", "set_value", {
      entity_id: this.config.fader_entity,
      value: finalVal,
    });
  }

  _toggleMute() {
    this.hass?.callService("switch", "toggle", { entity_id: this._entities.mute });
  }
}

customElements.define("audio-fader-card", AudioFaderCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "audio-fader-card",
  name: "Waves LV1 Audio Fader",
  description: "A vertical Waves eMotion LV1 channel fader.",
  preview: true,
});
