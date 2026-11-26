"use strict";
// Browser client for operator-started localhost-only Recipe Studio.
// No hardware API and no remote production library.
window.RD6018StudioSave = (() => {
  const config = window.RD6018_STUDIO_CONFIG;
  const connected = !!(config && location.origin === config.origin &&
    location.hostname === "127.0.0.1" && config.token);
  async function submit(kind, recipe, save) {
    if (!connected) throw Error(
      "Редактор открыт без локального моста. Запустите Recipe Studio на HOME-PC.");
    const response = await fetch(save ? "/api/save" : "/api/check", {
      method: "POST", mode: "same-origin",
      credentials: "omit",
      headers: {
        "Content-Type": "application/json",
        "X-Recipe-Studio-Token": config.token
      },
      body: JSON.stringify({kind, recipe}),
    });
    const result = await response.json();
    if (!response.ok) throw Error(result.error || "Сохранение отклонено сервером.");
    if (result.physical_start_authorized !== false)
      throw Error("Некорректный ответ проверки: отсутствует запрет физического START.");
    return result;
  }
  async function library(operation, request) {
    if (!connected) throw Error("Запустите локальный Recipe Studio на HOME-PC.");
    if (!["list", "load", "compare", "archive"].includes(operation))
      throw Error("Недопустимая операция библиотеки.");
    const response = await fetch("/api/" + operation, {
      method: "POST", mode: "same-origin", credentials: "omit",
      headers: {"Content-Type": "application/json", "X-Recipe-Studio-Token": config.token},
      body: JSON.stringify(request),
    });
    const result = await response.json();
    if (!response.ok) throw Error(result.error || "Операция отклонена.");
    if (result.physical_start_authorized !== false)
      throw Error("Недопустимый ответ библиотеки.");
    return result;
  }
  return {connected, submit, library};
})();
