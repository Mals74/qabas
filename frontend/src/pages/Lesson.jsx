import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import Cards from "../components/Cards.jsx";
import { ErrorBox, Loading, PageHeader } from "../components/Common.jsx";
import { Bulb, Trash } from "../components/Icons.jsx";
import Player from "../components/Player.jsx";
import { AnySegment, TextSegment } from "../components/Segments.jsx";
import { SourceTag, TimePill } from "../components/Tags.jsx";

const TABS = [
  { key: "matn", label: "المتن" },
  { key: "sharh", label: "الشرح" },
  { key: "notes", label: "الملاحظات" },
];

function fmt(sec) {
  const s = Math.floor(sec || 0), h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}` : `${m}:${String(r).padStart(2, "0")}`;
}

export default function LessonPage() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const nav = useNavigate();
  const [lesson, setLesson] = useState(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState(params.get("t") ? "sharh" : "matn");
  const [focus, setFocus] = useState(params.get("t") ? Number(params.get("t")) : null);
  const [toast, setToast] = useState("");
  const player = useRef(null);

  // Load, and keep polling while the lesson is still being processed
  useEffect(() => {
    let timer;
    const load = () =>
      api.lesson(id).then((l) => {
        setLesson(l);
        if (l.status === "pending" || l.status === "processing") timer = setTimeout(load, 2500);
      }).catch((e) => setError(e.message));
    load();
    return () => clearTimeout(timer);
  }, [id]);

  // Deep link ?t=seconds: jump there once the player exists
  useEffect(() => {
    if (focus == null || !lesson) return;
    const t = setTimeout(() => player.current?.seek(focus), 1500);
    document.getElementById(`t-${Math.floor(focus)}`)?.scrollIntoView({ block: "center" });
    return () => clearTimeout(t);
  }, [lesson?.id]); // eslint-disable-line

  const seek = (seconds) => {
    setFocus(seconds);
    if (player.current?.hasMedia()) player.current.seek(seconds);
    else {
      setToast(`الدقيقة ${fmt(seconds)} — لا يوجد تسجيل مرفق بهذا الدرس التجريبي`);
      setTimeout(() => setToast(""), 2500);
    }
  };

  // Group segments: each matn line with the explanation that follows it
  const groups = useMemo(() => {
    if (!lesson) return [];
    const matns = lesson.segments.filter((s) => s.kind === "matn");
    return matns.map((m) => ({ matn: m, children: lesson.segments.filter((s) => s.matn_idx === m.idx) }));
  }, [lesson]);

  if (error) return <div className="page"><ErrorBox message={error} /></div>;
  if (!lesson) return <div className="page"><Loading /></div>;

  const busy = lesson.status === "pending" || lesson.status === "processing";

  return (
    <div className="page lesson-page">
      <PageHeader title={lesson.title} subtitle={lesson.sheikh} />
      <div className="meta-row">
        {lesson.book_title && <span>{lesson.book_title}</span>}
        {lesson.date && <span>{lesson.date}</span>}
        {lesson.status === "ready" && lesson.duration !== "0:00" && <span>{lesson.duration}</span>}
      </div>

      {lesson.is_sample && (
        <p className="notice small">درس تجريبي للعرض: النص مثال توضيحي وليس تفريغًا لشيخ بعينه. الآيات فيه مطابَقة فعليًا مع نص المصحف.</p>
      )}
      {lesson.mock_transcript && (
        <p className="notice small">الوضع التجريبي (دون مفتاح Gemini): التفريغ المعروض مثال ثابت وليس من هذا التسجيل.</p>
      )}

      <Player ref={player} youtubeId={lesson.youtube_id} mediaUrl={lesson.media_url} mediaKind={lesson.media_kind} />

      {busy && (
        <div className="processing">
          <div className="spinner" />
          <p>جارٍ تحويل الدرس إلى دفتر منظّم…</p>
          <p className="muted small">{lesson.progress}</p>
        </div>
      )}
      {lesson.status === "error" && (
        <div className="notice error">
          تعذّرت المعالجة: {lesson.error}
          <button className="btn-outline" onClick={() => api.reprocess(lesson.id).then(() => window.location.reload())}>إعادة المحاولة</button>
        </div>
      )}

      {lesson.status === "ready" && (
        <>
          <div className="segmented sticky">
            {TABS.map((t) => (
              <button key={t.key} className={tab === t.key ? "active" : ""} onClick={() => setTab(t.key)}>{t.label}</button>
            ))}
          </div>

          {tab === "matn" && (
            <div className="list">
              {groups.length === 0 && <p className="center muted">لم يُقرأ متن في هذا الدرس. راجع تبويب الشرح.</p>}
              {groups.map(({ matn, children }) => (
                <section key={matn.id} className="matn-group">
                  <TextSegment seg={matn} onSeek={seek} />
                  <div className="matn-children">
                    {children.map((c) => (
                      <div key={c.id} id={`t-${Math.floor(c.start)}`}><AnySegment seg={c} onSeek={seek} /></div>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          )}

          {tab === "sharh" && (
            <div className="list">
              {lesson.segments.map((s) => (
                <div key={s.id} id={`t-${Math.floor(s.start)}`}
                  className={focus != null && Math.abs(s.start - focus) < 1 ? "focused" : ""}>
                  <AnySegment seg={s} onSeek={seek} />
                </div>
              ))}
            </div>
          )}

          {tab === "notes" && (
            <Notes lesson={lesson} setLesson={setLesson} player={player} onSeek={seek} />
          )}

          <button className="btn-danger-link" onClick={() => {
            if (confirm("حذف هذا الدرس من دفترك؟")) api.deleteLesson(lesson.id).then(() => nav("/"));
          }}><Trash /> حذف الدرس</button>
        </>
      )}

      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}

function Notes({ lesson, setLesson, player, onSeek }) {
  const [text, setText] = useState("");

  async function add(e) {
    e.preventDefault();
    if (!text.trim()) return;
    const start = player.current?.currentTime?.() || 0;
    const note = await api.addNote(lesson.id, start, text);
    setLesson({ ...lesson, notes: [...lesson.notes, note].sort((a, b) => a.start - b.start) });
    setText("");
  }

  async function remove(noteId) {
    await api.deleteNote(noteId);
    setLesson({ ...lesson, notes: lesson.notes.filter((n) => n.id !== noteId) });
  }

  return (
    <div className="list">
      <section className="block summary">
        <div className="block-head">
          <span className="block-title"><Bulb /> فوائد الدرس</span>
          <SourceTag kind="ai" />
        </div>
        <ul>
          {lesson.summary.map((p, i) => (
            <li key={i}>
              <TimePill time={p.time} onClick={() => onSeek(p.start)} /> {p.point}
            </li>
          ))}
        </ul>
      </section>

      <section className="block">
        <div className="block-head"><span className="block-title">ملاحظاتي</span></div>
        <form className="note-form" onSubmit={add}>
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="اكتب ملاحظة عند الدقيقة الحالية…" />
          <button className="btn-primary small">حفظ</button>
        </form>
        {lesson.notes.length === 0 && <p className="muted small">لا توجد ملاحظات بعد.</p>}
        {lesson.notes.map((n) => (
          <div key={n.id} className="note">
            <TimePill time={n.time} onClick={() => onSeek(n.start)} />
            <p>{n.text}</p>
            <button className="icon-btn" onClick={() => remove(n.id)} aria-label="حذف"><Trash /></button>
          </div>
        ))}
      </section>

      <section>
        <h3 className="section-title">بطاقات المراجعة</h3>
        <Cards cards={lesson.cards} rejected={lesson.cards_rejected} onSeek={onSeek} />
      </section>
    </div>
  );
}
