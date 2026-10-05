// Rendering of transcript segments: Quran, hadith, matn, sharh.
import { createContext, useContext, useEffect, useState } from "react";
import { api } from "../api.js";
import { External, Pause, Play } from "./Icons.jsx";
import { SourceTag, TimePill } from "./Tags.jsx";
import { MarkedText } from "./Unsure.jsx";

// Which segment's play button started the recording, and whether it is playing now (set by the lesson page)
export const Playback = createContext({ from: null, playing: false, toggle: null });

// Play from this segment; pressed again while it plays, it pauses (and then resumes)
function PlayButton({ start, onSeek }) {
  const pb = useContext(Playback);
  const mine = pb.from === start;
  const active = mine && pb.playing;
  return (
    <button className="play-btn" onClick={() => (pb.toggle ? pb.toggle(start) : onSeek(start))}
      aria-label={active ? "إيقاف مؤقت" : "تشغيل من هنا"}>
      {active ? <Pause /> : <Play />}
    </button>
  );
}

// Small notes shown under any segment
function SegmentFlags({ seg }) {
  return (
    <>
      {seg.low_confidence && <SourceTag kind="warn">الصوت غير واضح في هذا الجزء؛ راجعه بالاستماع</SourceTag>}
      {seg.corrected && <span className="tag tag-fixed">صحّحته أنت</span>}
    </>
  );
}

// A recited verse. When verified we show the Mushaf text, never the transcription.
export function QuranBlock({ seg, onSeek, onChange }) {
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
          {q.parts?.length ? (
            q.parts.map((p, i) => (
              <div key={i}>
                <p className="ayah">﴿{p.text}﴾</p>
                <p className="ref">{p.ref}</p>
              </div>
            ))
          ) : (
            <>
              <p className="ayah">﴿{q.text}﴾</p>
              <p className="ref">{q.ref}</p>
            </>
          )}
          {q.ambiguous && q.also_in?.length > 0 && (
            <p className="muted small">وردت هذه الكلمات أيضًا في: {q.also_in.join("، ")}</p>
          )}
          <SourceTag kind="verified">{q.source}</SourceTag>
        </>
      ) : (
        <>
          <MarkedText seg={seg} onSeek={onSeek} onChange={onChange} className="recited" />
          <SourceTag kind="warn">لم يُتحقق من الآية آليًا؛ راجعها في المصحف</SourceTag>
        </>
      )}
    </div>
  );
}

// How the full hadith was found, in words the student can judge
const HOW = {
  rule: { kind: "verified", text: "مطابقة نصية: وردت في هذا الحديث خمس كلمات متتالية أو أكثر من كلام الشيخ" },
  check: { kind: "ai", text: "وُجد بفحص آلي للمعنى بين أقرب الأحاديث؛ تحقّق منه قبل الاعتماد" },
  candidate: { kind: "warn", text: "مرشّح غير مؤكد" },
  variant: { kind: "verified", text: "رواية أخرى للحديث السابق: وُجد هذا اللفظ بعينه في الكتاب" },
};

// The same search on dorar.net, for the student to check by hand
function dorarLink(seg) {
  const q = seg.text.split(/\s+/).slice(0, 7).join(" ");
  return `https://dorar.net/hadith/search?q=${encodeURIComponent(q)}`;
}

// One full hadith, taken from the book itself, with its reference and grade. Long ones are folded.
function HadithResult({ h }) {
  const [more, setMore] = useState(false);
  const long = (h.text || "").length > 420;
  const how = HOW[h.method] || HOW.candidate;
  return (
    <div className="takhrij-item">
      <p className={`hadith-text${long && !more ? " folded" : ""}`}>{h.text}</p>
      {long && <button className="link-btn" onClick={() => setMore(!more)}>{more ? "أقل" : "الحديث كاملًا"}</button>}
      <ul className="hadith-info">
        {h.narrator && <li><b>الراوي:</b> {h.narrator}</li>}
        {h.muhaddith && <li><b>المحدّث:</b> {h.muhaddith}</li>}
        {h.source && <li><b>المصدر:</b> {h.source}{h.number ? ` (${h.number})` : ""}</li>}
        {h.grade && <li><b>الحكم:</b> {h.grade}</li>}
      </ul>
      <SourceTag kind={how.kind}>{how.text}</SourceTag>
    </div>
  );
}

// A hadith the sheikh quoted (maybe partially): his words stay exactly as he said them; below them, the full hadith
// from the hadith books with its reference and grade, and a link to check it on Dorar (الدرر السنية).
export function HadithBlock({ seg, onSeek, onChange }) {
  const [data, setData] = useState(seg.hadith || null);
  const [loading, setLoading] = useState(false);

  async function load() {
    if (data?.results?.length) return;
    setLoading(true);
    try {
      setData(await api.takhrij(seg.id));
    } catch (e) {
      setData({ ok: false, results: [], message: e.message, search_url: dorarLink(seg) });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!seg.hadith) load();          // look the hadith up as soon as the lesson opens
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seg.id]);

  return (
    <div className="block hadith">
      <div className="block-head">
        <span className="block-title">حديث ذكره الشيخ</span>
        <TimePill time={seg.time} onClick={() => onSeek(seg.start)} />
      </div>
      <MarkedText seg={seg} onSeek={onSeek} onChange={onChange} className="recited" />
      <SourceTag kind="sheikh">من كلام الشيخ كما قاله (لا يُستبدل بنص آخر)</SourceTag>
      <SegmentFlags seg={seg} />
      <div className="takhrij">
        {loading && <p className="muted">جارٍ البحث في كتب الحديث…</p>}
        {data?.results?.map((h, i) => <HadithResult key={i} h={h} />)}
        {data && !loading && data.message && <p className="notice small">{data.message}</p>}
        {!loading && (
          <a className="btn-outline" href={data?.search_url || dorarLink(seg)} target="_blank" rel="noreferrer">
            <External /> تحقّق منه في الدرر السنية
          </a>
        )}
      </div>
    </div>
  );
}

// Any other segment: matn line, sharh, opening, audience placeholder
export function TextSegment({ seg, onSeek, onChange }) {
  if (seg.kind === "audience")
    return <p className="audience">{seg.text}</p>;
  return (
    <div className={`seg seg-${seg.kind}`}>
      <div className="seg-side">
        <TimePill time={seg.time} onClick={() => onSeek(seg.start)} />
        <PlayButton start={seg.start} onSeek={onSeek} />
      </div>
      <div className="seg-body">
        {seg.kind === "matn" && <span className="kind-label">المتن</span>}
        <MarkedText seg={seg} onSeek={onSeek} onChange={onChange} />
        <SourceTag kind="sheikh">{seg.kind === "matn" ? "من الكتاب" : "من كلام الشيخ"}</SourceTag>
        <SegmentFlags seg={seg} />
      </div>
    </div>
  );
}

export function AnySegment({ seg, onSeek, onChange }) {
  if (seg.kind === "quran") return <QuranBlock seg={seg} onSeek={onSeek} onChange={onChange} />;
  if (seg.kind === "hadith") return <HadithBlock seg={seg} onSeek={onSeek} onChange={onChange} />;
  return <TextSegment seg={seg} onSeek={onSeek} onChange={onChange} />;
}
