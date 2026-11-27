"use strict";
// RS-2 UI: read-only history, immutable new-version draft, one-way archive.
(() => {
  const $ = id => document.getElementById(id);
  const backend = window.RD6018StudioSave;
  const validName = name => /^[A-Za-z0-9_-]{1,80}$/.test(name);
  let items = [];
  function status(message) { $("libraryStatus").textContent = message; }
  function selected() { return items.find(item => item.id === $("libraryId").value); }
  function options(values) {
    return values.map(x => {
      const value = typeof x === "number" ? x : x.id;
      return '<option value="' + value + '">' + String(value) + '</option>';
    }).join("");
  }
  function renderVersions() {
    const item = selected();
    const versions = item?.versions || [];
    $("libraryVersion").innerHTML = options(versions);
    $("libraryCompareWith").innerHTML = options(versions);
    $("libraryVersion").value = String(item?.latest ?? "");
    $("libraryCompareWith").value = String(versions.at(-2) ?? item?.latest ?? "");
    $("libraryArchive").disabled = !item || item.archived;
    status(item ? (item.archived ? "Архив: только чтение" : "Активный рецепт") +
      " · версии: " + versions.join(", ") : "В библиотеке нет рецептов выбранного типа.");
  }
  async function refresh() {
    try {
      const kind = $("libraryKind").value;
      const response = await backend.library("list", {kind});
      items = response.items;
      $("libraryId").innerHTML = options(items);
      renderVersions();
    } catch (err) { status("Ошибка чтения библиотеки: " + err.message); }
  }
  $("libraryKind").addEventListener("change", refresh);
  $("libraryRefresh").addEventListener("click", refresh);
  $("libraryId").addEventListener("change", renderVersions);
  $("libraryLoad").addEventListener("click", async () => {
    try {
      const item = selected();
      if (!item || !validName(item.id)) throw Error("Выберите сохранённый рецепт.");
      if (item.archived) throw Error("Архивный рецепт нельзя редактировать; историю можно сравнивать.");
      const kind = $("libraryKind").value;
      const version = Number($("libraryVersion").value);
      const result = await backend.library("load", {kind, id:item.id, version});
      const next = item.latest + 1;
      if (kind === "native") window.RD6018NativeStudio.loadForEdit(result.recipe, next);
      else window.RD6018StepStudio.loadForEdit(result.recipe, next);
      status("Открыт черновик " + item.id + " v" + next + " из v" + version +
        ". Изменения не сохранены.");
    } catch (err) { status("Открытие отклонено: " + err.message); }
  });
  $("libraryCompare").addEventListener("click", async () => {
    try {
      const item = selected();
      if (!item) throw Error("Выберите рецепт.");
      const result = await backend.library("compare", {
        kind:$("libraryKind").value, id:item.id,
        left:Number($("libraryCompareWith").value),
        right:Number($("libraryVersion").value),
      });
      $("libraryDiff").textContent = result.changed ? result.diff : "Изменений нет.";
      status("Сравнение " + item.id + ": v" + result.left + " ↔ v" + result.right);
    } catch (err) { status("Сравнение отклонено: " + err.message); }
  });
  $("libraryArchive").addEventListener("click", async () => {
    const item = selected();
    if (!item || item.archived) return;
    if (!window.confirm("Архивировать " + item.id +
      "? Все версии останутся доступны для чтения, но сохранение новых будет запрещено.")) return;
    try {
      await backend.library("archive", {kind:$("libraryKind").value, id:item.id});
      await refresh();
      status("Рецепт " + item.id + " архивирован; версии не изменены.");
    } catch (err) { status("Архивирование отклонено: " + err.message); }
  });
  if (backend?.connected) refresh();
  else status("Локальный мост не запущен. Библиотека недоступна в file://.");
})();
