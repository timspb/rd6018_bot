"use strict";
// RS-1C UI only. Catalog is a generated snapshot; Python is authoritative on save.
(function () {
  const data = window.RD6018_NATIVE_CATALOG;
  const root = document.getElementById("nativeStudio");
  if (!root) return;
  const $ = id => document.getElementById(id);
  const escapeText = text => String(text).replace(/[&<>"']/g, char =>
    ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
  const defaultState = {name: "my_efb", version: 1, recipeId: "native_efb_normal", overrides: {}};
  let state = {...defaultState};
  if (!data || data.schema !== "rd6018.native_recipe_ui_catalog.v1" ||
      !Array.isArray(data.recipes) || data.recipes.length !== 12) {
    $("nativeStatus").textContent = "Нет каталога параметров. Перегенерируйте штатный каталог.";
    return;
  }
  const lookup = id => data.recipes.find(item => item.recipe_id === id);
  function inspectDraft(name, version, baseId, overrides) {
    if (!/^[a-zA-Z0-9_-]{1,60}$/.test(name) || name.startsWith("native_") ||
        !Number.isSafeInteger(version) || version < 1) throw Error("Имя или версия недопустимы.");
    const entry = lookup(baseId);
    if (!entry) throw Error("Неизвестный штатный рецепт.");
    const permitted = new Map(entry.parameters.filter(p => p.editable).map(p => [p.key, p]));
    const normalized = {};
    for (const [key, value] of Object.entries(overrides)) {
      const spec = permitted.get(key);
      if (!spec) throw Error("Параметр не разрешён: " + key);
      if (typeof value !== "number" || !Number.isFinite(value) ||
          (spec.type === "int" && !Number.isSafeInteger(value)) ||
          (spec.minimum !== null && value < spec.minimum) ||
          (spec.maximum !== null && value > spec.maximum))
        throw Error("Параметр вне диапазона: " + key);
      normalized[key] = value;
    }
    return {name, version, draft: {
      schema: 1, base_recipe_id: baseId,
      execution_kind: "native_authority", overrides: normalized
    }};
  }
  function choose() {
    const id = $("nativePreset").value;
    state = {name: $("nativeName").value, version: Number($("nativeVersion").value),
      recipeId: id, overrides: {}};
    draw();
  }
  function draw() {
    const entry = lookup(state.recipeId);
    if (!entry) return;
    $("nativePreset").value = entry.recipe_id;
    $("nativeName").value = state.name;
    $("nativeVersion").value = state.version;
    $("nativeFields").innerHTML = entry.parameters.map(spec => {
      const active = Object.hasOwn(state.overrides, spec.key);
      const value = active ? state.overrides[spec.key] : spec.default;
      const range = [spec.minimum, spec.maximum].map(v => v === null ? "—" : v).join(" … ");
      return '<tr><td><strong>' + escapeText(spec.description) + '</strong><small>' +
        escapeText(spec.key) + '</small></td><td>' + escapeText(spec.unit) + '</td><td>' +
        escapeText(spec.default) + '</td><td>' + escapeText(range) + '</td><td>' +
        (spec.editable ? '<input type="number" data-key="' + escapeText(spec.key) +
          '" step="' + (spec.type === "int" ? "1" : "any") + '" value="' + escapeText(value) +
          '" aria-label="' + escapeText(spec.key) + '">' :
          '<span class="muted">Недоступно для исполнения</span>') +
        '</td><td>' + (spec.editable ? (active ? "Изменено" : "Штатное") : "Только просмотр") +
        '</td></tr>';
    }).join("");
    $("nativeStatus").textContent = entry.profile + " / " + entry.intent +
      " · параметры из штатного каталога · без запуска оборудования";
    $("nativeJSON").textContent = JSON.stringify({
      name: state.name, version: state.version,
      draft: {schema:1,base_recipe_id:state.recipeId,
        execution_kind:"native_authority",overrides:state.overrides}
    }, null, 2);
  }
  function report(error) {
    $("nativeError").textContent = error instanceof Error ? error.message : String(error);
  }
  $("nativePreset").innerHTML = data.recipes.map(entry =>
    '<option value="' + escapeText(entry.recipe_id) + '">' +
    escapeText(entry.profile + " · " + entry.intent) + '</option>').join("");
  $("nativePreset").addEventListener("change", choose);
  $("nativeName").addEventListener("change", () => {state.name = $("nativeName").value; draw();});
  $("nativeVersion").addEventListener("change", () => {
    state.version = Number($("nativeVersion").value); draw();
  });
  $("nativeFields").addEventListener("change", event => {
    const key = event.target.dataset.key;
    if (!key) return;
    const entry = lookup(state.recipeId);
    const spec = entry.parameters.find(p => p.key === key);
    if (!spec || !spec.editable) return;
    const raw = event.target.value;
    if (!raw.trim()) {report("Требуется число: " + key); return;}
    const value = Number(raw);
    try {
      const candidate = {...state.overrides, [key]:value};
      inspectDraft(state.name, state.version, state.recipeId, candidate);
      state.overrides = candidate;
      $("nativeError").textContent = "";
      draw();
    } catch (error) {report(error); event.target.value = state.overrides[key] ?? spec.default;}
  });
  $("nativeReset").addEventListener("click", () => {state.overrides = {}; draw();});
  $("nativeExport").addEventListener("click", () => {
    try {
      state.name = $("nativeName").value;
      state.version = Number($("nativeVersion").value);
      const payload = inspectDraft(state.name, state.version, state.recipeId, state.overrides);
      const url = URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],
        {type:"application/json"}));
      const a = document.createElement("a");
      a.href = url; a.download = "rd6018-native-draft.json"; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      $("nativeError").textContent = "Черновик экспортирован. Проверить: check-native; сохранить: save-native.";
    } catch (error) {report(error);}
  });
  $("nativeImportBtn").addEventListener("click", () => $("nativeFile").click());
  $("nativeFile").addEventListener("change", async event => {
    try {
      const file = event.target.files[0];
      if (!file) return;
      if (file.size > 256 * 1024) throw Error("Слишком большой JSON.");
      const document = JSON.parse(await file.text());
      if (!document || Object.keys(document).sort().join(",") !== "draft,name,version" ||
          !document.draft || Object.keys(document.draft).sort().join(",") !==
          "base_recipe_id,execution_kind,overrides,schema" ||
          document.draft.schema !== 1 ||
          document.draft.execution_kind !== "native_authority" ||
          !document.draft.overrides || typeof document.draft.overrides !== "object" ||
          Array.isArray(document.draft.overrides)) throw Error("Неверный формат native-черновика.");
      const verified = inspectDraft(document.name, document.version,
        document.draft.base_recipe_id, document.draft.overrides);
      state = {name:verified.name, version:verified.version,
        recipeId:verified.draft.base_recipe_id, overrides:verified.draft.overrides};
      $("nativeError").textContent = "";
      draw();
    } catch (error) {report(error);}
    finally {event.target.value = "";}
  });
  draw();
  window.RD6018NativeStudio = {inspectDraft};
})();
