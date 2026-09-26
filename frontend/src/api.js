// Tiny API client for the FastAPI backend.

async function request(path, options = {}) {
  const res = await fetch(`/api${path}`, options);
  const isJson = res.headers.get("content-type")?.includes("application/json");
  const body = isJson ? await res.json() : null;
  if (!res.ok) {
    // FastAPI puts error messages in `detail`
    throw new Error(body?.detail || "حدث خطأ غير متوقع");
  }
  return body;
}

const json = (method, data) => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(data),
});

export const api = {
  status: () => request("/status"),
  books: () => request("/books"),
  book: (id) => request(`/books/${id}`),
  createBook: (data) => request("/books", json("POST", data)),
  bookCards: (id) => request(`/books/${id}/cards`),
  ask: (id, question) => request(`/books/${id}/ask`, json("POST", { question })),
  recent: () => request("/lessons/recent"),
  lesson: (id) => request(`/lessons/${id}`),
  createLesson: (formData) => request("/lessons", { method: "POST", body: formData }),
  reprocess: (id) => request(`/lessons/${id}/reprocess`, { method: "POST" }),
  deleteLesson: (id) => request(`/lessons/${id}`, { method: "DELETE" }),
  addNote: (id, start, text) => request(`/lessons/${id}/notes`, json("POST", { start, text })),
  deleteNote: (id) => request(`/notes/${id}`, { method: "DELETE" }),
  takhrij: (segmentId) => request(`/segments/${segmentId}/takhrij`),
  search: (q) => request(`/search?q=${encodeURIComponent(q)}`),
};
