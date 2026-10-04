# سجل المصادر والمكونات — قَبَس (Sources & components log)

Draft for Clause 9 of the challenge terms: every tool, model, service, data source and
open-source component, with its purpose and license. Fill in the dates column, check each
license yourself before submitting, and add anything you add later.

| # | المكوّن | النوع | المصدر | الغرض | الترخيص / السند | التاريخ |
|---|---|---|---|---|---|---|
| 1 | Gemini API (google-genai SDK) | نموذج وخدمة ذكاء اصطناعي خارجية | Google | تفريغ الدروس، الملخص، البطاقات، سؤال الدروس | شروط Gemini API من Google؛ SDK برخصة Apache-2.0 | |
| 2 | نص القرآن الكريم (الرسم العثماني) | بيانات | حزمة quran-json 3.1.2 (المصدر الأصلي: موسوعة القرآن الكريم quranenc.com) | مطابقة الآيات وعرضها بنص المصحف | CC BY-SA 4.0 (quran-json)؛ تُراجع شروط quranenc | |
| 3 | الدرر السنية (dorar.net) | رابط خارجي | dorar.net/hadith/search | رابط «تحقّق منه في الدرر السنية» تحت كل حديث (لا يستدعي التطبيقُ الموقعَ آليًا) | — | |
| 4 | YouTube IFrame Player API | خدمة خارجية | YouTube | تشغيل الدرس من الدقيقة المطلوبة دون تنزيل الفيديو | شروط خدمة YouTube API | |
| 5 | FastAPI, Uvicorn | مكتبات مفتوحة المصدر | PyPI | الخادم | MIT / BSD-3 | |
| 6 | SQLModel / SQLAlchemy | مكتبات مفتوحة المصدر | PyPI | قاعدة البيانات | MIT | |
| 7 | RapidFuzz | مكتبة مفتوحة المصدر | PyPI | المطابقة التقريبية للنصوص | MIT | |
| 8 | httpx, BeautifulSoup4 | مكتبات مفتوحة المصدر | PyPI | الاتصال بالدرر وقراءة النتائج | BSD-3 / MIT | |
| 9 | React, React Router, Vite | مكتبات مفتوحة المصدر | npm | الواجهة | MIT | |
| 10 | IBM Plex Sans Arabic, Readex Pro, Amiri Quran | خطوط | Fontsource (npm) | خطوط الواجهة والآيات | SIL Open Font License 1.1 | |
| 11 | الدرس التجريبي في التطبيق | بيانات اصطناعية | كتبها الفريق للعرض | بيانات اختبار (البند 9: لا بيانات حقيقية) | من إعداد الفريق | |
| 12 | تصاميم الواجهة الأولية | صور | (اذكروا الأداة المستخدمة، وإن كانت مولّدة بالذكاء الاصطناعي فصرّحوا بذلك) | العرض التقديمي | | |
| 13 | المساعدة البرمجية | أداة ذكاء اصطناعي | Claude (Anthropic) | المساعدة في كتابة الشفرة والعرض | شروط الخدمة | |
| 14 | Haystack (haystack-ai) | مكتبة مفتوحة المصدر | PyPI (deepset) | البحث النصي BM25 عن الحديث في كتب الحديث، وتقييم البحث | Apache-2.0 | |
| 15 | نصوص كتب الحديث التسعة: الصحيحان، والسنن الأربع، والموطأ، والأربعون النووية والقدسية (العربية) | بيانات | fawazahmed0/hadith-api (ara-bukhari, ara-muslim, ara-abudawud, ara-tirmidhi, ara-nasai, ara-ibnmajah, ara-malik, ara-nawawi, ara-qudsi) | البحث عن الحديث وعرض نصه بمرجعه وحكمه | Unlicense (يُراجع أصل النصوص قبل التسليم) | |
| 16 | Gemini Flash-Lite | نموذج ذكاء اصطناعي خارجي | Google | الملخص والبطاقات والأسئلة وفحص مطابقة الحديث، ونموذج احتياطي | شروط Gemini API من Google | |
| 17 | دروس صوتية ونصوص منشورة لاختبار الدقة (binbaz.org.sa، shkhudheir.com، archive.org، يوتيوب) | بيانات اختبار | مواقع المشايخ الرسمية | قياس دقة التفريغ فقط، ولم يُعد نشرها؛ ولا تُضمَّن في المستودع | تُراجع شروط كل موقع | |
| 18 | الدروس الجاهزة في `backend/data/seed` | بيانات | تفريغ آلي لدرس منشور | عرض التطبيق بدروس حقيقية | يُتأكد من إذن الشيخ أو ترخيص الدرس قبل النشر العام | |

