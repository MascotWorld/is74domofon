/**
 * IS74 Domofon Card for Home Assistant
 * 
 * A custom Lovelace card for controlling IS74 intercoms
 */

const LitElement = Object.getPrototypeOf(
  customElements.get("ha-panel-lovelace")
);
const html = LitElement.prototype.html;
const css = LitElement.prototype.css;

class IS74DomofonCard extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      config: { type: Object },
      _activeTab: { type: String },
    };
  }

  constructor() {
    super();
    this._activeTab = "main";
  }

  static get styles() {
    return css`
      :host {
        --card-bg: #1a1a2e;
        --card-border: #16213e;
        --accent-color: #0f3460;
        --accent-bright: #e94560;
        --text-primary: #eaeaea;
        --text-secondary: #a0a0a0;
        --success-color: #4ade80;
        --warning-color: #fbbf24;
        --danger-color: #f87171;
        --button-bg: #0f3460;
        --button-hover: #1a4980;
      }

      .card-container {
        background: var(--card-bg);
        border: 1px solid var(--card-border);
        border-radius: 16px;
        overflow: hidden;
        font-family: 'Segoe UI', system-ui, sans-serif;
      }

      /* Header */
      .card-header {
        background: linear-gradient(135deg, var(--accent-color), var(--card-border));
        padding: 16px 20px;
        display: flex;
        align-items: center;
        justify-content: space-between;
      }

      .header-left {
        display: flex;
        align-items: center;
        gap: 12px;
      }

      .header-icon {
        width: 48px;
        height: 48px;
        background: var(--accent-bright);
        border-radius: 12px;
        display: flex;
        align-items: center;
        justify-content: center;
      }

      .header-icon ha-icon {
        color: white;
        --mdc-icon-size: 28px;
      }

      .header-info h2 {
        margin: 0;
        font-size: 18px;
        font-weight: 600;
        color: var(--text-primary);
      }

      .header-info .subtitle {
        font-size: 12px;
        color: var(--text-secondary);
        margin-top: 2px;
      }

      .status-badge {
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
      }

      .status-online {
        background: rgba(74, 222, 128, 0.2);
        color: var(--success-color);
      }

      .status-offline {
        background: rgba(248, 113, 113, 0.2);
        color: var(--danger-color);
      }

      /* Tabs */
      .tabs {
        display: flex;
        background: rgba(0, 0, 0, 0.2);
        padding: 8px;
        gap: 4px;
      }

      .tab {
        flex: 1;
        padding: 10px;
        text-align: center;
        border-radius: 8px;
        cursor: pointer;
        transition: all 0.2s ease;
        color: var(--text-secondary);
        font-size: 13px;
        font-weight: 500;
      }

      .tab:hover {
        background: rgba(255, 255, 255, 0.05);
      }

      .tab.active {
        background: var(--accent-bright);
        color: white;
      }

      .tab ha-icon {
        --mdc-icon-size: 18px;
        margin-right: 6px;
      }

      /* Content */
      .card-content {
        padding: 16px;
      }

      /* Main Controls */
      .control-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 12px;
        margin-bottom: 16px;
      }

      .control-button {
        aspect-ratio: 1;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 8px;
        background: var(--button-bg);
        border: none;
        border-radius: 16px;
        cursor: pointer;
        transition: all 0.2s ease;
        padding: 16px;
      }

      .control-button:hover {
        background: var(--button-hover);
        transform: translateY(-2px);
      }

      .control-button:active {
        transform: translateY(0);
      }

      .control-button.open {
        background: linear-gradient(135deg, #22c55e, #16a34a);
      }

      .control-button.open:hover {
        background: linear-gradient(135deg, #16a34a, #15803d);
      }

      .control-button.courier {
        background: linear-gradient(135deg, #3b82f6, #2563eb);
      }

      .control-button.courier:hover {
        background: linear-gradient(135deg, #2563eb, #1d4ed8);
      }

      .control-button.reject {
        background: linear-gradient(135deg, #ef4444, #dc2626);
      }

      .control-button.reject:hover {
        background: linear-gradient(135deg, #dc2626, #b91c1c);
      }

      .control-button ha-icon {
        --mdc-icon-size: 32px;
        color: white;
      }

      .control-button span {
        font-size: 12px;
        color: rgba(255, 255, 255, 0.9);
        font-weight: 500;
      }

      /* Status Line */
      .status-line {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 12px 16px;
        background: rgba(255, 255, 255, 0.03);
        border-radius: 12px;
        margin-bottom: 12px;
      }

      .status-line .label {
        display: flex;
        align-items: center;
        gap: 8px;
        color: var(--text-secondary);
        font-size: 13px;
      }

      .status-line .label ha-icon {
        --mdc-icon-size: 18px;
      }

      .status-line .value {
        font-size: 13px;
        font-weight: 500;
        color: var(--text-primary);
      }

      /* Auto-open toggle */
      .toggle-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 16px;
        background: rgba(255, 255, 255, 0.03);
        border-radius: 12px;
        margin-bottom: 12px;
      }

      .toggle-info {
        display: flex;
        align-items: center;
        gap: 12px;
      }

      .toggle-info ha-icon {
        --mdc-icon-size: 24px;
        color: var(--accent-bright);
      }

      .toggle-info .text h4 {
        margin: 0;
        font-size: 14px;
        color: var(--text-primary);
      }

      .toggle-info .text p {
        margin: 4px 0 0;
        font-size: 11px;
        color: var(--text-secondary);
      }

      /* Camera Grid */
      .camera-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 12px;
      }

      .camera-card {
        background: rgba(255, 255, 255, 0.03);
        border-radius: 12px;
        overflow: hidden;
      }

      .camera-preview {
        aspect-ratio: 16/9;
        background: #000;
        display: flex;
        align-items: center;
        justify-content: center;
        position: relative;
      }

      .camera-preview img {
        width: 100%;
        height: 100%;
        object-fit: cover;
      }

      .camera-preview .placeholder {
        color: var(--text-secondary);
        text-align: center;
      }

      .camera-preview .placeholder ha-icon {
        --mdc-icon-size: 48px;
        margin-bottom: 8px;
      }

      .camera-info {
        padding: 12px;
      }

      .camera-info h4 {
        margin: 0;
        font-size: 13px;
        color: var(--text-primary);
      }

      .camera-info .camera-status {
        display: flex;
        align-items: center;
        gap: 6px;
        margin-top: 4px;
        font-size: 11px;
        color: var(--text-secondary);
      }

      .camera-status-dot {
        width: 6px;
        height: 6px;
        border-radius: 50%;
      }

      .camera-status-dot.online {
        background: var(--success-color);
      }

      .camera-status-dot.offline {
        background: var(--danger-color);
      }

      /* Web Panel Button */
      .web-panel-button {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        width: 100%;
        padding: 14px;
        background: var(--button-bg);
        border: none;
        border-radius: 12px;
        cursor: pointer;
        transition: all 0.2s ease;
        color: var(--text-primary);
        font-size: 14px;
        font-weight: 500;
        margin-top: 12px;
      }

      .web-panel-button:hover {
        background: var(--button-hover);
      }

      .web-panel-button ha-icon {
        --mdc-icon-size: 20px;
      }

      /* Settings */
      .settings-section {
        margin-bottom: 16px;
      }

      .settings-section h3 {
        margin: 0 0 12px;
        font-size: 14px;
        color: var(--text-primary);
        font-weight: 600;
      }

      /* Call banner */
      .call-banner {
        background: linear-gradient(135deg, var(--accent-bright), #c81e45);
        padding: 16px;
        border-radius: 12px;
        margin-bottom: 16px;
        animation: pulse 2s infinite;
      }

      @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.8; }
      }

      .call-banner h3 {
        margin: 0;
        color: white;
        font-size: 16px;
        display: flex;
        align-items: center;
        gap: 8px;
      }

      .call-banner p {
        margin: 8px 0 0;
        color: rgba(255, 255, 255, 0.8);
        font-size: 13px;
      }
    `;
  }

  setConfig(config) {
    if (!config.entities) {
      throw new Error("You need to define entities");
    }
    this.config = {
      title: "IS74 Домофон",
      ...config,
    };
  }

  getCardSize() {
    return 4;
  }

  _getEntity(entityId) {
    return this.hass?.states[entityId];
  }

  _callService(domain, service, data) {
    this.hass.callService(domain, service, data);
  }

  _openDoor() {
    const openButton = this.config.entities.open_button;
    if (openButton) {
      this._callService("button", "press", { entity_id: openButton });
    }
  }

  _toggleAutoOpen() {
    const autoOpenSwitch = this.config.entities.auto_open_switch;
    if (autoOpenSwitch) {
      this._callService("switch", "toggle", { entity_id: autoOpenSwitch });
    }
  }

  _toggleCourier() {
    const courierSwitch = this.config.entities.courier_switch;
    if (courierSwitch) {
      this._callService("switch", "toggle", { entity_id: courierSwitch });
    }
  }

  _rejectCall() {
    const rejectButton = this.config.entities.reject_button;
    if (rejectButton) {
      this._callService("button", "press", { entity_id: rejectButton });
    }
  }

  _openWebPanel() {
    const apiUrl = this.config.api_url || "http://localhost:8000";
    window.open(apiUrl, "_blank");
  }

  _setActiveTab(tab) {
    this._activeTab = tab;
  }

  _renderHeader() {
    const deviceSensor = this._getEntity(this.config.entities.device_sensor);
    const isOnline = deviceSensor?.attributes?.is_online ?? false;
    const address = deviceSensor?.attributes?.address ?? "";

    return html`
      <div class="card-header">
        <div class="header-left">
          <div class="header-icon">
            <ha-icon icon="mdi:doorbell-video"></ha-icon>
          </div>
          <div class="header-info">
            <h2>${this.config.title}</h2>
            <div class="subtitle">${address}</div>
          </div>
        </div>
        <div class="status-badge ${isOnline ? "status-online" : "status-offline"}">
          ${isOnline ? "Online" : "Offline"}
        </div>
      </div>
    `;
  }

  _renderTabs() {
    return html`
      <div class="tabs">
        <div 
          class="tab ${this._activeTab === "main" ? "active" : ""}"
          @click=${() => this._setActiveTab("main")}
        >
          <ha-icon icon="mdi:door"></ha-icon>
          Управление
        </div>
        <div 
          class="tab ${this._activeTab === "cameras" ? "active" : ""}"
          @click=${() => this._setActiveTab("cameras")}
        >
          <ha-icon icon="mdi:cctv"></ha-icon>
          Камеры
        </div>
        <div 
          class="tab ${this._activeTab === "settings" ? "active" : ""}"
          @click=${() => this._setActiveTab("settings")}
        >
          <ha-icon icon="mdi:cog"></ha-icon>
          Настройки
        </div>
      </div>
    `;
  }

  _renderMainControls() {
    const autoOpenSwitch = this._getEntity(this.config.entities.auto_open_switch);
    const courierSwitch = this._getEntity(this.config.entities.courier_switch);
    const fcmSensor = this._getEntity(this.config.entities.fcm_sensor);
    
    const isAutoOpen = autoOpenSwitch?.state === "on";
    const isCourier = courierSwitch?.state === "on";
    const fcmStatus = fcmSensor?.state ?? "unknown";

    return html`
      <div class="card-content">
        <div class="control-grid">
          <button class="control-button open" @click=${this._openDoor}>
            <ha-icon icon="mdi:door-open"></ha-icon>
            <span>Открыть</span>
          </button>
          <button class="control-button courier ${isCourier ? "active" : ""}" @click=${this._toggleCourier}>
            <ha-icon icon="mdi:truck-delivery"></ha-icon>
            <span>Курьер</span>
          </button>
          <button class="control-button reject" @click=${this._rejectCall}>
            <ha-icon icon="mdi:phone-hangup"></ha-icon>
            <span>Сброс</span>
          </button>
        </div>

        <div class="toggle-row">
          <div class="toggle-info">
            <ha-icon icon="mdi:door-sliding-lock"></ha-icon>
            <div class="text">
              <h4>Автооткрытие</h4>
              <p>Открывать дверь при звонке</p>
            </div>
          </div>
          <ha-switch
            .checked=${isAutoOpen}
            @change=${this._toggleAutoOpen}
          ></ha-switch>
        </div>

        <div class="status-line">
          <div class="label">
            <ha-icon icon="mdi:bell-ring"></ha-icon>
            Push уведомления
          </div>
          <div class="value">${fcmStatus === "active" ? "Активны" : "Неактивны"}</div>
        </div>

        <button class="web-panel-button" @click=${this._openWebPanel}>
          <ha-icon icon="mdi:web"></ha-icon>
          Открыть веб-панель
        </button>
      </div>
    `;
  }

  _renderCameras() {
    const cameras = this.config.entities.cameras || [];

    return html`
      <div class="card-content">
        <div class="camera-grid">
          ${cameras.map(cameraId => {
            const camera = this._getEntity(cameraId);
            const isOnline = camera?.attributes?.is_online ?? false;
            const name = camera?.attributes?.friendly_name ?? "Камера";
            
            return html`
              <div class="camera-card">
                <div class="camera-preview">
                  ${camera?.attributes?.entity_picture 
                    ? html`<img src="${camera.attributes.entity_picture}" alt="${name}" />`
                    : html`
                      <div class="placeholder">
                        <ha-icon icon="mdi:camera-off"></ha-icon>
                        <div>Нет изображения</div>
                      </div>
                    `
                  }
                </div>
                <div class="camera-info">
                  <h4>${name}</h4>
                  <div class="camera-status">
                    <span class="camera-status-dot ${isOnline ? "online" : "offline"}"></span>
                    ${isOnline ? "Online" : "Offline"}
                  </div>
                </div>
              </div>
            `;
          })}
          ${cameras.length === 0 ? html`
            <div class="camera-card">
              <div class="camera-preview">
                <div class="placeholder">
                  <ha-icon icon="mdi:camera-off"></ha-icon>
                  <div>Нет камер</div>
                </div>
              </div>
            </div>
          ` : ""}
        </div>
      </div>
    `;
  }

  _renderSettings() {
    const fcmSwitch = this._getEntity(this.config.entities.fcm_switch);
    const serviceSensor = this._getEntity(this.config.entities.service_sensor);
    
    const isFcmEnabled = fcmSwitch?.state === "on";
    const serviceStatus = serviceSensor?.state ?? "unknown";
    const isAuthenticated = serviceSensor?.attributes?.authenticated ?? false;

    return html`
      <div class="card-content">
        <div class="settings-section">
          <h3>Сервис</h3>
          <div class="status-line">
            <div class="label">
              <ha-icon icon="mdi:server"></ha-icon>
              Статус
            </div>
            <div class="value">${serviceStatus === "running" ? "Работает" : "Остановлен"}</div>
          </div>
          <div class="status-line">
            <div class="label">
              <ha-icon icon="mdi:account-check"></ha-icon>
              Авторизация
            </div>
            <div class="value">${isAuthenticated ? "Да" : "Нет"}</div>
          </div>
        </div>

        <div class="settings-section">
          <h3>Push уведомления</h3>
          <div class="toggle-row">
            <div class="toggle-info">
              <ha-icon icon="mdi:bell-ring"></ha-icon>
              <div class="text">
                <h4>FCM Listener</h4>
                <p>Получать уведомления о звонках</p>
              </div>
            </div>
            <ha-switch
              .checked=${isFcmEnabled}
              @change=${() => this._callService("switch", "toggle", { entity_id: this.config.entities.fcm_switch })}
            ></ha-switch>
          </div>
        </div>

        <button class="web-panel-button" @click=${this._openWebPanel}>
          <ha-icon icon="mdi:web"></ha-icon>
          Открыть веб-панель
        </button>
      </div>
    `;
  }

  render() {
    if (!this.hass || !this.config) {
      return html``;
    }

    return html`
      <ha-card>
        <div class="card-container">
          ${this._renderHeader()}
          ${this._renderTabs()}
          ${this._activeTab === "main" ? this._renderMainControls() : ""}
          ${this._activeTab === "cameras" ? this._renderCameras() : ""}
          ${this._activeTab === "settings" ? this._renderSettings() : ""}
        </div>
      </ha-card>
    `;
  }

  static getConfigElement() {
    return document.createElement("is74-domofon-card-editor");
  }

  static getStubConfig() {
    return {
      title: "IS74 Домофон",
      api_url: "http://localhost:8000",
      entities: {
        device_sensor: "sensor.is74_domofon_status",
        service_sensor: "sensor.is74_service_status",
        fcm_sensor: "sensor.is74_fcm_push",
        open_button: "button.is74_open_door",
        reject_button: "button.is74_reject_call",
        auto_open_switch: "switch.is74_auto_open",
        courier_switch: "switch.is74_courier",
        fcm_switch: "switch.is74_fcm",
        cameras: [],
      },
    };
  }
}

