// الفهرس: meanings of words from classical dictionaries, looked up by root (no AI).
// - FahrasResults: the roots a word may come from, each with its dictionary entries and their books
// - FahrasSheet: the same in a bottom sheet, opened from a word the student tapped in the transcript
// - WordPicker: wraps the transcript; tapping a word offers «ابحث في الفهرس»
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { api } from "../api.js";

export function FahrasResults({ word }) {
  const [res, setRes] = useState(null);
  const [error, setError] = useState("");
  const [active, setActive] = useState(0);

  useEffect(() => {
    setRes(null); setError(""); setActive(0);
    if (word) api.fahras(word).then(setRes).catch((e) => setError(e.message));
  }, [word]);

  if (error) return <p className="muted">{error}</p>;
  if (!res) return <p className="muted">جارٍ البحث في المعاجم…</p>;
  if (!res.roots.length)
    return <p className="muted">لم يُعثر على جذر هذه الكلمة في المعاجم المتاحة.</p>;

  const root = res.roots[active];
  return (
    <div className="fahras">
      <p className="muted small">الجذور المحتملة لكلمة «{res.word}» — اختر الأنسب للسياق:</p>
      <div className="fahras-roots">
        {res.roots.map((r, i) => (
          <button key={r.key} className={i === active ? "active" : ""} onClick={() => setActive(i)}>{r.root}</button>
        ))}
      </div>
      <RootEntries root={root} />
      <p className="muted small fahras-source">المصدر: {res.source}</p>
    </div>
  );
}

// One root: an entry per dictionary, shortened, with «المدخل كاملًا» to load the whole entry
function RootEntries({ root }) {
  const [full, setFull] = useState({});
  useEffect(() => setFull({}), [root.key]);
  const more = (key) =>
    api.fahrasRoot(root.key).then((r) => setFull(Object.fromEntries(r.entries.map((e) => [e.key, e.text]))));

  if (!root.entries.length) return <p className="muted">لا توجد مداخل لهذا الجذر.</p>;
  return root.entries.map((e) => (
    <article key={e.key} className="fahras-entry">
      <h4>{e.book} <span className="muted small">— {e.author}، مادة ({e.entry})</span></h4>
      <p>{full[e.key] || e.text}</p>
      {e.more && !full[e.key] && <button className="link-btn" onClick={() => more(e.key)}>المدخل كاملًا</button>}
    </article>
  ));
}

export function FahrasSheet({ word, onClose }) {
  if (!word) return null;
  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div className="sheet" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="الفهرس">
        <div className="sheet-head">
          <h3>الفهرس: {word}</h3>
          <button className="link-btn" onClick={onClose}>إغلاق</button>
        </div>
        <FahrasResults word={word} />
      </div>
    </div>
  );
}

// The Arabic word under the tap, read from the text itself (works across marks and spans)
function wordAt(x, y) {
  let node, offset;
  if (document.caretRangeFromPoint) {
    const r = document.caretRangeFromPoint(x, y);
    if (!r) return "";
    node = r.startContainer; offset = r.startOffset;
  } else if (document.caretPositionFromPoint) {
    const p = document.caretPositionFromPoint(x, y);
    if (!p) return "";
    node = p.offsetNode; offset = p.offset;
  }
  if (!node || node.nodeType !== 3) return "";
  const text = node.textContent;
  const isLetter = (ch) => /[\u0621-\u065F\u0670-\u06D3\u06D6-\u06ED\u08D3-\u08FF]/.test(ch);   // letters and their harakat
  let a = offset, b = offset;
  while (a > 0 && isLetter(text[a - 1])) a--;
  while (b < text.length && isLetter(text[b])) b++;
  return text.slice(a, b);
}

export function WordPicker({ children }) {
  const [pick, setPick] = useState(null);     // {word, x, y} for the small «ابحث في الفهرس» button
  const [open, setOpen] = useState("");
  const box = useRef(null);

  const onClick = (e) => {
    if (e.target.closest(".fahras-pick")) return;
    if (e.target.closest("button, a, input, textarea, .unsure, .review")) return setPick(null);
    if (window.getSelection()?.toString()) return;          // selecting text, not tapping a word
    const word = wordAt(e.clientX, e.clientY);
    const letters = word.replace(/[^ء-ي]/g, "");
    if (letters.length < 2 || (pick && pick.word === word)) return setPick(null);   // a second tap closes it
    const rect = box.current.getBoundingClientRect();
    setPick({ word, x: e.clientX - rect.left, y: e.clientY - rect.top });
  };

  // Keep the popup inside the screen: centre it on the tap, then pull it back from the edges
  const popup = useRef(null);
  useLayoutEffect(() => {
    if (!pick || !popup.current || !box.current) return;
    const w = popup.current.offsetWidth, max = box.current.clientWidth - w - 8;
    popup.current.style.left = `${Math.max(8, Math.min(pick.x - w / 2, max))}px`;
  }, [pick]);

  // An accidental tap must be easy to undo: ✕, a tap anywhere else, Esc, scrolling, or 6 seconds all close it
  useEffect(() => {
    if (!pick) return;
    const outside = (e) => { if (!box.current?.contains(e.target)) setPick(null); };
    const esc = (e) => { if (e.key === "Escape") setPick(null); };
    const startY = window.scrollY;                  // close on a real scroll, not on a small layout shift
    const scrolled = () => { if (Math.abs(window.scrollY - startY) > 60) setPick(null); };
    const timer = setTimeout(() => setPick(null), 6000);
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", esc);
    window.addEventListener("scroll", scrolled, { passive: true });
    return () => {
      clearTimeout(timer);
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", esc);
      window.removeEventListener("scroll", scrolled);
    };
  }, [pick]);

  return (
    <div ref={box} className="word-picker" onClick={onClick}>
      {children}
      {pick && (
        <div ref={popup} className="fahras-pick" style={{ top: pick.y + 14, left: 8 }}>
          <button onClick={() => { setOpen(pick.word); setPick(null); }}>ابحث في الفهرس: «{pick.word}»</button>
          <button className="fahras-pick-x" onClick={() => setPick(null)} aria-label="إغلاق">✕</button>
        </div>
      )}
      <FahrasSheet word={open} onClose={() => setOpen("")} />
    </div>
  );
}
