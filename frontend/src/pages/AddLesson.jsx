import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { PageHeader } from "../components/Common.jsx";

export default function AddLesson() {
  const nav = useNavigate();
  const [books, setBooks] = useState([]);
  const [bookId, setBookId] = useState("new");
  const [newBook, setNewBook] = useState("");
  const [title, setTitle] = useState("");
  const [sheikh, setSheikh] = useState("");
  const [date, setDate] = useState("");
  const [source, setSource] = useState("youtube");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState(null);

  useEffect(() => {
    api.books().then((b) => { setBooks(b); if (b.length) setBookId(String(b[0].id)); });
    api.status().then(setStatus).catch(() => {});
  }, []);

  async function submit(e) {
    e.preventDefault();
    setError("");
    const fd = new FormData();
    fd.append("title", title);
    if (bookId === "new") fd.append("new_book_title", newBook);
    else fd.append("book_id", bookId);
    fd.append("sheikh", sheikh);
    fd.append("date", date);
    if (source === "youtube") fd.append("youtube_url", url);
    else if (file) fd.append("file", file);
    setBusy(true);
    try {
      const lesson = await api.createLesson(fd);
      nav(`/lessons/${lesson.id}`, { replace: true });
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <PageHeader title="إضافة درس جديد" />
      {status?.provider === "mock" && (
        <p className="notice small">
          يعمل التطبيق الآن في الوضع التجريبي دون مفتاح Gemini: سيُحفظ الدرس ويُعرض بتفريغ مثال ثابت. أضف المفتاح لتفريغ الدروس فعليًا.
        </p>
      )}
      <form className="form" onSubmit={submit}>
        <label>الكتاب
          <select value={bookId} onChange={(e) => setBookId(e.target.value)}>
            {books.map((b) => <option key={b.id} value={b.id}>{b.title}</option>)}
            <option value="new">+ كتاب جديد</option>
          </select>
        </label>
        {bookId === "new" && (
          <label>اسم الكتاب
            <input required value={newBook} onChange={(e) => setNewBook(e.target.value)} placeholder="مثال: الأصول الثلاثة" />
          </label>
        )}
        <label>عنوان الدرس
          <input required value={title} onChange={(e) => setTitle(e.target.value)} placeholder="مثال: الدرس 3 - الشرك وأنواعه" />
        </label>
        <label>الشيخ
          <input value={sheikh} onChange={(e) => setSheikh(e.target.value)} placeholder="اسم الشيخ" />
        </label>
        <label>تاريخ الدرس
          <input value={date} onChange={(e) => setDate(e.target.value)} placeholder="مثال: ١٢ رجب ١٤٤٧ هـ" />
        </label>

        <div className="segmented">
          <button type="button" className={source === "youtube" ? "active" : ""} onClick={() => setSource("youtube")}>رابط يوتيوب</button>
          <button type="button" className={source === "file" ? "active" : ""} onClick={() => setSource("file")}>تسجيل من الجهاز</button>
        </div>
        {source === "youtube" ? (
          <label>رابط الدرس أو البث
            <input required dir="ltr" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://www.youtube.com/watch?v=…" />
            <span className="hint">يُرسل الرابط إلى Gemini مباشرة دون تنزيل الفيديو.</span>
          </label>
        ) : (
          <label>ملف التسجيل (صوت أو فيديو)
            <input required type="file" accept="audio/*,video/*" onChange={(e) => setFile(e.target.files[0])} />
          </label>
        )}

        {status?.max_minutes > 0 && (
          <p className="hint">في النسخة التجريبية يُفرَّغ أول {status.max_minutes} دقائق من كل تسجيل (لحماية الحصة المجانية للخدمة).</p>
        )}
        {status?.lessons_today?.limit > 0 && (
          <p className={status.lessons_today.left === 0 ? "notice small" : "hint"}>
            {status.lessons_today.left === 0
              ? "بلغت النسخة التجريبية حدها اليومي من الدروس الجديدة (لأسباب تتعلق بالميزانية). تصفّح الدروس الجاهزة، أو جرّب غدًا بعد 10 صباحًا بتوقيت السعودية."
              : `لأسباب تتعلق بالميزانية، عدد الدروس الجديدة في النسخة التجريبية محدود: بقي اليوم ${status.lessons_today.left} من ${status.lessons_today.limit}.`}
          </p>
        )}
        {status?.quota?.exhausted && (
          <p className="notice small">انتهت الحصة اليومية للنموذج الأساسي؛ سيُستخدم نموذج احتياطي أقل دقة حتى تتجدد الحصة (10 صباحًا بتوقيت السعودية).</p>
        )}
        <p className="hint">أضف دروسًا يحق لك الوصول إليها. دفترك خاص بك، ولا يُفرَّغ كلام الحضور حفاظًا على خصوصيتهم.</p>
        {error && <p className="notice error">{error}</p>}
        <button className="btn-primary wide" disabled={busy || status?.lessons_today?.left === 0}>{busy ? "جارٍ الإضافة…" : "ابدأ المعالجة"}</button>
      </form>
    </div>
  );
}
