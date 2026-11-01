const base = "/api";

async function request(path, options = {}) {
  const response = await fetch(`${base}${path}`, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  const data = await response.json().catch(() => null);
  if (!response.ok)
    throw new Error(
      data?.message || "Не вдалося виконати дію. Спробуйте ще раз.",
    );
  return data;
}

export const api = {
  overview: () => request("/overview"),
  tests: () => request("/tests"),
  createTest: (body) =>
    request("/tests", { method: "POST", body: JSON.stringify(body) }),
  updateTest: (id, body) =>
    request(`/tests/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteTest: (id) => request(`/tests/${id}`, { method: "DELETE" }),
  attempt: (body) =>
    request("/attempts", { method: "POST", body: JSON.stringify(body) }),
  favorites: (testId) =>
    request("/favorites", { method: "POST", body: JSON.stringify({ testId }) }),
  friends: () => request("/friends"),
  friendProfile: (id) => request(`/friends/${id}/profile`),
  friendRequest: (username) =>
    request("/friend-requests", {
      method: "POST",
      body: JSON.stringify({ username }),
    }),
  respondRequest: (id, action) =>
    request(`/friend-requests/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ action }),
    }),
};
