(function () {
  const DB_NAME = "kore-agro-field";
  const DB_VERSION = 1;
  const EVENT_STORE = "events";
  const META_STORE = "meta";
  const config = window.KORE_FIELD_CONFIG;

  let db;
  let masters = { farms: [], groups: [], animals: [], inputs: [], today_actions: [] };

  function openDb() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);
      request.onupgradeneeded = () => {
        const database = request.result;
        if (!database.objectStoreNames.contains(EVENT_STORE)) {
          const events = database.createObjectStore(EVENT_STORE, { keyPath: "event_id" });
          events.createIndex("status", "status", { unique: false });
          events.createIndex("client_sequence", "client_sequence", { unique: false });
        }
        if (!database.objectStoreNames.contains(META_STORE)) {
          database.createObjectStore(META_STORE, { keyPath: "key" });
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  function tx(storeName, mode) {
    return db.transaction(storeName, mode).objectStore(storeName);
  }

  function requestToPromise(request) {
    return new Promise((resolve, reject) => {
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  function put(storeName, value) {
    return requestToPromise(tx(storeName, "readwrite").put(value));
  }

  function del(storeName, key) {
    return requestToPromise(tx(storeName, "readwrite").delete(key));
  }

  function get(storeName, key) {
    return requestToPromise(tx(storeName, "readonly").get(key));
  }

  function getAll(storeName) {
    return requestToPromise(tx(storeName, "readonly").getAll());
  }

  function deviceId() {
    let value = localStorage.getItem("kore_device_id");
    if (!value) {
      value = crypto.randomUUID();
      localStorage.setItem("kore_device_id", value);
    }
    return value;
  }

  function nextSequence() {
    const current = Number(localStorage.getItem("kore_client_sequence") || "0") + 1;
    localStorage.setItem("kore_client_sequence", String(current));
    return current;
  }

  async function queueEvent(eventType, payload) {
    const event = {
      event_id: crypto.randomUUID(),
      tenant_id: null,
      device_id: deviceId(),
      actor_id: null,
      occurred_at: new Date().toISOString(),
      event_type: eventType,
      payload,
      client_sequence: nextSequence(),
      schema_version: 1,
      status: "pending",
      detail: "",
      resolution: "",
      retryable: false,
      attempts: 0
    };
    await put(EVENT_STORE, event);
    await renderQueue();
    resetLastSync("Guardado offline");
    if (navigator.onLine) {
      syncQueue();
    }
  }

  async function renderQueue() {
    const events = await getAll(EVENT_STORE);
    const pending = events.filter((event) => event.status !== "acked" && event.status !== "discarded");
    document.getElementById("queueCount").textContent = String(pending.length);
    const list = document.getElementById("queueList");
    list.innerHTML = "";
    pending
      .sort((a, b) => a.client_sequence - b.client_sequence)
      .slice(0, 20)
      .forEach((event) => {
        const item = document.createElement("li");
        const label = document.createElement("span");
        label.textContent = `${event.client_sequence} - ${event.event_type} - ${event.status}`;
        item.appendChild(label);
        if (event.detail) {
          const detail = document.createElement("small");
          detail.textContent = `${event.detail} ${event.resolution || ""}`.trim();
          item.appendChild(detail);
        }
        if (event.status !== "pending") {
          const retry = document.createElement("button");
          retry.type = "button";
          retry.textContent = "Reintentar";
          retry.disabled = event.status === "conflict" || event.retryable === false;
          retry.addEventListener("click", () => retryEvent(event.event_id));
          item.appendChild(retry);

          const discard = document.createElement("button");
          discard.type = "button";
          discard.textContent = "Descartar";
          discard.addEventListener("click", () => discardEvent(event.event_id));
          item.appendChild(discard);
        }
        list.appendChild(item);
      });
  }

  async function syncQueue() {
    if (!navigator.onLine) {
      updateNetworkState();
      return;
    }
    const events = (await getAll(EVENT_STORE))
      .filter((event) => event.status === "pending")
      .sort((a, b) => a.client_sequence - b.client_sequence);

    if (!events.length) {
      resetLastSync("Sin pendientes");
      return;
    }

    let response;
    try {
      response = await fetch(config.syncUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Kore-Device-ID": deviceId() },
        body: JSON.stringify({ events })
      });
    } catch (error) {
      await markTransportFailure(events, error.message || "No se pudo conectar al servidor.");
      resetLastSync("Sin conexión con el servidor");
      await renderQueue();
      return;
    }

    if (!response.ok) {
      await markTransportFailure(events, `Error HTTP ${response.status}`);
      resetLastSync(`Error HTTP ${response.status}`);
      await renderQueue();
      return;
    }

    const data = await response.json();
    for (const result of data.results || []) {
      if (result.status === "acked") {
        await del(EVENT_STORE, result.event_id);
      } else {
        const event = await get(EVENT_STORE, result.event_id);
        if (event) {
          event.status = result.status || "failed";
          event.detail = result.detail || "";
          event.resolution = result.resolution || "";
          event.retryable = Boolean(result.retryable);
          event.attempts = Number(event.attempts || 0) + 1;
          await put(EVENT_STORE, event);
        }
      }
    }
    resetLastSync(new Date().toLocaleTimeString());
    await renderQueue();
  }

  async function markTransportFailure(events, detail) {
    for (const queued of events) {
      const event = await get(EVENT_STORE, queued.event_id);
      if (event) {
        event.status = "pending";
        event.detail = detail;
        event.resolution = "Reintenta cuando se restablezca la conexión.";
        event.retryable = true;
        event.attempts = Number(event.attempts || 0) + 1;
        await put(EVENT_STORE, event);
      }
    }
  }

  async function retryEvent(eventId) {
    const event = await get(EVENT_STORE, eventId);
    if (!event || event.status === "conflict") return;
    event.status = "pending";
    event.detail = "";
    event.resolution = "";
    await put(EVENT_STORE, event);
    await renderQueue();
    syncQueue();
  }

  async function discardEvent(eventId) {
    const event = await get(EVENT_STORE, eventId);
    if (!event || !window.confirm("¿Descartar este evento local? No se enviará al servidor.")) return;
    event.status = "discarded";
    await put(EVENT_STORE, event);
    await renderQueue();
  }

  async function retryPendingEvents() {
    const events = await getAll(EVENT_STORE);
    for (const event of events) {
      if (event.retryable && event.status !== "conflict") {
        event.status = "pending";
        event.detail = "";
        event.resolution = "";
        await put(EVENT_STORE, event);
      }
    }
    await renderQueue();
    syncQueue();
  }

  async function loadBootstrap() {
    try {
      const response = await fetch(config.bootstrapUrl, {
        headers: { "X-Kore-Device-ID": deviceId() }
      });
      if (!response.ok) {
        throw new Error(`Bootstrap HTTP ${response.status}`);
      }
      masters = await response.json();
      await put(META_STORE, { key: "bootstrap", value: masters });
    } catch (error) {
      const cached = await get(META_STORE, "bootstrap");
      if (cached) {
        masters = cached.value;
      }
    }
    populateSelects();
    renderTodayActions();
  }

  function populateSelects() {
    document.querySelectorAll("select[data-source]").forEach((select) => {
      if (select.dataset.source === "farms") populateSelect(select);
    });
    restoreSelectedFarms();
    document.querySelectorAll("select[data-source]").forEach((select) => {
      if (select.dataset.source !== "farms") populateSelect(select);
    });
  }

  function populateSelect(select) {
    const source = select.dataset.source;
    const previousValue = select.value;
    const required = select.hasAttribute("required");
    const form = select.closest("form");
    const farmId = form && form.elements.farm_id ? form.elements.farm_id.value : "";
    let items = masters[source] || [];
    if ((source === "animals" || source === "groups") && farmId) {
      items = items.filter((item) => item.farm_id === farmId);
    }
    select.innerHTML = required ? "" : '<option value="">Sin asignar</option>';
    items.forEach((item) => {
      const option = document.createElement("option");
      option.value = item.id;
      option.textContent = labelFor(source, item);
      select.appendChild(option);
    });
    if (items.some((item) => item.id === previousValue)) select.value = previousValue;
  }

  function restoreSelectedFarms() {
    const rememberedFarm = localStorage.getItem("kore_selected_farm");
    const defaultFarm = masters.farms.some((farm) => farm.id === rememberedFarm)
      ? rememberedFarm
      : (masters.farms[0] || {}).id;
    document.querySelectorAll("select[data-source='farms']").forEach((select) => {
      select.value = defaultFarm || "";
    });
  }

  function refreshFormSources(form) {
    form.querySelectorAll("select[data-source='animals'], select[data-source='groups']").forEach(populateSelect);
  }

  function renderTodayActions() {
    const container = document.getElementById("todayActions");
    if (!container) return;
    container.innerHTML = "";
    const actions = masters.today_actions || [];
    if (!actions.length) {
      container.innerHTML = '<p class="emptyState">Todo al día. No hay alertas urgentes para esta jornada.</p>';
      return;
    }
    actions.forEach((action) => {
      const card = document.createElement("button");
      card.type = "button";
      card.className = `attentionCard ${action.priority || "normal"}`;
      const symbol = document.createElement("span");
      symbol.className = "attentionSymbol";
      symbol.textContent = symbolForAction(action.kind);
      const copy = document.createElement("span");
      const title = document.createElement("strong");
      title.textContent = action.title;
      const detail = document.createElement("small");
      detail.textContent = action.detail;
      copy.append(title, detail);
      const arrow = document.createElement("span");
      arrow.className = "attentionArrow";
      arrow.textContent = ">";
      card.append(symbol, copy, arrow);
      card.addEventListener("click", () => openPanel(action.panel, action.animal_id));
      container.appendChild(card);
    });
  }

  function symbolForAction(kind) {
    return { withdrawal: "!", dry_off: "◐", pregnancy: "?", treatment: "+" }[kind] || "•";
  }

  function labelFor(source, item) {
    if (source === "farms") {
      return `${item.code} - ${item.name}`;
    }
    if (source === "groups") {
      return item.name;
    }
    if (source === "animals") {
      const statuses = {
        calf: "ternera",
        heifer: "vientre",
        lactating: "en producción",
        dry: "seca",
        pregnant: "preñada"
      };
      return `${item.tag}${item.name ? ` · ${item.name}` : ""} - ${statuses[item.status] || item.status}`;
    }
    if (source === "inputs") {
      return `${item.name} - ${item.unit}`;
    }
    return item.name || item.id;
  }

  function formData(form) {
    return Object.fromEntries(new FormData(form).entries());
  }

  function cleanPayload(payload) {
    return Object.fromEntries(
      Object.entries(payload).filter(([, value]) => value !== "" && value !== null && value !== undefined)
    );
  }

  function bindForms() {
    document.getElementById("milkForm").addEventListener("submit", (event) => {
      event.preventDefault();
      const data = formData(event.currentTarget);
      const record =
        data.target_type === "group"
          ? { group_id: data.group_id, liters: data.liters }
          : { animal_id: data.animal_id, liters: data.liters };
      queueEvent(
        "milk.milking_recorded",
        cleanPayload({
          farm_id: data.farm_id,
          milking_date: todayIso(),
          shift: data.shift,
          records: [record]
        })
      );
      resetFieldForm(event.currentTarget);
    });

    document.getElementById("reproForm").addEventListener("submit", (event) => {
      event.preventDefault();
      const data = formData(event.currentTarget);
      queueEvent(
        data.event_kind,
        cleanPayload({
          farm_id: data.farm_id,
          animal_id: data.animal_id,
          occurred_on: data.occurred_on,
          service_type: data.service_type,
          sire_identifier: data.sire_identifier,
          calf_id: data.calf_tag ? crypto.randomUUID() : "",
          calf_tag: data.calf_tag,
          calf_sex: data.calf_sex,
          birth_date: data.event_kind === "reproduction.calving_recorded" ? data.occurred_on : ""
        })
      );
      resetFieldForm(event.currentTarget);
    });

    document.getElementById("healthForm").addEventListener("submit", (event) => {
      event.preventDefault();
      const data = formData(event.currentTarget);
      queueEvent(
        "health.treatment_recorded",
        cleanPayload({
          farm_id: data.farm_id,
          animal_id: data.animal_id,
          diagnosis: data.diagnosis,
          input_id: data.input_id,
          quantity: data.quantity,
          dosage: data.dosage,
          milk_withdrawal_hours: data.milk_withdrawal_hours
        })
      );
      resetFieldForm(event.currentTarget);
    });

    document.getElementById("inventoryForm").addEventListener("submit", (event) => {
      event.preventDefault();
      const data = formData(event.currentTarget);
      queueEvent(
        "inventory.input_consumed",
        cleanPayload({
          farm_id: data.farm_id,
          input_id: data.input_id,
          quantity: data.quantity,
          animal_id: data.animal_id,
          group_id: data.group_id,
          notes: data.notes
        })
      );
      resetFieldForm(event.currentTarget);
    });

    document.querySelector("select[name='target_type']").addEventListener("change", (event) => {
      const isGroup = event.target.value === "group";
      document.querySelector(".targetAnimal").classList.toggle("hidden", isGroup);
      document.querySelector(".targetGroup").classList.toggle("hidden", !isGroup);
    });

    document.querySelectorAll("select[data-source='farms']").forEach((select) => {
      select.addEventListener("change", (event) => {
        localStorage.setItem("kore_selected_farm", event.target.value);
        document.querySelectorAll("select[data-source='farms']").forEach((farmSelect) => {
          farmSelect.value = event.target.value;
          refreshFormSources(farmSelect.closest("form"));
        });
      });
    });
  }

  function bindTabs() {
    document.querySelectorAll(".tab").forEach((tab) => {
      tab.addEventListener("click", () => openPanel(tab.dataset.panel));
    });
  }

  function bindQuickActions() {
    document.querySelectorAll("[data-open-panel]").forEach((button) => {
      button.addEventListener("click", () => openPanel(button.dataset.openPanel, null, button.dataset.focus));
    });
  }

  function openPanel(panelId, animalId = null, focusSelector = null) {
    document.querySelectorAll(".tab").forEach((item) => {
      item.classList.toggle("active", item.dataset.panel === panelId);
    });
    document.querySelectorAll(".panel").forEach((panel) => {
      panel.classList.toggle("active", panel.id === panelId);
    });
    const panel = document.getElementById(panelId);
    if (!panel) return;
    if (animalId) {
      const animalSelect = panel.querySelector("select[name='animal_id']");
      if (animalSelect && [...animalSelect.options].some((option) => option.value === animalId)) {
        animalSelect.value = animalId;
      }
    }
    panel.scrollIntoView({ behavior: "smooth", block: "start" });
    const target = focusSelector ? document.querySelector(focusSelector) : null;
    if (target) setTimeout(() => target.focus(), 350);
  }

  function resetFieldForm(form) {
    form.reset();
    setTodayDefaults();
    restoreSelectedFarms();
    refreshFormSources(form);
  }

  function setTodayDefaults() {
    document.querySelectorAll("input[type='date']").forEach((input) => {
      input.value = todayIso();
    });
  }

  function setTodayLabel() {
    const label = document.getElementById("todayLabel");
    if (!label) return;
    label.textContent = new Intl.DateTimeFormat("es-EC", {
      weekday: "long",
      day: "numeric",
      month: "long"
    }).format(new Date());
  }

  function todayIso() {
    return new Date().toISOString().slice(0, 10);
  }

  function updateNetworkState() {
    document.getElementById("networkState").textContent = navigator.onLine ? "Online" : "Offline";
  }

  function resetLastSync(value) {
    document.getElementById("lastSync").textContent = value;
  }

  async function registerServiceWorker() {
    if ("serviceWorker" in navigator) {
      await navigator.serviceWorker.register(config.serviceWorkerUrl);
    }
  }

  async function init() {
    db = await openDb();
    setTodayLabel();
    setTodayDefaults();
    bindTabs();
    bindQuickActions();
    bindForms();
    updateNetworkState();
    await registerServiceWorker();
    await loadBootstrap();
    await renderQueue();
    document.getElementById("syncNow").addEventListener("click", syncQueue);
    document.getElementById("retryQueue").addEventListener("click", retryPendingEvents);
    window.addEventListener("online", () => {
      updateNetworkState();
      syncQueue();
    });
    window.addEventListener("offline", updateNetworkState);
    if (navigator.onLine) {
      syncQueue();
    }
  }

  init().catch((error) => {
    resetLastSync(error.message || "Error");
  });
})();

