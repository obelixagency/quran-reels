# 🎬 Quran Reels: أوتوميشن ريلز القرآن الكريم (مجاني بالكامل)

كل يوم السيستم بيعمل الخطوات دي لوحده:
1. يختار **آيات** مناسبة (من قائمة مختارة في `data/passages.json`) لا تتعدى **٣٠ ثانية**
2. يجيب **النص العثماني** و**التفسير الميسر** و**التلاوة آية بآية** و**توقيت نطق كل كلمة** من Quran.com (والاحتياطي alquran.cloud و everyayah.com)
3. يجيب **فيديو طبيعة** (شلالات، أنهار، جبال…) من Pexels ويشيل صوته الأصلي، يعني مفيش أي موسيقى
4. يركّب الريل بمقاس **1080×1920**: **الآية بتتكتب كلمة بكلمة في نفس لحظة نطق الشيخ ليها**، وتحتها **السورة ورقم الآية واسم الشيخ**، والخلفية بتتحرك بهدوء، وفي Fade في الأول والآخر
5. يكتب **كابشن** و**هاشتاجات** مناسبة لموضوع الآيات
6. ينشر على **فيسبوك + إنستجرام + تيك توك + يوتيوب (Shorts)**
7. يسجّل اللي اتنشر في `history.json` عشان الآيات والخلفيات ما تتكررش

> ✅ **مفيش ذكاء اصطناعي بيكتب آيات أو يقلّد أصوات.** النص والتلاوة والتفسير بييجوا كلهم من مصادر القرآن المعروفة زي ما هم، والأوتوميشن بيركّبهم وبس.

---

## 🧰 التكلفة: صفر

| الجزء | الأداة | مجاني؟ |
|---|---|---|
| التشغيل اليومي | GitHub Actions | ✅ (الريبو الخاص ليه ٢٠٠٠ دقيقة في الشهر، والريل الواحد بياخد حوالي ٣ دقايق) |
| نص الآيات والتفسير | alquran.cloud / Quran.com | ✅ |
| التلاوة | everyayah.com / Quran.com | ✅ |
| الخلفيات | Pexels API | ✅ (مجاني ومسموح تجاريًا من غير ما تذكر المصدر) |
| توقيت الكلمات | Quran.com (segments) | ✅ |
| فيسبوك وإنستجرام | Meta Graph API الرسمي | ✅ |
| تيك توك | TikTok Content Posting API الرسمي | ✅ |
| يوتيوب | YouTube Data API v3 الرسمي | ✅ (لحد ٦ رفعات في اليوم مجانًا) |
| الخط | Amiri Quran | ✅ (رخصة OFL) |

---

## 🚀 الإعداد (مرة واحدة بس)

