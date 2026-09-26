import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { ErrorBox, LessonRow, Loading, Logo } from "../components/Common.jsx";
import { Plus, Search } from "../components/Icons.jsx";

export default function Home() {
  const [lessons, setLessons] = useState(null);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const nav = useNavigate();

  useEffect(() => {
    api.recent().then(setLessons).catch((e) => setError(e.message));
  }, []);

  return (
    <div className="page">
      <Logo />

      <form className="search-box" onSubmit={(e) => { e.preventDefault(); if (q.trim()) nav(`/search?q=${encodeURIComponent(q)}`); }}>
        <Search size={20} />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="ابحث عن كتاب، درس، أو كلمة…" />
      </form>

      <section className="hero">
        <h2>ابدأ برحلتك التعليمية</h2>
        <p>حوّل أي درس من يوتيوب أو من جهازك إلى دفتر منظّم، مع آيات موثّقة وأحاديث مخرّجة وإحالة إلى كلام الشيخ.</p>
        <Link to="/add" className="btn-primary"><Plus /> إضافة درس جديد</Link>
      </section>

      <div className="section-head">
        <h2>أحدث الدروس</h2>
        <Link to="/library" className="link">عرض الكل</Link>
      </div>
      {error && <ErrorBox message={error} />}
      {!lessons && !error && <Loading />}
      <div className="list">
        {lessons?.map((l) => <LessonRow key={l.id} lesson={l} />)}
      </div>
    </div>
  );
}
