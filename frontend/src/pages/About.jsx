import { useEffect, useState } from "react";
import { Logo, PageHeader } from "../components/Common.jsx";
import { SourceTag } from "../components/Tags.jsx";
import { api } from "../api.js";

export default function About() {
  const [status, setStatus] = useState(null);
  useEffect(() => { api.status().then(setStatus).catch(() => {}); }, []);

  return (
    <div className="page">
      <PageHeader title="عن قَبَس" back={false} />
      <Logo />

      <section className="block">
        <h3 className="block-title">المبدأ</h3>
        <p className="principle">الذكاء الاصطناعي يقترح، والمصدر الموثوق يؤكّد</p>
        <div className="tags-row">
          <SourceTag kind="verified" />
          <SourceTag kind="sheikh" />
          <SourceTag kind="ai" />
        </div>
      </section>

      <section className="block">
        <h3 className="block-title">الضوابط العلمية</h3>
        <ul className="plain">
          <li>الآيات تُعرض من نص المصحف المعتمد، لا من مخرجات النموذج.</li>
          <li>الأحاديث تُخرَّج من الدرر السنية؛ وإذا تعذّر ذلك لا يُعرض نص الحديث.</li>
          <li>لا تُعتمد بطاقة مراجعة إلا إذا وُجد نصها في كلام الشيخ.</li>
          <li>إذا لم يوجد الجواب في الدروس يصرّح قَبَس بذلك ولا يولّد جوابًا.</li>
          <li>لا يُفتي، ويحيل الأسئلة الشخصية إلى أهل العلم.</li>
          <li>الدفتر خاص بك، ولا يُفرَّغ كلام الحضور.</li>
        </ul>
      </section>

      <section className="block">
        <h3 className="block-title">المصادر والتقنيات</h3>
        <ul className="plain">
          <li>تفريغ الدروس: Gemini API</li>
          <li>نص القرآن: المصحف الشريف برسم مصحف المدينة</li>
          <li>تخريج الأحاديث: الدرر السنية (dorar.net)</li>
          <li>الخادم: Python و FastAPI، والواجهة: React</li>
        </ul>
        {status && (
          <p className="muted small">
            وضع التشغيل الحالي: {status.provider === "gemini" ? `Gemini (${status.model})` : "تجريبي دون مفتاح"}
          </p>
        )}
      </section>
    </div>
  );
}
