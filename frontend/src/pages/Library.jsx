import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { ErrorBox, Loading, PageHeader } from "../components/Common.jsx";
import { Book, Chevron } from "../components/Icons.jsx";

export default function LibraryPage() {
  const [books, setBooks] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.books().then(setBooks).catch((e) => setError(e.message));
  }, []);

  return (
    <div className="page">
      <PageHeader title="مكتبتي" subtitle="دفترك الخاص: الدروس مرتبة بحسب الكتب" back={false} />
      {error && <ErrorBox message={error} />}
      {!books && !error && <Loading />}
      <div className="list">
        {books?.map((b) => (
          <Link key={b.id} to={`/books/${b.id}`} className="lesson-row">
            <div className="cover cover-book"><Book size={24} /></div>
            <div className="lesson-row-body">
              <h3>{b.title}</h3>
              {b.author && <p className="muted">{b.author}</p>}
              <p className="muted small">{b.lesson_count} {b.lesson_count === 1 ? "درس" : "دروس"}</p>
            </div>
            <Chevron />
          </Link>
        ))}
      </div>
      <Link to="/add" className="btn-outline wide">إضافة درس أو كتاب جديد</Link>
    </div>
  );
}
