// Hitek68 keybind editor frontend.

const state = {
  layers: [],
  activeLayer: 0,
  layout: [],
  behaviors: [],
  keycodes: {},
  selected: null, // {position}
  dirty: false,
};

const SCALE = 0.55; // layout units -> svg units

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

async function init() {
  try {
    const st = await api("/api/status");
    const el = document.getElementById("status");
    if (st.connected) {
      el.textContent = `Connected${st.unlocked ? "" : " (locked)"}`;
      el.className = "status connected";
    } else {
      el.textContent = "Not connected";
      el.className = "status disconnected";
      document.getElementById("hint").textContent =
        "Dongle not found. Plug it in and reload. (" + (st.error || "") + ")";
      return;
    }
  } catch (e) {
    document.getElementById("status").textContent = "Server error";
    return;
  }

  const [km, layout, kc] = await Promise.all([
    api("/api/keymap"),
    api("/api/layout"),
    api("/api/keycodes"),
  ]);
  state.layers = km.layers;
  state.layout = layout.keys;
  state.keycodes = kc;

  // Behaviors are slow (one RPC each); load in background.
  api("/api/behaviors").then((b) => {
    state.behaviors = b.behaviors;
    populateBehaviors();
  });

  renderLayerTabs();
  renderBoard();
  updateToolbar();
  populateKeySelect("");
}

function renderLayerTabs() {
  const nav = document.getElementById("layers");
  nav.innerHTML = "";
  state.layers.forEach((l, i) => {
    const b = document.createElement("button");
    b.textContent = l.name || `Layer ${l.id}`;
    b.className = i === state.activeLayer ? "active" : "";
    b.onclick = () => {
      state.activeLayer = i;
      state.selected = null;
      renderLayerTabs();
      renderBoard();
    };
    nav.appendChild(b);
  });
}

function bindingLabel(binding) {
  // Resolve a human-readable label for a binding.
  const { behavior_id, param1 } = binding;
  // Try to match a known key_press behavior by display name later; for now
  // decode keycodes directly and show behavior id for non-kp.
  const name = keycodeName(param1);
  if (name) return name;
  return `#${behavior_id.toString(16)}`;
}

function keycodeName(value) {
  for (const [name, v] of Object.entries(state.keycodes)) {
    if (v === value) return name;
  }
  return null;
}

function renderBoard() {
  const svg = document.getElementById("board");
  svg.innerHTML = "";
  const layer = state.layers[state.activeLayer];
  if (!layer) return;

  state.layout.forEach((k, pos) => {
    if (k.w === 0) return; // unpopulated
    const x = k.x * SCALE, y = k.y * SCALE;
    const w = k.w * SCALE, h = k.h * SCALE;

    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");

    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    rect.setAttribute("x", x + 2);
    rect.setAttribute("y", y + 2);
    rect.setAttribute("width", w - 4);
    rect.setAttribute("height", h - 4);
    rect.setAttribute("rx", 8);
    rect.setAttribute("class", "key" + (state.selected?.position === pos ? " selected" : ""));
    rect.addEventListener("click", () => openPicker(pos));
    g.appendChild(rect);

    const binding = layer.bindings[pos];
    if (binding) {
      const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
      label.setAttribute("x", x + w / 2);
      label.setAttribute("y", y + h / 2 - 6);
      label.setAttribute("class", "key-label");
      label.textContent = shortLabel(bindingLabel(binding));
      g.appendChild(label);

      const sub = document.createElementNS("http://www.w3.org/2000/svg", "text");
      sub.setAttribute("x", x + w / 2);
      sub.setAttribute("y", y + h / 2 + 16);
      sub.setAttribute("class", "key-sub");
      sub.textContent = `pos ${pos}`;
      g.appendChild(sub);
    }
    svg.appendChild(g);
  });
}

function shortLabel(name) {
  // Trim verbose names to fit on a keycap.
  return name
    .replace("C_VOL_UP", "VOL+")
    .replace("C_VOL_DN", "VOL-")
    .replace("C_MUTE", "MUTE")
    .replace("C_PP", "PLAY")
    .replace("ENTER", "ENT")
    .replace("SPACE", "SPC")
    .replace("BSPC", "⌫")
    .replace("LCTRL", "CTL")
    .replace("RCTRL", "CTL")
    .replace("LGUI", "GUI")
    .replace("RGUI", "GUI")
    .replace("LALT", "ALT")
    .replace("RALT", "ALT")
    .replace("LSHIFT", "SHF")
    .replace("RSHIFT", "SHF");
}

// ---- Picker ----

