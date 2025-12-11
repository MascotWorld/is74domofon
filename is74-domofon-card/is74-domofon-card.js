/**
 * IS74 Domofon Card for Home Assistant
 * 
 * A custom Lovelace card for controlling IS74 intercoms
 */

class IS74DomofonCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._activeTab = 'main';
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  setConfig(config) {
    if (!config.entities) {
      throw new Error("You need to define entities");
    }
    this._config = {
      title: "IS74 Домофон",
      api_url: "http://localhost:8000",
      ...config,
    };
  }

  getCardSize() {
    return 4;
  }

  _getEntity(entityId) {
    return this._hass?.states[entityId];
  }

  _callService(domain, service, data) {
    this._hass.callService(domain, service, data);
  }

  _openDoor() {
    const openButton = this._config.entities.open_button;
    if (openButton) {
      this._callService("button", "press", { entity_id: openButton });
    }
  }

  _toggleAutoOpen() {
    const autoOpenSwitch = this._config.entities.auto_open_switch;
    if (autoOpenSwitch) {
      this._callService("switch", "toggle", { entity_id: autoOpenSwitch });
    }
  }

  _toggleCourier() {
    const courierSwitch = this._config.entities.courier_switch;
    if (courierSwitch) {
      this._callService("switch", "toggle", { entity_id: courierSwitch });
    }
  }

  _rejectCall() {
    const rejectButton = this._config.entities.reject_button;
    if (rejectButton) {
      this._callService("button", "press", { entity_id: rejectButton });
    }
  }

  _openWebPanel() {
    const apiUrl = this._config.api_url || "http://localhost:8000";
    window.open(apiUrl, "_blank");
  }

  _setActiveTab(tab) {
    this._activeTab = tab;
    this._render();
  }

  _render() {
    if (!this._hass || !this._config) return;

    const deviceSensor = this._getEntity(this._config.entities.device_sensor);
    const autoOpenSwitch = this._getEntity(this._config.entities.auto_open_switch);
    const courierSwitch = this._getEntity(this._config.entities.courier_switch);
    const fcmSensor = this._getEntity(this._config.entities.fcm_sensor);
    const fcmSwitch = this._getEntity(this._config.entities.fcm_switch);
    const serviceSensor = this._getEntity(this._config.entities.service_sensor);

    const isOnline = deviceSensor?.attributes?.is_online ?? false;
    const address = deviceSensor?.attributes?.address ?? "";
    const isAutoOpen = autoOpenSwitch?.state === "on";
    const isCourier = courierSwitch?.state === "on";
    const fcmStatus = fcmSensor?.state ?? "unknown";
    const isFcmEnabled = fcmSwitch?.state === "on";
    const serviceStatus = serviceSensor?.state ?? "unknown";
    const isAuthenticated = serviceSensor?.attributes?.authenticated ?? false;

    const cameras = this._config.entities.cameras || [];

    this.shadowRoot.innerHTML = `
      <style>
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
          border: none;
          background: transparent;
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

        .card-content {
          padding: 16px;
        }

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

        .control-button.courier.active {
          box-shadow: 0 0 20px rgba(59, 130, 246, 0.5);
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

        .toggle-button {
          width: 50px;
          height: 26px;
          border-radius: 13px;
          border: none;
          cursor: pointer;
          position: relative;
          transition: background 0.2s;
          background: #555;
        }

        .toggle-button.on {
          background: var(--success-color);
        }

        .toggle-button::after {
          content: '';
          position: absolute;
          width: 22px;
          height: 22px;
          border-radius: 50%;
          background: white;
          top: 2px;
          left: 2px;
          transition: transform 0.2s;
        }

        .toggle-button.on::after {
          transform: translateX(24px);
        }

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
          display: block;
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

        .settings-section {
          margin-bottom: 16px;
        }

        .settings-section h3 {
          margin: 0 0 12px;
          font-size: 14px;
          color: var(--text-primary);
          font-weight: 600;
        }

        .hidden {
          display: none !important;
        }
      </style>

      <ha-card>
        <div class="card-container">
          <!-- Header -->
          <div class="card-header">
            <div class="header-left">
              <div class="header-icon">
                <ha-icon icon="mdi:doorbell-video"></ha-icon>
              </div>
              <div class="header-info">
                <h2>${this._config.title}</h2>
                <div class="subtitle">${address || 'Домофон'}</div>
              </div>
            </div>
            <div class="status-badge ${isOnline ? 'status-online' : 'status-offline'}">
              ${isOnline ? 'Online' : 'Offline'}
            </div>
          </div>

          <!-- Tabs -->
          <div class="tabs">
            <button class="tab ${this._activeTab === 'main' ? 'active' : ''}" id="tab-main">
              <ha-icon icon="mdi:door"></ha-icon>
              Управление
            </button>
            <button class="tab ${this._activeTab === 'cameras' ? 'active' : ''}" id="tab-cameras">
              <ha-icon icon="mdi:cctv"></ha-icon>
              Камеры
            </button>
            <button class="tab ${this._activeTab === 'settings' ? 'active' : ''}" id="tab-settings">
              <ha-icon icon="mdi:cog"></ha-icon>
              Настройки
            </button>
          </div>

          <!-- Main Tab -->
          <div class="card-content ${this._activeTab !== 'main' ? 'hidden' : ''}" id="content-main">
            <div class="control-grid">
              <button class="control-button open" id="btn-open">
                <ha-icon icon="mdi:door-open"></ha-icon>
                <span>Открыть</span>
              </button>
              <button class="control-button courier ${isCourier ? 'active' : ''}" id="btn-courier">
                <ha-icon icon="mdi:truck-delivery"></ha-icon>
                <span>Курьер</span>
              </button>
              <button class="control-button reject" id="btn-reject">
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
              <button class="toggle-button ${isAutoOpen ? 'on' : ''}" id="btn-auto-open"></button>
            </div>

            <div class="status-line">
              <div class="label">
                <ha-icon icon="mdi:bell-ring"></ha-icon>
                Push уведомления
              </div>
              <div class="value">${fcmStatus === 'active' ? 'Активны' : 'Неактивны'}</div>
            </div>

            <button class="web-panel-button" id="btn-web-panel">
              <ha-icon icon="mdi:web"></ha-icon>
              Открыть веб-панель
            </button>
          </div>

          <!-- Cameras Tab -->
          <div class="card-content ${this._activeTab !== 'cameras' ? 'hidden' : ''}" id="content-cameras">
            <div class="camera-grid">
              ${cameras.length > 0 ? cameras.map(cameraId => {
                const camera = this._getEntity(cameraId);
                const camOnline = camera?.state === 'idle' || camera?.attributes?.is_online;
                const camName = camera?.attributes?.friendly_name ?? 'Камера';
                const entityPicture = camera?.attributes?.entity_picture;
                
                return `
                  <div class="camera-card">
                    <div class="camera-preview">
                      ${entityPicture 
                        ? `<img src="${entityPicture}" alt="${camName}" />`
                        : `<div class="placeholder">
                            <ha-icon icon="mdi:camera-off"></ha-icon>
                            <div>Нет изображения</div>
                          </div>`
                      }
                    </div>
                    <div class="camera-info">
                      <h4>${camName}</h4>
                      <div class="camera-status">
                        <span class="camera-status-dot ${camOnline ? 'online' : 'offline'}"></span>
                        ${camOnline ? 'Online' : 'Offline'}
                      </div>
                    </div>
                  </div>
                `;
              }).join('') : `
                <div class="camera-card">
                  <div class="camera-preview">
                    <div class="placeholder">
                      <ha-icon icon="mdi:camera-off"></ha-icon>
                      <div>Нет камер</div>
                    </div>
                  </div>
                </div>
              `}
            </div>
          </div>

          <!-- Settings Tab -->
          <div class="card-content ${this._activeTab !== 'settings' ? 'hidden' : ''}" id="content-settings">
            <div class="settings-section">
              <h3>Сервис</h3>
              <div class="status-line">
                <div class="label">
                  <ha-icon icon="mdi:server"></ha-icon>
                  Статус
                </div>
                <div class="value">${serviceStatus === 'running' ? 'Работает' : 'Остановлен'}</div>
              </div>
              <div class="status-line">
                <div class="label">
                  <ha-icon icon="mdi:account-check"></ha-icon>
                  Авторизация
                </div>
                <div class="value">${isAuthenticated ? 'Да' : 'Нет'}</div>
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
                <button class="toggle-button ${isFcmEnabled ? 'on' : ''}" id="btn-fcm"></button>
              </div>
            </div>

            <button class="web-panel-button" id="btn-web-panel-2">
              <ha-icon icon="mdi:web"></ha-icon>
              Открыть веб-панель
            </button>
          </div>
        </div>
      </ha-card>
    `;

    // Add event listeners
    this.shadowRoot.getElementById('tab-main').addEventListener('click', () => this._setActiveTab('main'));
    this.shadowRoot.getElementById('tab-cameras').addEventListener('click', () => this._setActiveTab('cameras'));
    this.shadowRoot.getElementById('tab-settings').addEventListener('click', () => this._setActiveTab('settings'));
    
    this.shadowRoot.getElementById('btn-open').addEventListener('click', () => this._openDoor());
    this.shadowRoot.getElementById('btn-courier').addEventListener('click', () => this._toggleCourier());
    this.shadowRoot.getElementById('btn-reject').addEventListener('click', () => this._rejectCall());
    this.shadowRoot.getElementById('btn-auto-open').addEventListener('click', () => this._toggleAutoOpen());
    this.shadowRoot.getElementById('btn-web-panel').addEventListener('click', () => this._openWebPanel());
    this.shadowRoot.getElementById('btn-web-panel-2')?.addEventListener('click', () => this._openWebPanel());
    
    const fcmBtn = this.shadowRoot.getElementById('btn-fcm');
    if (fcmBtn) {
      fcmBtn.addEventListener('click', () => {
        const fcmSwitch = this._config.entities.fcm_switch;
        if (fcmSwitch) {
          this._callService("switch", "toggle", { entity_id: fcmSwitch });
        }
      });
    }
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

// Simple editor
class IS74DomofonCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
  }

  set hass(hass) {
    this._hass = hass;
  }

  setConfig(config) {
    this._config = config;
    this._render();
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        .editor {
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
          border: 1px solid var(--divider-color, #ccc);
          border-radius: 4px;
          box-sizing: border-box;
        }
      </style>
      <div class="editor">
        <div class="form-row">
          <label>Название</label>
          <input type="text" id="title" value="${this._config?.title || 'IS74 Домофон'}" />
        </div>
        <div class="form-row">
          <label>URL веб-панели</label>
          <input type="text" id="api_url" value="${this._config?.api_url || 'http://localhost:8000'}" />
        </div>
        <p>Сущности настраиваются в YAML конфигурации карточки.</p>
      </div>
    `;

    this.shadowRoot.getElementById('title').addEventListener('input', (e) => {
      this._updateConfig('title', e.target.value);
    });
    this.shadowRoot.getElementById('api_url').addEventListener('input', (e) => {
      this._updateConfig('api_url', e.target.value);
    });
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

// Register elements
customElements.define("is74-domofon-card", IS74DomofonCard);
customElements.define("is74-domofon-card-editor", IS74DomofonCardEditor);

// Register card
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
