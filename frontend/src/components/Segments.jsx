// Rendering of transcript segments: Quran, hadith, matn, sharh.
import { useState } from "react";
import { api } from "../api.js";
import { External, Play } from "./Icons.jsx";
import { SourceTag, TimePill } from "./Tags.jsx";

// A recited verse. When verified we show the Mushaf text, never the transcription.
export function QuranBlock({ seg, onSeek }) {
  const q = seg.quran;
  const verified = q?.verified;
  return (
    <div className="block quran">
      <div className="block-head">
        <span className="block-title">الآية</span>
        <TimePill time={seg.time} onClick={() => onSeek(seg.start)} />
      </div>
      {verified ? (
        <>
          <p className="ayah">﴿{q.text}﴾</p>
          <p className="ref">{q.ref}</p>
          {q.ambiguous && q.also_in?.length > 0 && (
            <p className="muted small">وردت هذه الكلمات أيضًا في: {q.also_in.join("، ")}</p>
          )}
          <SourceTag kind="verified">{q.source}</SourceTag>
        </>
      ) : (
        <>
          <p className="recited">{seg.text}</p>
          <SourceTag kind="warn">لم يُتحقق من الآية آليًا؛ راجعها في المصحف</SourceTag>
        </>
      )}
    </div>
  );
}

// A hadith the sheikh quoted (maybe partially). Full text only comes from Dorar.
export function HadithBlock({ seg, onSeek }) {
  const [data, setData] = useState(seg.hadith || null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  async function load() {
    setOpen(true);
    if (data) return;
    setLoading(true);
    try {
      setData(await api.takhrij(seg.id));
    } catch (e) {
      setData({ ok: false, results: [], message: e.message });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="block hadith">
      <div className="block-head">
        <span className="block-title">حديث ذكره الشيخ</span>
        <TimePill time={seg.time} onClick={() => onSeek(seg.start)} />
      </div>
      <p className="recited">«{seg.text}»</p>
      <SourceTag kind="sheikh" />
      {!open && (
        <button className="btn-outline" onClick={load}>تخريج الحديث كاملًا</button>
      )}
      {open && (
        <div className="takhrij">
          {loading && <p className="muted">جارٍ البحث في الدرر السنية…</p>}
          {data?.results?.map((h, i) => (
            <div key={i} className="takhrij-item">
              <p className="hadith-text">{h.text}</p>
              <ul className="hadith-info">
                {h.narrator && <li><b>الراوي:</b> {h.narrator}</li>}
                {h.muhaddith && <li><b>المحدّث:</b> {h.muhaddith}</li>}
                {h.source && <li><b>المصدر:</b> {h.source}{h.number ? ` (${h.number})` : ""}</li>}
                {h.grade && <li><b>خلاصة حكم المحدّث:</b> {h.grade}</li>}
              </ul>
              <SourceTag kind="verified">من الدرر السنية</SourceTag>
            </div>
          ))}
          {data && !loading && data.results?.length === 0 && <p className="notice">{data.message}</p>}
          {data?.search_url && (
            <a className="btn-outline" href={data.search_url} target="_blank" rel="noreferrer">
              <External /> افتح البحث في الدرر السنية
            </a>
          )}
        </div>
      )}
    </div>
  );
}

// Any other segment: matn line, sharh, opening, audience placeholder
export function TextSegment({ seg, onSeek }) {
  if (seg.kind === "audience")
    return <p className="audience">{seg.text}</p>;
  return (
    <div className={`seg seg-${seg.kind}`}>
      <div className="seg-side">
        <TimePill time={seg.time} onClick={() => onSeek(seg.start)} />
        <button className="play-btn" onClick={() => onSeek(seg.start)} aria-label="تشغيل من هنا"><Play /></button>
      </div>
      <div className="seg-body">
        {seg.kind === "matn" && <span className="kind-label">المتن</span>}
        <p>{seg.text}</p>
        <SourceTag kind="sheikh">{seg.kind === "matn" ? "من الكتاب" : "من كلام الشيخ"}</SourceTag>
      </div>
    </div>
  );
}

export function AnySegment({ seg, onSeek }) {
  if (seg.kind === "quran") return <QuranBlock seg={seg} onSeek={onSeek} />;
  if (seg.kind === "hadith") return <HadithBlock seg={seg} onSeek={onSeek} />;
  return <TextSegment seg={seg} onSeek={onSeek} />;
}
