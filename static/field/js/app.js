(function () {
  const DB_NAME = "kore-agro-field";
  const DB_VERSION = 1;
  const EVENT_STORE = "events";
  const META_STORE = "meta";
  const config = window.KORE_FIELD_CONFIG;

  let db;
  let masters = {
    farms: [], groups: [], animals: [], inputs: [], paddocks: [], active_grazing: [],
    workers: [], work_tasks: [], today_actions: [], capabilities: []
  };
  let selectedFarmId = "";
  let syncInFlight = false;
  let syncAgain = false;

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
    resetLastSync(navigator.onLine ? "Pendiente de envío" : "Guardado en dispositivo");
    if (navigator.onLine) {
      synchronize();
    }
  }

  async function renderQueue() {
    const events = await getAll(EVENT_STORE);
    const pending = events.filter((event) => event.status !== "acked" && event.status !== "discarded");
    document.getElementById("queueCount").textContent = `${pending.length} ${pending.length === 1 ? "evento" : "eventos"}`;
    const list = document.getElementById("queueList");
    list.innerHTML = "";
    if (!pending.length) {
      list.innerHTML = '<li class="queueEmpty">No hay registros pendientes.</li>';
      return;
    }
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
          const actions = document.createElement("div");
          actions.className = "queueActions";
          const retry = document.createElement("button");
          retry.type = "button";
          retry.textContent = "Reintentar";
          retry.disabled = event.status === "conflict" || event.retryable === false;
          retry.addEventListener("click", () => retryEvent(event.event_id));
          actions.appendChild(retry);

          const discard = document.createElement("button");
          discard.type = "button";
          discard.textContent = "Descartar";
          discard.className = "queueDiscard";
          discard.addEventListener("click", () => discardEvent(event.event_id));
          actions.appendChild(discard);
          item.appendChild(actions);
        }
        list.appendChild(item);
      });
  }

  async function syncQueue() {
    if (!navigator.onLine) {
      setNetworkState("offline");
      return false;
    }
    if (syncInFlight) {
      syncAgain = true;
      return;
    }
    syncInFlight = true;
    setNetworkState("syncing");

    let events = [];
    try {
      events = (await getAll(EVENT_STORE))
        .filter((event) => event.status === "pending")
        .sort((a, b) => a.client_sequence - b.client_sequence);

      if (!events.length) {
        setNetworkState("online");
        return true;
      }

      const response = await fetch(config.syncUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Kore-Device-ID": deviceId() },
        body: JSON.stringify({ events })
      });

      if (!response.ok) {
        await markTransportFailure(events, `Error HTTP ${response.status}`);
        resetLastSync(`Error HTTP ${response.status}`);
        setNetworkState("online");
        await renderQueue();
        return false;
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
      setNetworkState("online");
      resetLastSync(`Sincronizado ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`);
      await renderQueue();
      return true;
    } catch (error) {
      await markTransportFailure(events, error.message || "No se pudo conectar al servidor.");
      setNetworkState("offline");
      resetLastSync("Guardado en dispositivo");
      await renderQueue();
      return false;
    } finally {
      syncInFlight = false;
      if (syncAgain) {
        syncAgain = false;
        synchronize();
      }
    }
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
    synchronize();
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
    synchronize();
  }

  function applyBootstrap(data) {
    masters = {
      farms: [],
      groups: [],
      animals: [],
      inputs: [],
      paddocks: [],
      active_grazing: [],
      workers: [],
      work_tasks: [],
      today_actions: [],
      capabilities: [],
      ...data
    };
    applyCapabilityVisibility();
    configureFarmContext();
    populateSelects();
    renderTodayActions();
  }

  function applyCapabilityVisibility() {
    const enabled = new Set(masters.capabilities || []);
    document.querySelectorAll("[data-capability]").forEach((element) => {
      const available = enabled.has(element.dataset.capability);
      element.classList.toggle("capabilityHidden", !available);
    });

    const panels = [...document.querySelectorAll(".panel:not(.capabilityHidden)")];
    const activePanel = document.querySelector(".panel.active:not(.capabilityHidden)");
    if (!activePanel && panels.length) openPanel(panels[0].id);
    document.getElementById("noModules").classList.toggle("hidden", panels.length > 0);
    document.getElementById("attentionPanel").classList.toggle(
      "capabilityHidden",
      !enabled.has("reproduction") && !enabled.has("health")
    );
  }

  async function loadCachedBootstrap() {
    const cached = await get(META_STORE, "bootstrap");
    if (!cached) return false;
    applyBootstrap(cached.value);
    resetLastSync(navigator.onLine ? "Actualizando..." : "Datos guardados");
    return true;
  }

  async function refreshBootstrap() {
    try {
      const response = await fetch(config.bootstrapUrl, {
        cache: "no-store",
        headers: { "X-Kore-Device-ID": deviceId() }
      });
      if (!response.ok) {
        throw new Error(`No se pudo actualizar (${response.status}).`);
      }
      const freshMasters = await response.json();
      await put(META_STORE, { key: "bootstrap", value: freshMasters });
      applyBootstrap(freshMasters);
      setNetworkState("online");
      resetLastSync(`Actualizado ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`);
      return true;
    } catch (error) {
      setNetworkState(navigator.onLine ? "online" : "offline");
      resetLastSync(navigator.onLine ? error.message : "Datos guardados");
      if (!(masters.farms || []).length) {
        configureFarmContext();
      }
      return false;
    }
  }

  async function synchronize() {
    const synced = await syncQueue();
    if (synced) await refreshBootstrap();
    return synced;
  }

  function farmStorageKey() {
    return `kore_selected_farm_${masters.tenant || "default"}`;
  }

  function configureFarmContext() {
    const farms = masters.farms || [];
    const rememberedFarm = localStorage.getItem(farmStorageKey());
    const preferredFarm = rememberedFarm || masters.default_farm_id;
    const selectedFarm = farms.find((farm) => farm.id === preferredFarm) || farms[0];
    selectedFarmId = selectedFarm ? selectedFarm.id : "";

    const context = document.getElementById("farmContext");
    const name = document.getElementById("farmName");
    const switcher = document.getElementById("farmSwitcher");
    const select = document.getElementById("farmSelect");
    context.classList.toggle("noFarm", !selectedFarm);
    name.textContent = selectedFarm ? selectedFarm.name : "Sin hacienda asignada";

    select.innerHTML = "";
    farms.forEach((farm) => {
      const option = document.createElement("option");
      option.value = farm.id;
      option.textContent = `${farm.code} - ${farm.name}`;
      select.appendChild(option);
    });
    select.value = selectedFarmId;
    switcher.classList.toggle("hidden", !masters.can_switch_farm || farms.length < 2);
    setCaptureEnabled(Boolean(selectedFarm));
    if (selectedFarm) localStorage.setItem(farmStorageKey(), selectedFarm.id);
  }

  function setCaptureEnabled(enabled) {
    document.querySelectorAll(".quickAction, .tab, .form input, .form select, .form button").forEach((element) => {
      element.disabled = !enabled;
    });
  }

  function populateSelects() {
    document.querySelectorAll("select[data-source]").forEach(populateSelect);
  }

  function populateSelect(select) {
    const source = select.dataset.source;
    const previousValue = select.value;
    const required = select.hasAttribute("required");
    let items = masters[source] || [];
    if (
      ["animals", "groups", "paddocks", "active_grazing", "workers", "work_tasks"].includes(source)
      && selectedFarmId
    ) {
      items = items.filter((item) => item.farm_id === selectedFarmId);
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

  function refreshFormSources(form) {
    form.querySelectorAll("select[data-source='animals'], select[data-source='groups']").forEach(populateSelect);
  }

  function renderTodayActions() {
    const container = document.getElementById("todayActions");
    if (!container) return;
    container.innerHTML = "";
    const actions = (masters.today_actions || []).filter(
      (action) => !action.farm_id || action.farm_id === selectedFarmId
    );
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
    if (source === "paddocks") {
      return `${item.code} - ${item.name}`;
    }
    if (source === "active_grazing") {
      return `${item.paddock__name} - ${item.group__name}`;
    }
    if (source === "workers") {
      return `${item.code} - ${item.full_name}`;
    }
    if (source === "work_tasks") {
      const assigned = item.assigned_to__full_name ? ` - ${item.assigned_to__full_name}` : "";
      return `${item.title}${assigned}`;
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
          farm_id: selectedFarmId,
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
          farm_id: selectedFarmId,
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
          farm_id: selectedFarmId,
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
          farm_id: selectedFarmId,
          input_id: data.input_id,
          quantity: data.quantity,
          animal_id: data.animal_id,
          group_id: data.group_id,
          notes: data.notes
        })
      );
      resetFieldForm(event.currentTarget);
    });

    document.getElementById("weightForm").addEventListener("submit", (event) => {
      event.preventDefault();
      const data = formData(event.currentTarget);
      queueEvent(
        "growth.weight_recorded",
        cleanPayload({
          farm_id: selectedFarmId,
          animal_id: data.animal_id,
          weight_kg: data.weight_kg,
          body_condition_score: data.body_condition_score,
          weighed_on: data.weighed_on,
          scale_identifier: data.scale_identifier,
          notes: data.notes
        })
      );
      resetFieldForm(event.currentTarget);
    });

    document.getElementById("grazingForm").addEventListener("submit", (event) => {
      event.preventDefault();
      const data = formData(event.currentTarget);
      const starting = data.action_kind === "start";
      queueEvent(
        starting ? "grazing.rotation_started" : "grazing.rotation_finished",
        cleanPayload({
          farm_id: selectedFarmId,
          paddock_id: starting ? data.paddock_id : "",
          group_id: starting ? data.group_id : "",
          grazing_period_id: starting ? "" : data.grazing_period_id,
          started_on: starting ? data.occurred_on : "",
          ended_on: starting ? "" : data.occurred_on,
          planned_end_on: starting ? data.planned_end_on : "",
          head_count: starting ? data.head_count : "",
          entry_biomass_kg_ha: starting ? data.biomass_kg_ha : "",
          exit_biomass_kg_ha: starting ? "" : data.biomass_kg_ha,
          notes: data.notes
        })
      );
      resetFieldForm(event.currentTarget);
    });

    document.getElementById("taskForm").addEventListener("submit", (event) => {
      event.preventDefault();
      const data = formData(event.currentTarget);
      const completing = data.action_kind === "complete";
      queueEvent(
        completing ? "workforce.task_completed" : "workforce.task_started",
        cleanPayload({
          farm_id: selectedFarmId,
          task_id: data.task_id,
          worker_id: data.worker_id,
          hours: completing ? data.hours : "",
          notes: data.notes
        })
      );
      resetFieldForm(event.currentTarget);
    });

    document.getElementById("receiptForm").addEventListener("submit", (event) => {
      event.preventDefault();
      const data = formData(event.currentTarget);
      queueEvent(
        "inventory.input_received",
        cleanPayload({
          farm_id: selectedFarmId,
          input_id: data.input_id,
          quantity: data.quantity,
          unit_cost: data.unit_cost,
          lot_code: data.lot_code,
          expires_on: data.expires_on,
          notes: data.notes
        })
      );
      resetFieldForm(event.currentTarget);
    });

    document.getElementById("adjustmentForm").addEventListener("submit", (event) => {
      event.preventDefault();
      const data = formData(event.currentTarget);
      const quantityField = event.currentTarget.elements.quantity_delta;
      if (Number(data.quantity_delta) === 0) {
        quantityField.setCustomValidity("La diferencia no puede ser cero.");
        quantityField.reportValidity();
        return;
      }
      queueEvent(
        "inventory.stock_adjusted",
        cleanPayload({
          farm_id: selectedFarmId,
          input_id: data.input_id,
          quantity_delta: data.quantity_delta,
          reason: data.reason,
          animal_id: data.animal_id,
          group_id: data.group_id
        })
      );
      resetFieldForm(event.currentTarget);
    });

    document.getElementById("expenseForm").addEventListener("submit", (event) => {
      event.preventDefault();
      const data = formData(event.currentTarget);
      queueEvent(
        "finance.expense_recorded",
        cleanPayload({
          farm_id: selectedFarmId,
          amount: data.amount,
          cost_type: data.cost_type,
          cost_date: data.cost_date,
          animal_id: data.animal_id,
          group_id: data.group_id,
          notes: data.notes
        })
      );
      resetFieldForm(event.currentTarget);
    });

    document.getElementById("saleForm").addEventListener("submit", (event) => {
      event.preventDefault();
      const data = formData(event.currentTarget);
      queueEvent(
        "herd.animal_sold",
        cleanPayload({
          farm_id: selectedFarmId,
          animal_id: data.animal_id,
          amount: data.amount,
          sale_date: data.sale_date,
          notes: data.notes
        })
      );
      resetFieldForm(event.currentTarget);
    });

    document
      .querySelector("#adjustmentForm [name='quantity_delta']")
      .addEventListener("input", (event) => event.target.setCustomValidity(""));

    document.querySelector("select[name='target_type']").addEventListener("change", (event) => {
      const isGroup = event.target.value === "group";
      document.querySelector(".targetAnimal").classList.toggle("hidden", isGroup);
      document.querySelector(".targetGroup").classList.toggle("hidden", !isGroup);
    });

    document
      .querySelector("#grazingForm [name='action_kind']")
      .addEventListener("change", configureGrazingForm);
    configureGrazingForm();
    document
      .querySelector("#taskForm [name='action_kind']")
      .addEventListener("change", configureTaskForm);
    configureTaskForm();

  }

  function configureGrazingForm() {
    const form = document.getElementById("grazingForm");
    const mode = form.elements.action_kind.value;
    form.querySelectorAll("[data-grazing-mode]").forEach((row) => {
      const active = row.dataset.grazingMode === mode;
      row.classList.toggle("hidden", !active);
      row.querySelectorAll("input, select").forEach((field) => {
        field.disabled = !active;
        if (field.name === "grazing_period_id") field.required = active;
      });
    });
  }

  function configureTaskForm() {
    const form = document.getElementById("taskForm");
    const completing = form.elements.action_kind.value === "complete";
    form.querySelectorAll("[data-task-mode='complete']").forEach((row) => {
      row.classList.toggle("hidden", !completing);
      const hours = row.querySelector("input[name='hours']");
      hours.disabled = !completing;
      hours.required = completing;
    });
  }

  function bindFarmContext() {
    document.getElementById("farmSelect").addEventListener("change", (event) => {
      selectedFarmId = event.target.value;
      const farm = (masters.farms || []).find((item) => item.id === selectedFarmId);
      document.getElementById("farmName").textContent = farm ? farm.name : "Sin hacienda asignada";
      localStorage.setItem(farmStorageKey(), selectedFarmId);
      document.querySelectorAll(".form").forEach((form) => resetFieldForm(form));
      populateSelects();
      renderTodayActions();
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
    document.querySelectorAll(".quickAction").forEach((item) => {
      const isActive = item.dataset.openPanel === panelId;
      item.classList.toggle("active", isActive);
      item.setAttribute("aria-pressed", String(isActive));
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
    refreshFormSources(form);
    if (form.id === "grazingForm") configureGrazingForm();
    if (form.id === "taskForm") configureTaskForm();
  }

  function setTodayDefaults() {
    document.querySelectorAll("input[type='date']:not([data-no-default])").forEach((input) => {
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

  function setNetworkState(state = navigator.onLine ? "online" : "offline") {
    const indicator = document.getElementById("networkState");
    const labels = {
      online: "En línea",
      offline: "Sin conexión",
      syncing: "Sincronizando"
    };
    indicator.textContent = labels[state] || labels.offline;
    indicator.dataset.state = state;
  }

  function resetLastSync(value) {
    document.getElementById("lastSync").textContent = value;
  }

  async function registerServiceWorker() {
    if ("serviceWorker" in navigator) {
      try {
        await navigator.serviceWorker.register(config.serviceWorkerUrl);
      } catch (error) {
        resetLastSync("No se pudo preparar el modo offline");
      }
    }
  }

  async function init() {
    db = await openDb();
    setTodayLabel();
    setTodayDefaults();
    bindTabs();
    bindQuickActions();
    bindForms();
    bindFarmContext();
    setCaptureEnabled(false);
    setNetworkState();
    await registerServiceWorker();
    const hasCachedData = await loadCachedBootstrap();
    await renderQueue();
    document.getElementById("syncNow").addEventListener("click", synchronize);
    document.getElementById("retryQueue").addEventListener("click", retryPendingEvents);
    window.addEventListener("online", async () => {
      setNetworkState("syncing");
      await synchronize();
    });
    window.addEventListener("offline", () => {
      setNetworkState("offline");
      resetLastSync("Guardado en dispositivo");
    });
    if (navigator.onLine) {
      await synchronize();
    } else if (!hasCachedData) {
      configureFarmContext();
      resetLastSync("Conéctate para cargar la hacienda");
    }
  }

  init().catch((error) => {
    resetLastSync(error.message || "Error");
  });
})();
