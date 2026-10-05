// الفهرس page: look up any word in six classical dictionaries (by root, no AI)
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { PageHeader } from "../components/Common.jsx";
import { FahrasResults } from "../components/Fahras.jsx";
import { Search } from "../components/Icons.jsx";

const BOOKS = "النهاية في غريب الحديث والأثر، الفائق في غريب الحديث، الصحاح، القاموس المحيط، لسان العرب، تهذيب اللغة";

export default function FahrasPage() {
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get("w") || "");
  const word = params.get("w");

  return (
    <div className="page">
      <PageHeader title="الفهرس" subtitle="معاني الكلمات من المعاجم العربية" />
      <form className="search-box" onSubmit={(e) => { e.preventDefault(); if (q.trim()) setParams({ w: q.trim() }); }}>
        <Search size={20} />
        <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="اكتب كلمة، مثل: الغُرّة أو يستغفرون…" />
      </form>
      {word ? <FahrasResults word={word} /> : (
        <p className="muted small">
          يبحث قَبَس عن جذر الكلمة بقواعد الصرف (دون ذكاء اصطناعي)، ثم يعرض مادتها من: {BOOKS}. ويمكنك أيضًا الضغط على أي كلمة في تفريغ الدرس.
        </p>
      )}
    </div>
  );
}
