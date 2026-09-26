// "Ask the lessons": answers come only from the sheikh's words, each with a citation.
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { PaperPlane } from "./PaperPlane.jsx";
import { SourceTag } from "./Tags.jsx";

const EXAMPLES = ["ما معنى التوحيد؟", "ما أنواع الشرك؟", "ما الحكمة من خلق الجن والإنس؟"];

export default function Ask({ bookId }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit(q) {
    const text = (q ?? question).trim();
    if (!text) return;
    setQuestion(text);
    setLoading(true);
    setError("");
    try {
      setAnswer(await api.ask(bookId, text));
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="ask">
      <form className="ask-box" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="اكتب سؤالك هنا…" />
        <button className="send" disabled={loading} aria-label="إرسال"><PaperPlane /></button>
      </form>

      {!answer && !loading && (
        <div className="examples">
          <p className="muted small">أمثلة على الأسئلة</p>
          {EXAMPLES.map((e) => (
            <button key={e} className="chip" onClick={() => submit(e)}>{e}</button>
          ))}
        </div>
      )}

      {loading && <p className="muted center">أبحث في كلام الشيخ…</p>}
      {error && <p className="notice error">{error}</p>}

      {answer && !loading && (
        <div className="answer-box">
          <h3>الإجابة</h3>
          <p className="answer">{answer.answer}</p>
          {answer.found ? (
            <>
              <SourceTag kind="ai">صياغة آلية من كلام الشيخ</SourceTag>
              <h4>المصدر</h4>
              {answer.citations.map((c, i) => (
                <div key={i} className="citation">
                  <blockquote className="evidence">«{c.quote}» <SourceTag kind="sheikh" /></blockquote>
                  <Link className="link" to={`/lessons/${c.lesson_id}?t=${Math.floor(c.start)}`}>
                    {c.lesson_title} · الدقيقة {c.time}
                  </Link>
                </div>
              ))}
            </>
          ) : (
            <p className="muted small">لا يجيب قَبَس من خارج الدروس المسجلة، ولا يُفتي في المسائل الشخصية.</p>
          )}
        </div>
      )}
    </div>
  );
}
