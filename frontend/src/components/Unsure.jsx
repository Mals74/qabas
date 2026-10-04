// «غير مؤكد»: words the two readings of the lesson disagreed on, and re-listening couldn't settle.
// They are shown highlighted inside the sheikh's words; tapping one lets the student listen to that
// moment and choose the right reading (or type what they heard). Nothing is hidden or silently guessed.
import { useState } from "react";
import { api } from "../api.js";
import { Play } from "./Icons.jsx";

function fmt(sec) {
  const s = Math.max(0, Math.floor(sec || 0)), m = Math.floor(s / 60), r = s % 60;
  return `${m}:${String(r).padStart(2, "0")}`;
}

// The segment text with its unsure spots highlighted and tappable
export function MarkedText({ seg, onSeek, onChange, className = "" }) {
  const [open, setOpen] = useState(null);           // id of the mark being reviewed
  const marks = seg.uncertain || [];
  if (!marks.length) return <p className={className}>{seg.text}</p>;

  // cut the text into plain pieces and marked pieces
  const pieces = [];
  let pos = 0;
  for (const m of marks) {
    if (m.start > pos) pieces.push({ text: seg.text.slice(pos, m.start) });
    pieces.push({ mark: m, text: seg.text.slice(m.start, m.end) });
    pos = m.end;
  }
  if (pos < seg.text.length) pieces.push({ text: seg.text.slice(pos) });
  const current = marks.find((m) => m.id === open);

  return (
    <>
      <p className={className}>
        {pieces.map((p, i) =>
          p.mark ? (
            <button key={i} className={`unsure${p.mark.negation ? " neg" : ""}${open === p.mark.id ? " active" : ""}${p.text ? "" : " gap"}`}
              onClick={() => setOpen(open === p.mark.id ? null : p.mark.id)}
              title="غير مؤكد: اضغط للمراجعة">
              {p.text || "؟"}
            </button>
          ) : (
            <span key={i}>{p.text}</span>
          )
        )}
      </p>
      {current && (
        <ReviewPanel seg={seg} mark={current} onSeek={onSeek}
          onDone={(updated) => { setOpen(null); onChange?.(updated); }} onClose={() => setOpen(null)} />
      )}
    </>
  );
}

function ReviewPanel({ seg, mark, onSeek, onDone, onClose }) {
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function choose(text) {
    setBusy(true);
    setError("");
    try {
      onDone(await api.resolve(seg.id, mark.id, text));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={`review${mark.negation ? " neg" : ""}`}>
      <div className="review-head">
        <span className="review-title">غير مؤكد</span>
        <button className="icon-btn small" onClick={onClose} aria-label="إغلاق">✕</button>
      </div>
      <p className="small">
        {mark.negation
          ? "اختلفت القراءتان هنا في أداة نفي، وهذا قد يقلب المعنى. استمع ثم اختر ما قاله الشيخ."
          : "اختلفت القراءتان هنا ولم يُحسم الموضع بالاستماع الآلي. استمع ثم اختر ما قاله الشيخ."}
      </p>
      <button className="btn-outline" onClick={() => onSeek(Math.max(0, mark.time - 3))}>
        <Play /> استمع من {fmt(mark.time - 3)}
      </button>
      <div className="options">
        {mark.options.map((o, i) => (
          <button key={i} className="option" disabled={busy} onClick={() => choose(o)}>
            {o ? `«${o}»` : "لم يُقل شيء هنا"}
          </button>
        ))}
      </div>
      <form className="note-form" onSubmit={(e) => { e.preventDefault(); if (typed.trim()) choose(typed); }}>
        <input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="أو اكتب ما سمعته…" />
        <button className="btn-primary small" disabled={busy || !typed.trim()}>حفظ</button>
      </form>
      {error && <p className="small error-text">{error}</p>}
    </div>
  );
}

// Banner at the top of a lesson: how the two-pass check went
export function QualityNote({ quality, segments, onRetry }) {
  if (!quality) return null;
  const twoPass = quality.passes === 2;
  const left = segments.reduce((n, s) => n + (s.uncertain?.length || 0), 0);
  const low = segments.some((s) => s.low_confidence);
  const failed = quality.summary_failed || quality.cards_failed;
  if (!twoPass && !quality.capped_minutes && !quality.backup_calls && !failed) return null;
  return (
    <div className="quality">
      {twoPass && (
        <>
          <p>
            فُرِّغ هذا الدرس بقراءتين مستقلتين. اختلفتا في {quality.disagreements} موضعًا،
            حُسم منها {quality.resolved} بالاستماع مرة ثانية.
          </p>
          {left > 0 ? (
            <p><b>{left}</b> {left === 1 ? "موضع بقي" : "مواضع بقيت"} «غير مؤكد» ومظللة في النص؛ اضغط عليها لمراجعتها.</p>
          ) : (
            <p>لا توجد مواضع غير مؤكدة.</p>
          )}
        </>
      )}
      {low && <p className="small">بعض أجزاء التسجيل غير واضحة الصوت؛ راجعها بالاستماع.</p>}
      {quality.capped_minutes > 0 && (
        <p className="small">في النسخة التجريبية يُفرَّغ أول {quality.capped_minutes} دقائق من التسجيل فقط.</p>
      )}
      {quality.backup_calls > 0 && (
        <p className="small">استُخدم نموذج احتياطي في {quality.backup_calls} من الطلبات لأن النموذج الأساسي كان مزدحمًا أو انتهى حده اليومي{quality.models_used ? ` (${Object.keys(quality.models_used).join("، ")})` : ""}؛ قد تزيد الأخطاء فراجع النص.</p>
      )}
      {failed && (
        <p className="small">
          تعذّر إعداد {quality.summary_failed ? "الملخص" : ""}{quality.summary_failed && quality.cards_failed ? " و" : ""}{quality.cards_failed ? "البطاقات" : ""} الآن (الخدمة مشغولة أو انتهى الحد اليومي).
          {onRetry && <> <button className="link-btn" onClick={onRetry}>أعد المحاولة</button></>}
        </p>
      )}
    </div>
  );
}
