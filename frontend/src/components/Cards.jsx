// Review cards grouped by type. Each card shows the sheikh's exact words as evidence.
import { useState } from "react";
import { Link } from "react-router-dom";
import { Star } from "./Icons.jsx";
import { SourceTag } from "./Tags.jsx";

const KINDS = [
  { key: "masalah", label: "المسائل" },
  { key: "mustalah", label: "المصطلحات" },
  { key: "dalil", label: "الأدلة" },
];

export default function Cards({ cards, rejected = 0, onSeek }) {
  const [kind, setKind] = useState("masalah");
  const shown = cards.filter((c) => c.kind === kind);
  return (
    <div>
      <div className="segmented">
        {KINDS.map((k) => (
          <button key={k.key} className={kind === k.key ? "active" : ""} onClick={() => setKind(k.key)}>
            {k.label}
          </button>
        ))}
      </div>
      <p className="muted small count">{shown.length} بطاقة</p>
      {rejected > 0 && (
        <p className="notice small">
          استُبعدت {rejected} {rejected === 1 ? "بطاقة اقترحها" : "بطاقات اقترحها"} النموذج لعدم وجود نصها في كلام الشيخ.
        </p>
      )}
      {shown.length === 0 && <p className="center muted">لا توجد بطاقات من هذا النوع.</p>}
      <div className="list">
        {shown.map((c) => (
          <article key={c.id} className="card">
            <h3><span className="badge"><Star /></span>{c.question}</h3>
            <p className="answer">{c.answer}</p>
            <SourceTag kind="ai">صياغة آلية</SourceTag>
            <blockquote className="evidence">
              «{c.evidence_quote}»
              <SourceTag kind="sheikh" />
            </blockquote>
            <p className="ref-line muted small">
              المرجع:{" "}
              {onSeek ? (
                <button className="link" onClick={() => onSeek(c.evidence_start)}>الدقيقة {c.time}</button>
              ) : (
                <Link className="link" to={`/lessons/${c.lesson_id}?t=${Math.floor(c.evidence_start)}`}>
                  {c.lesson_title} · الدقيقة {c.time}
                </Link>
              )}
            </p>
          </article>
        ))}
      </div>
    </div>
  );
}
