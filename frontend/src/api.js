// Tiny API client for the FastAPI backend.

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(`/api${path}`, options);
  } catch {
    throw new Error("تعذّر الاتصال بالخادم. تأكد من الإنترنت ثم أعد المحاولة.");
  }
  const isJson = res.headers.get("content-type")?.includes("application/json");
  const body = isJson ? await res.json() : null;
  if (!res.ok) {
    // FastAPI puts error messages in `detail`
    if (body?.detail) throw new Error(typeof body.detail === "string" ? body.detail : "طلب غير صالح");
    // No JSON: the server itself did not answer (502/503/504 = waking up or restarting on the free plan)
    if ([502, 503, 504].includes(res.status))
      throw new Error("الخادم يستيقظ أو يُعاد تشغيله. انتظر دقيقة ثم حدّث الصفحة.");
    throw new Error(`حدث خطأ غير متوقع (رمز ${res.status}). حدّث الصفحة، وإن تكرر أرسل لنا لقطة شاشة.`);
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
  retryExtras: (id) => request(`/lessons/${id}/retry-extras`, { method: "POST" }),
  reprocess: (id) => request(`/lessons/${id}/reprocess`, { method: "POST" }),
  deleteLesson: (id) => request(`/lessons/${id}`, { method: "DELETE" }),
  addNote: (id, start, text) => request(`/lessons/${id}/notes`, json("POST", { start, text })),
  deleteNote: (id) => request(`/notes/${id}`, { method: "DELETE" }),
  takhrij: (segmentId) => request(`/segments/${segmentId}/takhrij`),
  resolve: (segmentId, markId, text) => request(`/segments/${segmentId}/resolve`, json("POST", { mark_id: markId, text })),
  search: (q) => request(`/search?q=${encodeURIComponent(q)}`),
};
