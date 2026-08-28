(function () {
  const DB_NAME = "kore-agro-field";
  const DB_VERSION = 1;
  const EVENT_STORE = "events";
  const META_STORE = "meta";
  const config = window.KORE_FIELD_CONFIG;

  let db;
  let masters = { farms: [], groups: [], animals: [], inputs: [] };

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
      detail: ""
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
    const pending = events.filter((event) => event.status !== "acked");
    document.getElementById("queueCount").textContent = String(pending.length);
    const list = document.getElementById("queueList");
    list.innerHTML = "";
    pending
      .sort((a, b) => a.client_sequence - b.client_sequence)
      .slice(0, 20)
      .forEach((event) => {
        const item = document.createElement("li");
        item.textContent = `${event.client_sequence} - ${event.event_type} - ${event.status}`;
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

    const response = await fetch(config.syncUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ events })
    });

    if (!response.ok) {
      resetLastSync(`Error HTTP ${response.status}`);
      return;
    }

    const data = await response.json();
    for (const result of data.results || []) {
      if (result.status === "acked") {
        await del(EVENT_STORE, result.event_id);
      } else {
        const event = await get(EVENT_STORE, result.event_id);
        if (event) {
          event.status = "failed";
          event.detail = result.detail || "";
          await put(EVENT_STORE, event);
        }
      }
    }
    resetLastSync(new Date().toLocaleTimeString());
    await renderQueue();
  }

  async function loadBootstrap() {
    try {
      const response = await fetch(config.bootstrapUrl);
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
  }

  function populateSelects() {
    document.querySelectorAll("select[data-source]").forEach((select) => {
      const source = select.dataset.source;
      const required = select.hasAttribute("required");
      select.innerHTML = required ? "" : '<option value="">N/A</option>';
      (masters[source] || []).forEach((item) => {
        const option = document.createElement("option");
        option.value = item.id;
        option.textContent = labelFor(source, item);
        select.appendChild(option);
      });
    });
  }

  function labelFor(source, item) {
    if (source === "farms") {
      return `${item.code} - ${item.name}`;
    }
    if (source === "groups") {
      return item.name;
    }
    if (source === "animals") {
      return `${item.tag} - ${item.status}`;
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
      event.currentTarget.reset();
      setTodayDefaults();
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
      event.currentTarget.reset();
      setTodayDefaults();
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
      event.currentTarget.reset();
      setTodayDefaults();
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
      event.currentTarget.reset();
      setTodayDefaults();
    });

    document.querySelector("select[name='target_type']").addEventListener("change", (event) => {
      const isGroup = event.target.value === "group";
      document.querySelector(".targetAnimal").classList.toggle("hidden", isGroup);
      document.querySelector(".targetGroup").classList.toggle("hidden", !isGroup);
    });
  }

  function bindTabs() {
    document.querySelectorAll(".tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active"));
        document.querySelectorAll(".panel").forEach((panel) => panel.classList.remove("active"));
        tab.classList.add("active");
        document.getElementById(tab.dataset.panel).classList.add("active");
      });
    });
  }

  function setTodayDefaults() {
    document.querySelectorAll("input[type='date']").forEach((input) => {
      input.value = todayIso();
    });
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
    setTodayDefaults();
    bindTabs();
    bindForms();
    updateNetworkState();
    await registerServiceWorker();
    await loadBootstrap();
    await renderQueue();
    document.getElementById("syncNow").addEventListener("click", syncQueue);
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

