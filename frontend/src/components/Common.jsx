// Shared layout pieces: page header, lesson row, loading/error states.
import { Link, useNavigate } from "react-router-dom";
import { Back, Book, Chevron, Flame } from "./Icons.jsx";

export function Logo({ small }) {
  return (
    <div className={`logo ${small ? "logo-small" : ""}`}>
      <Flame size={small ? 16 : 22} />
      <span className="logo-word">قَبَس</span>
      {!small && <span className="logo-tag">من درسٍ يُضيء دربك</span>}
    </div>
  );
}

export function PageHeader({ title, subtitle, back = true }) {
  const nav = useNavigate();
  return (
    <header className="page-header">
      {back && (
        <button className="icon-btn back" onClick={() => nav(-1)} aria-label="رجوع"><Back /></button>
      )}
      <h1>{title}</h1>
      {subtitle && <p className="subtitle">{subtitle}</p>}
    </header>
  );
}

const STATUS = { pending: "في الانتظار", processing: "قيد المعالجة", error: "تعذّرت المعالجة" };

export function LessonRow({ lesson, showBook = true }) {
  return (
    <Link to={`/lessons/${lesson.id}`} className="lesson-row">
      <div className="cover"><Book size={22} /></div>
      <div className="lesson-row-body">
        <h3>{lesson.title}</h3>
        {showBook && lesson.book_title && <p className="muted">{lesson.book_title}</p>}
        <p className="muted small">
          {lesson.sheikh}
          {lesson.date && ` · ${lesson.date}`}
          {lesson.status === "ready" && lesson.duration !== "0:00" && ` · ${lesson.duration}`}
        </p>
        {lesson.status !== "ready" && (
          <span className={`status status-${lesson.status}`}>{STATUS[lesson.status]}</span>
        )}
      </div>
      <Chevron />
    </Link>
  );
}

export function Loading() {
  return <div className="center muted">جارٍ التحميل…</div>;
}

export function ErrorBox({ message }) {
  return <div className="notice error">{message}</div>;
}
