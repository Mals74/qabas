import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import { PageHeader } from "../components/Common.jsx";
import { Search } from "../components/Icons.jsx";

export default function SearchPage() {
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get("q") || "");
  const [res, setRes] = useState(null);
  const nav = useNavigate();

  useEffect(() => {
    const query = params.get("q");
    if (query) api.search(query).then(setRes);
  }, [params]);

  return (
    <div className="page">
      <PageHeader title="البحث" subtitle="في كتبك ودروسك وكلام الشيخ" back={false} />
      <form className="search-box" onSubmit={(e) => { e.preventDefault(); setParams({ q }); }}>
        <Search size={20} />
        <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="ابحث عن كتاب، درس، أو كلمة…" />
      </form>

      <button className="link-btn" onClick={() => nav(q.trim() ? `/fahras?w=${encodeURIComponent(q.trim())}` : "/fahras")}>
        ابحث عن معنى كلمة في الفهرس (المعاجم العربية)
      </button>

      {res && (
        <>
          {res.books.length > 0 && <h3 className="section-title">الكتب</h3>}
          {res.books.map((b) => (
            <Link key={b.id} to={`/books/${b.id}`} className="result">{b.title}</Link>
          ))}
          <h3 className="section-title">في الدروس ({res.segments.length})</h3>
          {res.segments.length === 0 && <p className="muted">لا توجد نتائج.</p>}
          {res.segments.map((s) => (
            <Link key={s.segment_id} to={`/lessons/${s.lesson_id}?t=${Math.floor(s.start)}`} className="result">
              <p>{highlight(s.text, params.get("q"))}</p>
              <p className="muted small">{s.book_title} · {s.lesson_title} · الدقيقة {s.time}</p>
            </Link>
          ))}
        </>
      )}
    </div>
  );
}

// Bold the query inside the text when it appears as written
function highlight(text, q) {
  if (!q) return text;
  const i = text.indexOf(q);
  if (i < 0) return text;
  return <>{text.slice(0, i)}<mark>{q}</mark>{text.slice(i + q.length)}</>;
}
