const jsonHeaders = {
  "Content-Type": "application/json",
};

export async function getSessionStatus() {
  const response = await fetch("/api/v1/session/status");
  return response.json();
}

export async function getCurrentClassroom() {
  const response = await fetch("/api/v1/classroom/current");
  return response.json();
}

export async function getSettings() {
  const response = await fetch("/api/v1/settings");
  return response.json();
}

export async function getRecords(params = {}) {
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      searchParams.set(key, String(value));
    }
  }
  const query = searchParams.toString();
  const response = await fetch(`/api/v1/records${query ? `?${query}` : ""}`);
  return response.json();
}

export async function deleteRecord(alertId) {
  const response = await fetch(`/api/v1/records/${alertId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error("delete record failed");
  }
  return response.json();
}

export async function getAnalyticsOverview(params = {}) {
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      searchParams.set(key, String(value));
    }
  }
  const query = searchParams.toString();
  const response = await fetch(`/api/v1/analytics/overview${query ? `?${query}` : ""}`);
  return response.json();
}

export async function updateSettings(payload) {
  const response = await fetch("/api/v1/settings", {
    method: "PUT",
    headers: jsonHeaders,
    body: JSON.stringify(payload),
  });
  return response.json();
}

export async function startSession(payload) {
  const response = await fetch("/api/v1/session/start", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify(payload),
  });
  return response.json();
}

export async function stopSession() {
  const response = await fetch("/api/v1/session/stop", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({}),
  });
  return response.json();
}

export function createRealtimeSocket({ onMessage, onError, onClose }) {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(`${protocol}//${window.location.host}/ws/classroom/realtime`);
  socket.addEventListener("message", (event) => {
    onMessage?.(JSON.parse(event.data));
  });
  socket.addEventListener("error", (event) => {
    onError?.(event);
  });
  socket.addEventListener("close", (event) => {
    onClose?.(event);
  });
  return socket;
}
