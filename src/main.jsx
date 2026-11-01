import React from "react";
import ReactDOM from "react-dom/client";
import { setupWorker } from "msw/browser";
import { handlers } from "./mocks/handlers";
import "./index.css";

// Account access is checked by the Python backend before loading the demo tests.
try {
  const response = await fetch("/session", { credentials: "same-origin" });
  if (response.status === 401) {
    window.location.replace("/login");
    throw new Error("Потрібен вхід");
  }
  if (!response.ok) throw new Error("Сервер облікових записів недоступний");
  const session = await response.json();
  window.__FORMA_ACCOUNT__ = session.user;
  window.__FORMA_CSRF__ = session.csrf;
  window.__FORMA_EVENTS__ = session.recent_events ?? [];
  window.__FORMA_SESSIONS__ = Array.isArray(session.sessions) ? session.sessions : null;
} catch (error) {
  if (error.message !== "Потрібен вхід") {
    document.getElementById("root").textContent =
      `${error.message}. Запустіть backend: python backend/app.py`;
  }
  throw error;
}

// The existing test content remains a local demo, scoped to the signed-in account.
await setupWorker(...handlers).start({
  onUnhandledRequest: "bypass",
  quiet: true,
});
const { default: App } = await import("./App.jsx");
ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