function populateBehaviors() {
  const sel = document.getElementById("behavior-select");
  sel.innerHTML = "";
  const common = ["key_press", "mo", "tog", "lt", "trans", "none", "hold_tap"];
  const sorted = [...state.behaviors].sort((a, b) => {
    const ai = common.indexOf(a.name), bi = common.indexOf(b.name);
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
  });
  for (const b of sorted) {
    const o = document.createElement("option");
    o.value = b.id;
    o.textContent = b.name || `0x${b.id.toString(16)}`;
    sel.appendChild(o);
  }
}

function populateKeySelect(filter) {
  const sel = document.getElementById("key-select");
  sel.innerHTML = "";
  const f = filter.trim().toUpperCase();
  const names = Object.keys(state.keycodes)
    .filter((n) => !f || n.includes(f))
    .sort()
    .slice(0, 200);
  for (const n of names) {
    const o = document.createElement("option");
    o.value = n;
    o.textContent = n;
    sel.appendChild(o);
  }
}

function openPicker(pos) {
  state.selected = { position: pos };
  renderBoard();
  const layer = state.layers[state.activeLayer];
  const binding = layer.bindings[pos];
  document.getElementById("picker-title").textContent =
    `Edit key — Layer ${layer.id}, pos ${pos} (now: ${bindingLabel(binding)})`;
  document.getElementById("picker").classList.remove("hidden");
  document.getElementById("key-search").value = "";
  populateKeySelect("");
}

function closePicker() {
  document.getElementById("picker").classList.add("hidden");
  state.selected = null;
  renderBoard();
}

async function applyPicker() {
  const pos = state.selected.position;
  const layer = state.layers[state.activeLayer];
  const behaviorId = parseInt(document.getElementById("behavior-select").value, 10);
  const keyName = document.getElementById("key-select").value;

  let param1 = 0, param2 = 0;
  const bName = document.getElementById("behavior-select").selectedOptions[0]?.textContent;
  if (bName === "key_press" || bName === "kp") {
    param1 = state.keycodes[keyName] ?? 0;
  } else if (bName === "mo" || bName === "tog") {
    param1 = parseInt(document.getElementById("layer-param").value, 10) || 0;
  } else if (bName === "lt") {
    param1 = parseInt(document.getElementById("layer-param").value, 10) || 0;
    param2 = state.keycodes[keyName] ?? 0;
  }

  const res = await api("/api/binding", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      layer_id: layer.id,
      position: pos,
      behavior_id: behaviorId,
      param1, param2,
    }),
  });

  if (res.ok) {
    layer.bindings[pos] = { behavior_id: behaviorId, param1, param2 };
    state.dirty = true;
  } else {
    alert("Device rejected the binding.");
  }
  closePicker();
  updateToolbar();
}

function updateToolbar() {
  document.getElementById("save-btn").disabled = !state.dirty;
  document.getElementById("discard-btn").disabled = !state.dirty;
  document.getElementById("unsaved-note").textContent = state.dirty
    ? "Unsaved changes — they only persist after Save."
    : "";
}

document.getElementById("behavior-select").addEventListener("change", (e) => {
  const name = e.target.selectedOptions[0]?.textContent;
  document.getElementById("layer-param-wrap").classList.toggle(
    "hidden", !(name === "mo" || name === "tog" || name === "lt"));
});

document.getElementById("key-search").addEventListener("input", (e) => {
  populateKeySelect(e.target.value);
});
document.getElementById("picker-apply").onclick = applyPicker;
document.getElementById("picker-cancel").onclick = closePicker;
document.getElementById("save-btn").onclick = async () => {
  const r = await api("/api/save", { method: "POST" });
  if (r.ok) { state.dirty = false; updateToolbar(); }
  else alert("Save failed.");
};
document.getElementById("discard-btn").onclick = async () => {
  await api("/api/discard", { method: "POST" });
  const km = await api("/api/keymap");
  state.layers = km.layers;
  state.dirty = false;
  renderBoard();
  updateToolbar();
};

init();
pollBattery();
setInterval(pollBattery, 5000);

async function pollBattery() {
  try {
    const b = await api("/api/battery");
    const l = document.getElementById("bat-l");
    const r = document.getElementById("bat-r");
    l.textContent = "L " + (b.left == null ? "--%" : b.left + "%");
    r.textContent = "R " + (b.right == null ? "--%" : b.right + "%");
    l.className = b.left == null ? "na" : (b.left <= 20 ? "low" : "");
    r.className = b.right == null ? "na" : (b.right <= 20 ? "low" : "");
    document.getElementById("battery").style.opacity = b.connected ? "1" : "0.4";
  } catch (e) { /* server hiccup; try again next poll */ }
}

document.getElementById("sleep-apply").onclick = async () => {
  const minutes = parseFloat(document.getElementById("sleep-minutes").value) || 0;
  const target = document.getElementById("sleep-target").value;
  const r = await api("/api/sleep", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ timeout_ms: Math.round(minutes * 60000), target }),
  });
  if (!r.ok) alert("Sleep update failed: " + (r.error || "unknown error"));
};