// Card Editor
class IS74DomofonCardEditor extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      _config: { type: Object },
    };
  }

  setConfig(config) {
    this._config = config;
  }

  static get styles() {
    return css`
      .editor-container {
        padding: 16px;
      }
      
      .form-row {
        margin-bottom: 16px;
      }
      
      .form-row label {
        display: block;
        margin-bottom: 4px;
        font-weight: 500;
      }
      
      .form-row input {
        width: 100%;
        padding: 8px;
        border: 1px solid var(--divider-color);
        border-radius: 4px;
      }
    `;
  }

  render() {
    if (!this.hass || !this._config) {
      return html``;
    }

    return html`
      <div class="editor-container">
        <div class="form-row">
          <label>Название</label>
          <input
            type="text"
            .value=${this._config.title || ""}
            @input=${(e) => this._updateConfig("title", e.target.value)}
          />
        </div>
        <div class="form-row">
          <label>URL веб-панели</label>
          <input
            type="text"
            .value=${this._config.api_url || "http://localhost:8000"}
            @input=${(e) => this._updateConfig("api_url", e.target.value)}
          />
        </div>
        <p>Сущности настраиваются автоматически при добавлении интеграции.</p>
      </div>
    `;
  }

  _updateConfig(key, value) {
    this._config = { ...this._config, [key]: value };
    const event = new CustomEvent("config-changed", {
      detail: { config: this._config },
      bubbles: true,
      composed: true,
    });
    this.dispatchEvent(event);
  }
}

customElements.define("is74-domofon-card", IS74DomofonCard);
customElements.define("is74-domofon-card-editor", IS74DomofonCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "is74-domofon-card",
  name: "IS74 Домофон",
  description: "Карточка для управления домофоном IS74",
  preview: true,
});

console.info(
  `%c IS74-DOMOFON-CARD %c v1.0.0 `,
  "color: white; background: #e94560; font-weight: bold;",
  "color: #e94560; background: white; font-weight: bold;"
);