### ١) ارفع المشروع على GitHub
1. اعمل حساب على [github.com](https://github.com) لو معندكش
2. **New repository**، سمّيه `quran-reels` واختار **Private**
3. ارفع كل ملفات الفولدر ده (Add file ← Upload files، واسحب الملفات كلها بما فيها فولدر `.github`)

### ٢) مفتاح Pexels للخلفيات (دقيقتين)
1. سجّل على [pexels.com/api](https://www.pexels.com/api/) ← **Your API Key**
2. في GitHub: **Settings ← Secrets and variables ← Actions ← New repository secret**
   - الاسم: `PEXELS_API_KEY`، والقيمة: المفتاح

> 💡 لو عايز تضمن ١٠٠٪ إن الخلفية مناظر طبيعية بس ومفيهاش ناس، حمّل الفيديوهات اللي تعجبك بنفسك من Pexels وحطها في فولدر `backgrounds/` (فيه فيديو شلال جاهز كبداية). السيستم بيستخدم كل فيديو منهم مرة، ولما يخلصوا بيجيب من Pexels.

### ٣) فيسبوك وإنستجرام
**المطلوب قبل ما تبدأ:** حساب إنستجرام يكون **Business** أو **Creator** ومربوط بصفحة الفيسبوك (من إعدادات الصفحة ← Linked accounts ← Instagram).

1. ادخل [developers.facebook.com](https://developers.facebook.com) ← **My Apps ← Create App** ← اختار نوع **Business**
2. من إعدادات التطبيق (App settings ← Basic) انسخ **App ID** و**App Secret**
3. افتح [Graph API Explorer](https://developers.facebook.com/tools/explorer/):
   - اختار تطبيقك
   - **Add permissions**: `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, `business_management`, `instagram_basic`, `instagram_content_publish`
   - دوس **Generate Access Token**، ووافق واختار الصفحة وحساب الإنستجرام
   - انسخ التوكن
4. على جهازك (لازم يكون عليه Python):
   ```bash
   pip install requests
   python tools/setup_meta.py APP_ID APP_SECRET التوكن_اللي_نسخته
   ```
5. هيطلعلك ٣ قيم، ضيفهم كـ Secrets في GitHub:
   - `FB_PAGE_ID`
   - `FB_PAGE_TOKEN` (توكن الصفحة ده **مش بينتهي**)
   - `IG_USER_ID`

> التطبيق وهو في وضع **Development** بيقدر ينشر على الصفحات والحسابات اللي انت أدمن عليها، وده كفاية لصفحتك.

### ٤) تيك توك
1. ادخل [developers.tiktok.com](https://developers.tiktok.com) ← **Manage apps ← Connect an app**
2. ضيف المنتجات دي: **Login Kit** و**Content Posting API** (وفعّل **Direct Post** لو عايز النشر المباشر)
3. في Login Kit حط **Redirect URI** يكون أي رابط https بتاعك (مثلًا صفحة GitHub Pages)
4. انسخ **Client key** و**Client secret**، وشغّل:
   ```bash
   python tools/setup_tiktok.py CLIENT_KEY CLIENT_SECRET REDIRECT_URI
   ```
5. ضيف الـ Secrets دي في GitHub: `TIKTOK_CLIENT_KEY` و`TIKTOK_CLIENT_SECRET` و`TIKTOK_REFRESH_TOKEN`

**⚠️ ملاحظة مهمة عن تيك توك:**
- أي تطبيق جديد، TikTok مش بيسمحله ينشر **عام** غير لما يعدّي مراجعة (Audit).
- عشان كده الإعداد الافتراضي هو `"mode": "draft"`: الريل بيوصل لتطبيق تيك توك عندك كـ**مسودة/إشعار**، وانت تفتحه وتلزق الكابشن (موجود في ملف `caption_tiktok.txt` في صفحة التشغيل على GitHub) وتدوس نشر. الموضوع بياخد ١٠ ثواني.
- قدّم على الـ Audit من صفحة التطبيق. أول ما يتقبل، غيّر في `config.json`:
  ```json
  "tiktok": {"enabled": true, "hashtags": 6, "mode": "direct", "privacy_level": "PUBLIC_TO_EVERYONE"}
  ```
  وساعتها النشر هيبقى أوتوماتيك بالكامل.
- (اختياري) التوكن بتاع تيك توك بيتجدد لوحده. لو عايز السيستم يحدّثه تلقائيًا، اعمل GitHub Personal Access Token بصلاحية Secrets وحطه في Secret باسم `GH_PAT`.

### ٥) يوتيوب (Shorts على قناتك)
1. ادخل [console.cloud.google.com](https://console.cloud.google.com) واعمل **مشروع جديد**
2. **APIs & Services ← Library**، ودوّر على **YouTube Data API v3** وفعّلها (Enable)
3. **OAuth consent screen**: اختار **External**، واكتب اسم التطبيق وإيميلك
   - في **Audience** دوس **Publish app** وخليه **In production**، عشان التوكن ما ينتهيش بعد ٧ أيام. هيقولك إن التطبيق مش متحقق منه، وده عادي لأنك انت بس اللي هتستخدمه
4. **Credentials ← Create credentials ← OAuth client ID**، ونوعه **Desktop app**. انسخ **Client ID** و**Client secret**
5. على جهازك شغّل:
   ```bash
   python tools/setup_youtube.py CLIENT_ID CLIENT_SECRET
   ```
   هيفتحلك المتصفح: سجّل دخول بحساب جوجل، و**اختار القناة اللي عايز تنشر عليها**، ووافق (لو ظهرت رسالة "Google hasn't verified this app" دوس Advanced ← Continue)
6. ضيف الـ Secrets دي في GitHub: `YT_CLIENT_ID` و`YT_CLIENT_SECRET` و`YT_REFRESH_TOKEN` و`YT_CHANNEL_ID`. الأخير بيضمن إن النشر يروح للقناة الصح بس

**⚠️ ملاحظة مهمة عن يوتيوب:** مشاريع Google Cloud الجديدة، يوتيوب بيخلي الفيديوهات اللي بترفعها **خاص (Private)** لحد ما تعدّي مراجعة مجانية (YouTube API Audit). قدّم عليها من [الفورم ده](https://support.google.com/youtube/contact/yt_api_form). لحد ما يتقبل، تقدر تفتح YouTube Studio وتخلي الفيديو **عام** بضغطة واحدة.

### ٦) جرّب
**Actions ← Quran Reel – daily ← Run workflow**
- لو خليت `publish = false` هيولّد الريل بس من غير نشر. تقدر تنزّله من صفحة التشغيل (Artifacts) وتشوفه
- لو خليت `publish = true` هيولّد وينشر

بعد كده الريل هيتنشر **كل يوم الساعة ٧ مساءً بتوقيت القاهرة** لوحده.

---

## ⚙️ التحكم (config.json والملفات اللي في data/)

| عايز تغيّر إيه؟ | فين؟ |
|---|---|
| ميعاد النشر أو عدد الريلز في اليوم | `.github/workflows/daily-reel.yml` ← سطر `cron` |
| المدة القصوى للريل | `config.json` ← `max_seconds` |
| طريقة ظهور الآية | `config.json` ← `text_style`: `"write"` بتتكتب كلمة بكلمة مع التلاوة (الافتراضي)، أو `"highlight"` الآية كلها باهتة والكلمة اللي بتتقري بتنوّر دهبي، أو `"static"` الآية كلها مرة واحدة |
| درجة تغميق الخلفية | `config.json` ← `background_darken` (من 0 لـ 1) |
| المشايخ | `data/reciters.json` ← خلّي `enabled: true` للشيخ اللي عايزه |
| الآيات المختارة | `data/passages.json` (سورة، من آية، إلى آية، موضوع) |
| الجمل الافتتاحية والهاشتاجات لكل موضوع | `data/themes.json` |
| عدد الهاشتاجات لكل منصة | `config.json` ← `platforms` (إنستجرام حاليًا بيسمح بـ ٥ بس) |
| نوع مشاهد الخلفية | `config.json` ← `pexels_queries` |
| اسم الصفحة كعلامة مائية | `config.json` ← `watermark` |
| إيقاف منصة معينة | `config.json` ← `"enabled": false` |
| خصوصية فيديوهات يوتيوب | `config.json` ← `youtube.privacy`: `public` أو `unlisted` أو `private` |
| آيات عشوائية من القرآن كله بدل القائمة | `config.json` ← `"selection_mode": "random"` |

**المشايخ المفعّلين حاليًا:** الحصري، المنشاوي، عبد الباسط (مرتّل)، الطبلاوي، وبيتبدّلوا كل ريل. دول من أكتر التسجيلات انتشارًا وتداولًا. في مشايخ تانيين موجودين في الملف (العفاسي، السديس، الشريم، المعيقلي) بس مقفولين، لأن تسجيلات بعضهم عليها حقوق من شركات إنتاج وممكن فيسبوك يعلّم عليها. فعّلهم على مسؤوليتك.

---

## 📝 شكل الكابشن

```
آيات تريح قلبك وتهدّي أعصابك

﴿ ٱلَّذِينَ ءَامَنُواْ وَتَطۡمَئِنُّ قُلُوبُهُم بِذِكۡرِ ٱللَّهِۗ ... (٢٨) ... (٢٩) ﴾

📖 سورة الرعد | الآيات ٢٨ – ٢٩
🎙️ بصوت الشيخ محمد صديق المنشاوي

💡 التفسير الميسر:
(نص التفسير من المصدر)

شاركها… لعلها تكون صدقة جارية لك 🤍

#سورة_الرعد #طمأنينة #المنشاوي #قرآن_كريم #ذكر_الله
```

الهاشتاجات بتتختار بالترتيب ده: **السورة**، بعدها **موضوع الآيات** (من القائمة، ومن كلمات في نص الآيات زي الصبر، الدعاء، التوكل، الاستغفار، الجنة…)، بعدها **الشيخ**، وفي الآخر هاشتاجات عامة.

---

## 🖥️ التشغيل على جهازك (اختياري)
```bash
# محتاج ffmpeg و Python 3.10 أو أحدث
pip install -r requirements.txt
python -m src.main                                   # يولّد ريل في out/ من غير نشر
python -m src.main --passage raad-28 --reciter husary
python -m src.main --publish                         # يولّد وينشر
```

## 🛟 مشاكل شائعة
- **Instagram error "media type"**: اتأكد إن الحساب Business/Creator ومربوط بالصفحة
- **Facebook error 200 / permissions**: اعمل التوكن تاني بكل الصلاحيات اللي في الخطوة ٣
- **الخلفية طلعت متدرجة (مش طبيعة)**: يبقى `PEXELS_API_KEY` مش متضاف
- **تيك توك access_token_invalid**: شغّل `setup_tiktok.py` تاني وحدّث `TIKTOK_REFRESH_TOKEN`
- **الـ workflow وقف لوحده**: GitHub بيوقف الجدولة لو الريبو فضل ٦٠ يوم من غير أي نشاط. السيستم بيعمل commit لـ `history.json` كل يوم، فده مش المفروض يحصل

## 📚 المصادر والرخص
- النص العثماني: [Tanzil.net](https://tanzil.net) (عبر [alquran.cloud](https://alquran.cloud)) و[Quran.com](https://quran.com)
- التفسير الميسر: مجمع الملك فهد (عبر alquran.cloud)
- التلاوات وتوقيت الكلمات: [Quran.com](https://quran.com) و[EveryAyah.com](https://everyayah.com)
- الخطوط: Amiri / Amiri Quran، رخصة SIL OFL (`assets/fonts/OFL.txt`)
- الخلفيات: [Pexels License](https://www.pexels.com/license/)
