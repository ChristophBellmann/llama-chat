class LocalChatPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });

    this._hass = null;
    this._panel = null;
    this._ready = false;

    this._audioStream = null;
    this._audioContext = null;
    this._audioSource = null;
    this._audioProcessor = null;
    this._audioSinkGain = null;

    this._pipelineUnsubscribe = null;
    this._pipelineDoneResolver = null;
    this._pipelineHandlerId = null;
    this._pipelineResultText = "";
    this._pipelineError = null;
    this._pipelineRunActive = false;
    this._audioQueue = [];

    this._currentUtterance = null;
    this._continuousEnabled = false;
    this._continuousLoop = false;
    this._noticeDedup = new Map();
    this._voicesListenerBound = false;

    this.state = {
      language: "de",
      agentId: "conversation.locales_llm_ai_agent",
      ttsScriptEntityId: "script.tts_ansage",
      targetPlayer: "echo_base",
      speakAnswer: false,
      speakInBrowser: false,
      browserRate: 1.15,
      piperVoice: "",
      piperSpeedProfile: "normal",
      piperTtsEntityNormal: "tts.piper",
      piperTtsEntityFast: "tts.piper_fast",
      piperTtsEntitySlow: "tts.piper_slow",
      browserVoiceName: "",
      conversationId: null,
      pipelineId: null,
      micReady: false,
      micOpen: false,
      listening: false,
      vadThreshold: 0.012,
      silenceMs: 550,
      noSpeechTimeoutMs: 3000,
      maxUtteranceMs: 25000,
    };
  }

  set panel(panel) {
    this._panel = panel;
    this._applyPanelConfig();
  }

  set hass(hass) {
    this._hass = hass;
    this._applyPanelConfig();
    if (!this._ready) {
      this._render();
      this._wireEvents();
      this._ready = true;
      this._boot();
    }
  }

  _applyPanelConfig() {
    const conf = (this._panel && this._panel.config) || {};
    if (conf.language) this.state.language = conf.language;
    if (conf.local_llm_agent_id) this.state.agentId = conf.local_llm_agent_id;
    if (conf.tts_script_entity_id) this.state.ttsScriptEntityId = conf.tts_script_entity_id;
    if (conf.default_target_player) this.state.targetPlayer = conf.default_target_player;
    if (conf.default_piper_voice) this.state.piperVoice = conf.default_piper_voice;
    if (conf.default_piper_speed_profile) this.state.piperSpeedProfile = conf.default_piper_speed_profile;
    if (conf.piper_tts_entity_normal) this.state.piperTtsEntityNormal = conf.piper_tts_entity_normal;
    if (conf.piper_tts_entity_fast) this.state.piperTtsEntityFast = conf.piper_tts_entity_fast;
    if (conf.piper_tts_entity_slow) this.state.piperTtsEntitySlow = conf.piper_tts_entity_slow;
  }

  async _boot() {
    this._setStatus("Bereit");
    await this._detectPreferredPipeline();
    this._refreshBrowserVoices();
    if ("speechSynthesis" in window && !this._voicesListenerBound) {
      window.speechSynthesis.addEventListener("voiceschanged", () => this._refreshBrowserVoices());
      this._voicesListenerBound = true;
    }
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          height: 100%;
          color: var(--primary-text-color);
          background: var(--primary-background-color);
          font-family: var(--primary-font-family);
        }
        .wrap {
          display: grid;
          grid-template-rows: auto auto 1fr auto auto;
          height: 100%;
          gap: 10px;
          padding: 12px;
          box-sizing: border-box;
        }
        .row {
          display: flex;
          gap: 8px;
          align-items: center;
          flex-wrap: wrap;
        }
        .status {
          font-size: 13px;
          opacity: 0.85;
        }
        .chat {
          border: 1px solid var(--divider-color);
          border-radius: 8px;
          padding: 8px;
          overflow: auto;
          min-height: 220px;
          background: var(--card-background-color);
        }
        .msg {
          margin: 0 0 8px 0;
          padding: 8px 10px;
          border-radius: 8px;
          max-width: 92%;
          white-space: pre-wrap;
          line-height: 1.35;
          font-size: 14px;
        }
        .msg.user {
          margin-left: auto;
          background: rgba(33, 150, 243, 0.18);
          border: 1px solid rgba(33, 150, 243, 0.35);
        }
        .msg.assistant {
          margin-right: auto;
          background: rgba(120, 120, 120, 0.15);
          border: 1px solid rgba(120, 120, 120, 0.3);
        }
        .msg.system {
          margin-right: auto;
          background: rgba(255, 152, 0, 0.14);
          border: 1px solid rgba(255, 152, 0, 0.3);
          font-size: 13px;
        }
        textarea {
          width: 100%;
          min-height: 80px;
          resize: vertical;
          box-sizing: border-box;
          border-radius: 8px;
          border: 1px solid var(--divider-color);
          background: var(--card-background-color);
          color: var(--primary-text-color);
          padding: 10px;
          font: inherit;
        }
        button, select, input[type="range"] {
          font: inherit;
        }
        button {
          border: 1px solid var(--divider-color);
          background: var(--card-background-color);
          color: var(--primary-text-color);
          padding: 8px 12px;
          border-radius: 8px;
          cursor: pointer;
        }
        button.primary {
          background: var(--primary-color);
          border-color: var(--primary-color);
          color: var(--text-primary-color, #fff);
        }
        button:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }
        .small {
          font-size: 12px;
          opacity: 0.8;
        }
      </style>
      <div class="wrap">
        <div class="row">
          <strong>Chat</strong>
          <span id="status" class="status">Initialisiere...</span>
        </div>
        <div class="row">
          <label for="player">Ziel:</label>
          <select id="player">
            <option value="echo_base">Echo Base</option>
            <option value="sat1">SAT1</option>
            <option value="all">Alle</option>
          </select>
          <label><input id="speakAnswer" type="checkbox"> Lautsprecher (Piper)</label>
          <label><input id="speakBrowser" type="checkbox"> Browser lokal sprechen</label>
          <button id="clearChat" title="Chatverlauf leeren">Verlauf leeren</button>
        </div>
        <div class="row small">
          <label for="piperVoice">Piper-Stimme:</label>
          <select id="piperVoice">
            <option value="">Standard</option>
            <option value="de_DE-ramona-low">ramona (low)</option>
            <option value="de_DE-mls-medium">mls (medium)</option>
            <option value="de_DE-mls-high">mls (high)</option>
            <option value="de_DE-thorsten-high">thorsten (high)</option>
            <option value="custom">Benutzerdefiniert...</option>
          </select>
          <input id="piperVoiceCustom" type="text" placeholder="z. B. de_DE-ramona-low" style="display:none; min-width:220px;">
          <label for="piperSpeed">Piper-Tempo:</label>
          <select id="piperSpeed">
            <option value="fast">Fast (0.65)</option>
            <option value="normal">Normal (0.95)</option>
            <option value="slow">Langsam (1.35)</option>
          </select>
          <label for="browserVoice">Browser-Stimme:</label>
          <select id="browserVoice">
            <option value="">Standard (Browser)</option>
          </select>
          <label for="browserRate">Browser-Speed:</label>
          <input id="browserRate" type="range" min="0.8" max="1.8" step="0.05" value="1.15">
          <span id="browserRateValue">1.15x</span>
        </div>
        <div id="chat" class="chat"></div>
        <div class="row" style="display:block">
          <textarea id="input" placeholder="Frage eingeben..."></textarea>
          <div class="row" style="margin-top:8px">
            <button id="send" class="primary">Senden</button>
          </div>
        </div>
        <div>
          <div class="row">
            <button id="voiceOnce">Voice (einmal)</button>
            <label><input id="voiceContinuous" type="checkbox"> Kontinuierlich (experimentell, VAD)</label>
            <button id="voiceToggle">Start kontinuierlich</button>
          </div>
          <div class="row small">
            <span>Mikrofon: <span id="micState">inaktiv</span></span>
            <span>Pipeline: <span id="pipelineState">unbekannt</span></span>
          </div>
          <div class="row small">
            <label for="vad">VAD:</label>
            <input id="vad" type="range" min="4" max="40" value="12">
            <span id="vadValue">0.012</span>
            <label for="endpause">Endpause:</label>
            <input id="endpause" type="range" min="250" max="1200" step="50" value="550">
            <span id="endpauseValue">550 ms</span>
          </div>
        </div>
      </div>
    `;

    this.$ = {
      status: this.shadowRoot.querySelector("#status"),
      chat: this.shadowRoot.querySelector("#chat"),
      input: this.shadowRoot.querySelector("#input"),
      send: this.shadowRoot.querySelector("#send"),
      clearChat: this.shadowRoot.querySelector("#clearChat"),
      player: this.shadowRoot.querySelector("#player"),
      speakAnswer: this.shadowRoot.querySelector("#speakAnswer"),
      speakBrowser: this.shadowRoot.querySelector("#speakBrowser"),
      piperVoice: this.shadowRoot.querySelector("#piperVoice"),
      piperVoiceCustom: this.shadowRoot.querySelector("#piperVoiceCustom"),
      piperSpeed: this.shadowRoot.querySelector("#piperSpeed"),
      browserVoice: this.shadowRoot.querySelector("#browserVoice"),
      browserRate: this.shadowRoot.querySelector("#browserRate"),
      browserRateValue: this.shadowRoot.querySelector("#browserRateValue"),
      voiceOnce: this.shadowRoot.querySelector("#voiceOnce"),
      voiceContinuous: this.shadowRoot.querySelector("#voiceContinuous"),
      voiceToggle: this.shadowRoot.querySelector("#voiceToggle"),
      micState: this.shadowRoot.querySelector("#micState"),
      pipelineState: this.shadowRoot.querySelector("#pipelineState"),
      vad: this.shadowRoot.querySelector("#vad"),
      vadValue: this.shadowRoot.querySelector("#vadValue"),
      endpause: this.shadowRoot.querySelector("#endpause"),
      endpauseValue: this.shadowRoot.querySelector("#endpauseValue"),
    };

    this.$.player.value = this.state.targetPlayer;
    this.$.speakAnswer.checked = this.state.speakAnswer;
    this.$.speakBrowser.checked = this.state.speakInBrowser;
    this._syncPiperVoiceUiFromState();
    this.$.piperSpeed.value = this.state.piperSpeedProfile;
    this.$.browserRate.value = String(this.state.browserRate);
    this.$.browserRateValue.textContent = `${this.state.browserRate.toFixed(2)}x`;
    this.$.vad.value = String(Math.round(this.state.vadThreshold * 1000));
    this.$.vadValue.textContent = this.state.vadThreshold.toFixed(3);
    this.$.endpause.value = String(this.state.silenceMs);
    this.$.endpauseValue.textContent = `${this.state.silenceMs} ms`;
  }

  _wireEvents() {
    this.$.send.addEventListener("click", () => this._sendText());
    this.$.input.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" && !ev.shiftKey) {
        ev.preventDefault();
        this._sendText();
      }
    });
    this.$.clearChat.addEventListener("click", () => {
      this.$.chat.innerHTML = "";
      this.state.conversationId = null;
      this._appendSystem("Verlauf geleert.");
    });
    this.$.player.addEventListener("change", () => {
      this.state.targetPlayer = this.$.player.value;
    });
    this.$.speakAnswer.addEventListener("change", () => {
      this.state.speakAnswer = this.$.speakAnswer.checked;
    });
    this.$.speakBrowser.addEventListener("change", () => {
      this.state.speakInBrowser = this.$.speakBrowser.checked;
    });
    this.$.piperVoice.addEventListener("change", () => {
      if (this.$.piperVoice.value === "custom") {
        this.$.piperVoiceCustom.style.display = "";
        this.state.piperVoice = this.$.piperVoiceCustom.value.trim();
      } else {
        this.$.piperVoiceCustom.style.display = "none";
        this.state.piperVoice = this.$.piperVoice.value;
      }
    });
    this.$.piperVoiceCustom.addEventListener("input", () => {
      if (this.$.piperVoice.value === "custom") {
        this.state.piperVoice = this.$.piperVoiceCustom.value.trim();
      }
    });
    this.$.piperSpeed.addEventListener("change", () => {
      this.state.piperSpeedProfile = this.$.piperSpeed.value;
    });
    this.$.browserVoice.addEventListener("change", () => {
      this.state.browserVoiceName = this.$.browserVoice.value;
    });
    this.$.browserRate.addEventListener("input", () => {
      this.state.browserRate = Number(this.$.browserRate.value);
      this.$.browserRateValue.textContent = `${this.state.browserRate.toFixed(2)}x`;
    });
    this.$.voiceOnce.addEventListener("click", () => this._startSingleVoiceRun());
    this.$.voiceContinuous.addEventListener("change", () => {
      this._continuousEnabled = this.$.voiceContinuous.checked;
      if (!this._continuousEnabled && this._continuousLoop) {
        this._stopContinuousVoice();
      }
    });
    this.$.voiceToggle.addEventListener("click", async () => {
      if (this._continuousLoop) {
        this._stopContinuousVoice();
      } else {
        await this._startContinuousVoice();
      }
    });
    this.$.vad.addEventListener("input", () => {
      this.state.vadThreshold = Number(this.$.vad.value) / 1000;
      this.$.vadValue.textContent = this.state.vadThreshold.toFixed(3);
    });
    this.$.endpause.addEventListener("input", () => {
      this.state.silenceMs = Number(this.$.endpause.value);
      this.$.endpauseValue.textContent = `${this.state.silenceMs} ms`;
    });
  }

  _setStatus(text) {
    if (this.$?.status) this.$.status.textContent = text;
  }

  _setMicState(text) {
    if (this.$?.micState) this.$.micState.textContent = text;
  }

  _appendMessage(role, text) {
    const div = document.createElement("div");
    div.className = `msg ${role}`;
    div.textContent = text;
    this.$.chat.appendChild(div);
    this.$.chat.scrollTop = this.$.chat.scrollHeight;
  }

  _appendSystem(text) {
    this._appendMessage("system", text);
  }

  _appendSystemDedup(key, text, cooldownMs = 5000) {
    const now = Date.now();
    const last = this._noticeDedup.get(key) || 0;
    if (now - last < cooldownMs) return;
    this._noticeDedup.set(key, now);
    this._appendSystem(text);
  }

  _syncPiperVoiceUiFromState() {
    const knownVoices = new Set([
      "",
      "de_DE-ramona-low",
      "de_DE-mls-medium",
      "de_DE-mls-high",
      "de_DE-thorsten-high",
    ]);
    const current = (this.state.piperVoice || "").trim();
    if (knownVoices.has(current)) {
      this.$.piperVoice.value = current;
      this.$.piperVoiceCustom.value = "";
      this.$.piperVoiceCustom.style.display = "none";
    } else {
      this.$.piperVoice.value = "custom";
      this.$.piperVoiceCustom.value = current;
      this.$.piperVoiceCustom.style.display = "";
    }
  }

  _refreshBrowserVoices() {
    if (!this.$?.browserVoice || !("speechSynthesis" in window)) return;
    const voices = window.speechSynthesis.getVoices() || [];
    const current = this.state.browserVoiceName || "";
    this.$.browserVoice.innerHTML = '<option value="">Standard (Browser)</option>';
    for (const v of voices) {
      const opt = document.createElement("option");
      opt.value = v.name;
      opt.textContent = `${v.name} (${v.lang})`;
      this.$.browserVoice.appendChild(opt);
    }
    const exists = current && voices.some((v) => v.name === current);
    this.$.browserVoice.value = exists ? current : "";
    if (!exists) this.state.browserVoiceName = "";
  }

  _extractAssistantSpeech(resp) {
    return (
      resp?.response?.speech?.plain?.speech ||
      resp?.response?.speech?.text ||
      resp?.response?.text ||
      ""
    );
  }

  async _sendText() {
    const text = this.$.input.value.trim();
    if (!text) return;
    this.$.input.value = "";
    await this._processPrompt(text, "text");
  }

  async _processPrompt(text, source) {
    this._appendMessage("user", source === "voice" ? `[voice] ${text}` : text);
    this._setStatus("LLM antwortet...");

    try {
      const req = {
        type: "conversation/process",
        agent_id: this.state.agentId,
        text,
        language: this.state.language,
      };
      if (this.state.conversationId) req.conversation_id = this.state.conversationId;
      const resp = await this._hass.callWS(req);
      if (resp?.conversation_id) this.state.conversationId = resp.conversation_id;
      const answer = (this._extractAssistantSpeech(resp) || "").trim();
      if (!answer) {
        this._appendSystem("Keine Antwort vom Agenten erhalten.");
        this._setStatus("Fertig");
        return;
      }
      this._appendMessage("assistant", answer);
      this._setStatus("Fertig");
      await this._speakOutputs(answer);
    } catch (err) {
      const raw = String(err?.message || err || "Unbekannter Fehler");
      const key = raw.includes("Error talking to API")
        ? "llm_api_talk"
        : raw.includes("Error handling API response")
        ? "llm_api_response"
        : `llm_${raw}`;
      this._appendSystemDedup(
        key,
        `Fehler beim LLM-Aufruf: ${raw}`,
        4000
      );
      this._setStatus("Fehler");
    }
  }

  async _speakOutputs(message) {
    if (!this.state.speakAnswer && !this.state.speakInBrowser) return;

    if (this.state.speakInBrowser) {
      await this._speakInBrowser(message);
    }
    if (this.state.speakAnswer) {
      await this._speakViaPiper(message);
    }
  }

  async _speakViaPiper(message) {
    const scriptEntity = this.state.ttsScriptEntityId || "script.tts_ansage";
    const [domain, service] = scriptEntity.split(".");
    if (domain !== "script" || !service) {
      this._appendSystem(`Ungueltige TTS-Script-Entity: ${scriptEntity}`);
      return;
    }
    try {
      const payload = {
        nachricht: message,
        ziel_player: this.state.targetPlayer,
      };
      payload.piper_tts_entity = this._getPiperTtsEntityForProfile(this.state.piperSpeedProfile);
      const voice = (this.state.piperVoice || "").trim();
      if (voice) {
        payload.piper_stimme = voice;
      }
      await this._hass.callService("script", service, payload);
    } catch (err) {
      this._appendSystem(`TTS-Fehler: ${err?.message || err}`);
    }
  }

  _getPiperTtsEntityForProfile(profile) {
    if (profile === "fast") return this.state.piperTtsEntityFast || "tts.piper";
    if (profile === "slow") return this.state.piperTtsEntitySlow || "tts.piper";
    return this.state.piperTtsEntityNormal || "tts.piper";
  }

  async _speakInBrowser(message) {
    if (!("speechSynthesis" in window) || typeof SpeechSynthesisUtterance === "undefined") {
      this._appendSystemDedup(
        "browser_tts_unsupported",
        "Browser-TTS wird in diesem Browser nicht unterstuetzt.",
        10000
      );
      return;
    }
    try {
      window.speechSynthesis.cancel();
      await new Promise((resolve, reject) => {
        const utt = new SpeechSynthesisUtterance(message);
        utt.lang = this.state.language === "de" ? "de-DE" : this.state.language;
        const selected = (this.state.browserVoiceName || "").trim();
        if (selected) {
          const voices = window.speechSynthesis.getVoices() || [];
          const chosen = voices.find((v) => v.name === selected);
          if (chosen) utt.voice = chosen;
        }
        utt.rate = this.state.browserRate || 1.15;
        utt.pitch = 1.0;
        utt.onend = () => resolve();
        utt.onerror = (ev) => reject(new Error(ev?.error || "browser-tts-error"));
        window.speechSynthesis.speak(utt);
      });
    } catch (err) {
      this._appendSystemDedup(
        "browser_tts_error",
        `Browser-TTS-Fehler: ${err?.message || err}`,
        6000
      );
    }
  }

  async _detectPreferredPipeline() {
    if (!this._hass) return;
    try {
      const res = await this._hass.callWS({ type: "assist_pipeline/pipeline/list" });
      this.state.pipelineId =
        res?.preferred_pipeline || res?.pipelines?.[0]?.id || null;
      const name =
        res?.pipelines?.find((p) => p.id === this.state.pipelineId)?.name ||
        "default";
      this.$.pipelineState.textContent = name;
    } catch (err) {
      this.$.pipelineState.textContent = "nicht verfuegbar";
      this._appendSystem(`Pipeline-Liste nicht lesbar: ${err?.message || err}`);
    }
  }

  async _ensureAudio() {
    if (this._audioContext && this._audioProcessor && this._audioStream) return;
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        noiseSuppression: true,
        echoCancellation: true,
      },
    });
    this._audioStream = stream;
    this._audioContext = new AudioContext({ sampleRate: 16000 });
    this._audioSource = this._audioContext.createMediaStreamSource(stream);
    this._audioProcessor = this._audioContext.createScriptProcessor(4096, 1, 1);
    this._audioSinkGain = this._audioContext.createGain();
    this._audioSinkGain.gain.value = 0;

    this._audioSource.connect(this._audioProcessor);
    this._audioProcessor.connect(this._audioSinkGain);
    this._audioSinkGain.connect(this._audioContext.destination);
    this._audioProcessor.onaudioprocess = (ev) => this._handleAudioChunk(ev);

    this.state.micReady = true;
    this.state.micOpen = true;
    this._setMicState("bereit");
  }

  async _startSingleVoiceRun() {
    if (this.state.listening || this._continuousLoop) return;
    try {
      await this._ensureAudio();
      await this._runVoiceUtterance();
    } catch (err) {
      this._appendSystem(`Mikrofon/Voice-Start fehlgeschlagen: ${err?.message || err}`);
      this._setMicState("fehler");
    }
  }

  async _startContinuousVoice() {
    if (this._continuousLoop) return;
    this._continuousEnabled = true;
    this.$.voiceContinuous.checked = true;
    this._continuousLoop = true;
    this.$.voiceToggle.textContent = "Stop kontinuierlich";

    try {
      await this._ensureAudio();
      this._appendSystem("Kontinuierlicher Voice-Modus gestartet.");
      this._continuousTick();
    } catch (err) {
      this._continuousLoop = false;
      this.$.voiceToggle.textContent = "Start kontinuierlich";
      this._appendSystem(`Kontinuierlich nicht gestartet: ${err?.message || err}`);
    }
  }

  _stopContinuousVoice() {
    this._continuousLoop = false;
    this.$.voiceToggle.textContent = "Start kontinuierlich";
    this._setMicState("bereit");
    this._appendSystem("Kontinuierlicher Voice-Modus gestoppt.");
  }

  async _continuousTick() {
    while (this._continuousLoop) {
      if (!this.state.listening) {
        await this._runVoiceUtterance();
      }
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
  }

  async _runVoiceUtterance() {
    this.state.listening = true;
    this._setMicState("hoert zu");
    this._setStatus("STT laeuft...");
    this._pipelineResultText = "";
    this._pipelineError = null;
    this._audioQueue = [];

    this._currentUtterance = {
      startedAt: Date.now(),
      heardSpeech: false,
      lastSpeechAt: 0,
      ended: false,
    };

    const donePromise = new Promise((resolve) => {
      this._pipelineDoneResolver = resolve;
    });

    await this._startAssistPipelineRun();

    const timeoutTimer = setTimeout(() => {
      this._finishAudioStream();
    }, this.state.maxUtteranceMs);

    await donePromise;
    clearTimeout(timeoutTimer);

    this.state.listening = false;
    this._setMicState(this._continuousLoop ? "wartet auf sprachaktivitaet" : "bereit");

    if (this._pipelineError) {
      const isNoText = this._pipelineError.includes("stt-no-text-recognized");
      if (isNoText) {
        if (!this._continuousLoop) {
          this._appendSystem("Kein Text erkannt.");
        }
        this._setStatus("Warte auf Sprache");
      } else {
        this._appendSystemDedup(
          `voice_${this._pipelineError}`,
          `Voice-Fehler: ${this._pipelineError}`,
          5000
        );
        this._setStatus("Fehler");
      }
      return;
    }

    const transcript = (this._pipelineResultText || "").trim();
    if (!transcript) {
      this._appendSystem("Kein Text erkannt.");
      this._setStatus("Fertig");
      return;
    }

    this._setStatus("STT fertig, sende an LLM...");
    await this._processPrompt(transcript, "voice");
  }

  async _startAssistPipelineRun() {
    const conn = this._hass?.connection;
    if (!conn || typeof conn.subscribeMessage !== "function") {
      throw new Error("HA-Verbindung unterstuetzt kein Streaming.");
    }

    const runRequest = {
      type: "assist_pipeline/run",
      start_stage: "stt",
      end_stage: "stt",
      input: {
        sample_rate: 16000,
      },
    };
    if (this.state.pipelineId) runRequest.pipeline = this.state.pipelineId;

    this._pipelineRunActive = true;
    this._pipelineHandlerId = null;

    this._pipelineUnsubscribe = await conn.subscribeMessage(
      (msg) => this._handlePipelineMessage(msg),
      runRequest,
      { resubscribe: false }
    );
  }

  _handlePipelineMessage(msg) {
    const ev = msg?.event || msg;
    const evType = ev?.type;
    const data = ev?.data || {};
    if (!evType) return;

    if (evType === "run-start") {
      this._pipelineHandlerId = data?.runner_data?.stt_binary_handler_id ?? null;
      this._flushAudioQueue();
      return;
    }

    if (evType === "stt-end") {
      this._pipelineResultText = data?.stt_output?.text || "";
      return;
    }

    if (evType === "error") {
      this._pipelineError = `${data?.code || "error"}: ${data?.message || "unbekannt"}`;
      this._closePipelineRun();
      return;
    }

    if (evType === "run-end") {
      this._closePipelineRun();
    }
  }

  _closePipelineRun() {
    this._pipelineRunActive = false;
    if (this._pipelineUnsubscribe) {
      try {
        this._pipelineUnsubscribe();
      } catch (_err) {
        // ignore
      }
      this._pipelineUnsubscribe = null;
    }
    if (this._pipelineDoneResolver) {
      const resolve = this._pipelineDoneResolver;
      this._pipelineDoneResolver = null;
      resolve();
    }
  }

  _handleAudioChunk(ev) {
    const ut = this._currentUtterance;
    if (!ut || ut.ended || !this.state.listening) return;

    const input = ev.inputBuffer.getChannelData(0);
    const pcm16 = new Int16Array(input.length);
    let sum = 0;
    for (let i = 0; i < input.length; i += 1) {
      const s = Math.max(-1, Math.min(1, input[i]));
      pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      sum += s * s;
    }
    const rms = Math.sqrt(sum / input.length);
    const now = Date.now();

    if (rms >= this.state.vadThreshold) {
      ut.heardSpeech = true;
      ut.lastSpeechAt = now;
    }

    this._sendAudioPcmChunk(pcm16);

    if (!ut.heardSpeech && now - ut.startedAt > this.state.noSpeechTimeoutMs) {
      this._finishAudioStream();
      return;
    }

    if (ut.heardSpeech && now - ut.lastSpeechAt > this.state.silenceMs) {
      this._finishAudioStream();
    }
  }

  _sendAudioPcmChunk(pcm16) {
    if (!this._pipelineRunActive) return;
    if (this._pipelineHandlerId === null || this._pipelineHandlerId === undefined) {
      this._audioQueue.push(pcm16);
      if (this._audioQueue.length > 24) this._audioQueue.shift();
      return;
    }
    this._sendChunkWithHandler(pcm16);
  }

  _flushAudioQueue() {
    if (this._pipelineHandlerId === null || this._pipelineHandlerId === undefined) return;
    for (const chunk of this._audioQueue) {
      this._sendChunkWithHandler(chunk);
    }
    this._audioQueue = [];
  }

  _sendChunkWithHandler(pcm16) {
    const socket = this._hass?.connection?.socket;
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    const bytes = new Uint8Array(1 + pcm16.byteLength);
    bytes[0] = this._pipelineHandlerId & 0xff;
    bytes.set(new Uint8Array(pcm16.buffer), 1);
    socket.send(bytes);
  }

  _finishAudioStream() {
    const ut = this._currentUtterance;
    if (!ut || ut.ended) return;
    ut.ended = true;

    if (this._pipelineHandlerId !== null && this._pipelineHandlerId !== undefined) {
      const socket = this._hass?.connection?.socket;
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(new Uint8Array([this._pipelineHandlerId & 0xff]));
      }
    } else {
      // Kein Handler bekommen -> Pipeline trotzdem schliessen, um Hanger zu vermeiden.
      this._closePipelineRun();
    }
  }
}

if (!customElements.get("local-chat-panel")) {
  customElements.define("local-chat-panel", LocalChatPanel);
}
