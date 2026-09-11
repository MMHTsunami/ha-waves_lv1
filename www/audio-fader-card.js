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
    _dragIndex: { state: true },
    _dragPosition: { state: true },
  };

  static styles = css`
    :host {
      display: block;
      --fader-width: 156px;
      --fader-gap: 8px;
      --track-height: 320px;
      --muted-color: #d32626;
      --meter-green: #37bd67;
      --meter-yellow: #e2c33a;
      --meter-red: #e34d42;
      color: var(--primary-text-color, #e8e8e8);
      font-family: var(--paper-font-body1_-_font-family, sans-serif);
    }

    .card {
      box-sizing: border-box;
      width: min(100%, calc(var(--fader-count) * var(--fader-width) + (var(--fader-count) - 1) * var(--fader-gap) + 20px));
      max-width: 100%;
      min-height: 0;
      padding: 8px 10px 12px;
      overflow: hidden;
      background: var(--card-background-color, #202124);
      border: 1px solid var(--divider-color, #494949);
      border-radius: 4px;
      user-select: none;
    }

    .faders {
      display: grid;
      grid-template-columns: repeat(var(--fader-count), minmax(0, 1fr));
      gap: var(--fader-gap);
      width: 100%;
      padding-bottom: 2px;
    }

    .strip {
      min-width: 0;
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

    .track.left { left: 22px; }
    .track.right { right: 22px; }

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
      transform: translateX(-50%);
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
    this._dragIndex = null;
    this._dragPosition = null;
    this._lastSentValue = null;
  }

  setConfig(config) {
    const faderEntities = Array.isArray(config?.fader_entities)
      ? config.fader_entities
      : [config?.fader_entity];
    if (
      faderEntities.length === 0 ||
      faderEntities.length > 8 ||
      faderEntities.some((entityId) => typeof entityId !== "string" || !entityId)
    ) {
      throw new Error("audio-fader-card requires 1 to 8 fader_entities");
    }
    this.config = { ...config, fader_entities: faderEntities };
  }

  static getStubConfig() {
    return { fader_entity: "number.waves_lv1_192_168_0_176_ch1_fader" };
  }

  static getConfigForm() {
    return {
      schema: [
        {
          name: "fader_entities",
          selector: { entity: { domain: "number", multiple: true } },
        },
      ],
    };
  }

  render() {
    if (!this.config) return html``;

    const faderEntities = this._faderEntities;

    return html`
      <article class="card" style="--fader-count: ${faderEntities.length}">
        <div class="faders">
          ${faderEntities.map((faderEntity, index) => this._renderFader(faderEntity, index))}
        </div>
      </article>
    `;
  }

  get _faderEntities() {
    return this.config?.fader_entities || [this.config?.fader_entity];
  }

  _entities(faderEntity) {
    const prefix = faderEntity.replace(/^number\./, "").replace(/_fader$/, "");
    return {
      fader: faderEntity,
      name: `sensor.${prefix}_track_name`,
      color: `sensor.${prefix}_color`,
      mute: `switch.${prefix}_mute`,
      vu: `sensor.${prefix}_vu`,
    };
  }

  _renderFader(faderEntity, index) {
    const entities = this._entities(faderEntity);
    const faderState = this._state(entities.fader);
    const dragging = this._dragIndex === index && this._dragPosition !== null;
    const faderDb = dragging
      ? this._positionToDb(this._dragPosition)
      : this._numberState(faderState, -144);
    const position = dragging ? this._dragPosition : this._dbToPosition(faderDb);
    const vu = this._numberState(this._state(entities.vu), -144);
    const meterPosition = this._dbToPosition(vu);
    const color = this._safeColor(this._state(entities.color)?.state);
    const name = this._state(entities.name)?.state || "CH";
    const muted = this._state(entities.mute)?.state === "on";

    return html`
      <section class="strip">
        <div class="label" style="background-color: ${color}" title="${name}">${name}</div>
        <button class="mute" data-index="${index}" aria-pressed="${muted}" @click=${this._toggleMute}>MUTE</button>
        <div class="readout">${this._formatDb(faderDb)}</div>
        <div class="scale">
          ${MARKS.map((mark) => html`
            <span class="mark left" style="bottom: calc(${mark.position}% - 7px)">${mark.label}</span>
            <span class="mark right" style="bottom: calc(${mark.position}% - 7px)">${mark.label}</span>
          `)}
          <div class="track-wrap" data-index="${index}" @pointerdown=${this._startDrag} @pointermove=${this._moveDrag} @pointerup=${this._endDrag} @pointercancel=${this._endDrag}>
            <div class="track left"><div class="meter" style="--meter-height: ${meterPosition}%"></div></div>
            <div class="track right"><div class="meter" style="--meter-height: ${meterPosition}%"></div></div>
            <div class="cap" style="bottom: calc(${position}% - 11px)"></div>
          </div>
        </div>
      </section>
    `;
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
    this._dragIndex = Number(event.currentTarget.dataset.index);
    this._dragPosition = this._positionFromEvent(event);
    this._lastSentValue = null;
    this._sendFaderValue(this._dragIndex, this._dragPosition);
    this.requestUpdate();
  }

  _moveDrag(event) {
    if (this._dragIndex === null) return;
    this._dragPosition = this._positionFromEvent(event);
    this._sendFaderValue(this._dragIndex, this._dragPosition);
    this.requestUpdate();
  }

  _endDrag(event) {
    if (this._dragIndex === null) return;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    const position = this._dragPosition ?? 0;
    this._sendFaderValue(this._dragIndex, position);
    this._dragIndex = null;
    this._dragPosition = null;
    this._lastSentValue = null;
    this.requestUpdate();
  }

  _sendFaderValue(index, position) {
    const finalVal = Number(clamp(this._positionToDb(position), -144, 10).toFixed(1));
    if (finalVal === this._lastSentValue) return;
    this._lastSentValue = finalVal;
    this.hass?.callService("number", "set_value", {
      entity_id: this._faderEntities[index],
      value: finalVal,
    });
  }

  _toggleMute(event) {
    const index = Number(event.currentTarget.dataset.index);
    const entities = this._entities(this._faderEntities[index]);
    this.hass?.callService("switch", "toggle", { entity_id: entities.mute });
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
