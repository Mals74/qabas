import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api.js";
import Ask from "../components/Ask.jsx";
import Cards from "../components/Cards.jsx";
import { ErrorBox, LessonRow, Loading, PageHeader } from "../components/Common.jsx";

const TABS = [
  { key: "lessons", label: "الدروس" },
  { key: "cards", label: "بطاقات المراجعة" },
  { key: "ask", label: "اسأل الدروس" },
];

export default function BookPage() {
  const { id } = useParams();
  const [book, setBook] = useState(null);
  const [cards, setCards] = useState([]);
  const [tab, setTab] = useState("lessons");
  const [error, setError] = useState("");

  useEffect(() => {
    api.book(id).then(setBook).catch((e) => setError(e.message));
    api.bookCards(id).then(setCards).catch(() => {});
  }, [id]);

  if (error) return <div className="page"><ErrorBox message={error} /></div>;
  if (!book) return <div className="page"><Loading /></div>;

  return (
    <div className="page">
      <PageHeader title={book.title} subtitle={book.author} />
      <div className="segmented">
        {TABS.map((t) => (
          <button key={t.key} className={tab === t.key ? "active" : ""} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === "lessons" && (
        <div className="list">
          {book.lessons.map((l) => <LessonRow key={l.id} lesson={l} showBook={false} />)}
        </div>
      )}
      {tab === "cards" && <Cards cards={cards} />}
      {tab === "ask" && (
        <>
          <p className="muted small">يجيب من كلام الشيخ في جميع دروس هذا الكتاب، ويحيل كل إجابة إلى الدرس والدقيقة.</p>
          <Ask bookId={book.id} />
        </>
      )}
    </div>
  );
}
