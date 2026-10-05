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
          <li>يُفرَّغ كل درس بقراءتين مستقلتين؛ ما اختلفتا فيه يُستمع إليه مرة ثانية، وما بقي غير محسوم يُظلَّل «غير مؤكد» ولا يُخفى.</li>
          <li>الآيات تُعرض من نص المصحف المعتمد، لا من مخرجات النموذج.</li>
          <li>كلام الشيخ في الحديث يُعرض كما قاله؛ ونص الحديث الكامل يُعرض من كتاب الحديث نفسه مع رقمه ودرجته، ومعه رابط للتحقق في الدرر السنية. وإذا لم يُعثر عليه لا يُعرض نص.</li>
          <li>معاني الكلمات في الفهرس تُنقل من المعاجم كما هي مع اسم الكتاب والمادة، ولا يولّدها الذكاء الاصطناعي.</li>
          <li>لا تُعتمد بطاقة مراجعة إلا إذا وُجد نصها في كلام الشيخ.</li>
          <li>إذا لم يوجد الجواب في الدروس يصرّح قَبَس بذلك ولا يولّد جوابًا.</li>
          <li>لا يُفتي، ويحيل الأسئلة الشخصية إلى أهل العلم.</li>
          <li>الدفتر خاص بك، ولا يُفرَّغ كلام الحضور.</li>
        </ul>
      </section>

      <a className="result" href="/fahras">الفهرس: ابحث عن معنى أي كلمة في المعاجم العربية</a>

      <section className="block">
        <h3 className="block-title">المصادر والتقنيات</h3>
        <ul className="plain">
          <li>تفريغ الدروس: Gemini API</li>
          <li>نص القرآن وخطه: مصحف المدينة النبوية، الملف الرسمي لمجمع الملك فهد لطباعة المصحف الشريف (الإصدار 2.0)</li>
          <li>الأحاديث: الكتب التسعة (صحيح البخاري، صحيح مسلم، السنن الأربع، الموطأ، الأربعون النووية، الأحاديث القدسية)، مع رابط للتحقق في الدرر السنية</li>
          <li>الفهرس: النهاية في غريب الحديث، الفائق، الصحاح، القاموس المحيط، لسان العرب، تهذيب اللغة (من قاعدة جوامع الكلم)</li>
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
