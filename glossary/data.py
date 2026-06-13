# -*- coding: utf-8 -*-
"""Odoo glossary content — Arabic-first, data-driven (growth plan Phase 6).

Content is stored per-language IN this module (not in .po catalogues):
the plan explicitly calls for a data-driven glossary, the entries are long
editorial text, and Arabic is the PRIMARY content, not a translation of
English. Each term carries 'ar' and 'en' for every text field; Spanish
falls back to English at the view layer (documented MVP decision —
matching how DB-driven content already falls back on this site).

Field guide per term:
- slug          URL key, kebab-case, stable
- category      key into CATEGORY ORDER/labels (labels live in views, .po)
- term          the technical term itself (usually Latin, kept LTR)
- title         per-language display title
- definition    2–3 sentences, plain language
- example       one concrete situation
- why           why it matters for a business/admin
- mistake       the common mistake people make
- related       list of other slugs (validated by tests)
- cta           'xray' | 'rescue' | '' — which tool the term naturally leads to
"""

CATEGORY_ORDER = [
    'studio', 'automation', 'orm', 'views', 'core', 'accounting',
    'sales', 'inventory', 'migration', 'hosting', 'security', 'integration',
]

TERMS = [
    # ── Odoo Studio ──────────────────────────────────────────────────────────
    {
        'slug': 'odoo-studio', 'category': 'studio', 'term': 'Odoo Studio',
        'title': {'ar': 'Odoo Studio (ستوديو أودو)', 'en': 'Odoo Studio'},
        'definition': {
            'ar': 'أداة في نسخة Odoo Enterprise تتيح تعديل النظام بالسحب والإفلات دون كتابة كود: إضافة حقول، وتعديل شاشات، وإنشاء نماذج وأتمتات جديدة. كل ما تبنيه بها يُخزَّن داخل قاعدة البيانات نفسها وليس في وحدة برمجية.',
            'en': 'An Odoo Enterprise tool for customizing the system by drag-and-drop without writing code: adding fields, changing screens, creating new models and automations. Everything it builds is stored inside the database itself, not in a code module.',
        },
        'example': {
            'ar': 'مدير مبيعات يضيف حقل "نسبة الهامش" إلى نموذج عرض السعر في خمس دقائق عبر Studio بدل انتظار مطوّر.',
            'en': 'A sales manager adds a "margin %" field to the quotation form in five minutes via Studio instead of waiting for a developer.',
        },
        'why': {
            'ar': 'سرعة Studio مغرية، لكن كل تعديل يبقى حبيس قاعدة البيانات: لا يدخل نظام التحكم بالإصدارات، ولا تنقله سكربتات الترقية القياسية تلقائيًا.',
            'en': 'Studio is fast, but every change lives only in that database: it never enters version control, and standard upgrade scripts do not carry it over automatically.',
        },
        'mistake': {
            'ar': 'بناء عمليات جوهرية كاملة داخل Studio ثم اكتشاف عند الترقية أن أحدًا لا يعرف ماذا بُني ولا كيف يُعاد بناؤه.',
            'en': 'Building entire core processes in Studio, then discovering at upgrade time that nobody knows what was built or how to rebuild it.',
        },
        'related': ['custom-field', 'automated-action', 'studio-view'],
        'cta': 'xray',
    },
    {
        'slug': 'custom-field', 'category': 'studio', 'term': 'x_studio field',
        'title': {'ar': 'حقل مخصص (x_studio)', 'en': 'Custom field (x_studio)'},
        'definition': {
            'ar': 'حقل يضيفه المستخدم إلى نموذج موجود عبر Studio أو إعدادات المطوّر. تبدأ أسماء حقول Studio بالبادئة x_studio_ وتُخزَّن تعريفاتها في قاعدة البيانات فقط.',
            'en': 'A field a user adds to an existing model through Studio or developer settings. Studio field names start with the x_studio_ prefix and their definitions are stored only in the database.',
        },
        'example': {
            'ar': 'إضافة حقل x_studio_hs_code إلى المنتجات لتسجيل الرمز الجمركي لكل صنف.',
            'en': 'Adding x_studio_hs_code on products to record each item\'s customs code.',
        },
        'why': {
            'ar': 'بضعة حقول لا تضر، لكن عشرات الحقول على نماذج جوهرية مثل الفواتير وأوامر البيع ترفع تكلفة كل ترقية وتزيد احتمالات تعارض البيانات.',
            'en': 'A few fields are harmless, but dozens on core models like invoices and sales orders raise the cost of every upgrade and multiply data-conflict risks.',
        },
        'mistake': {
            'ar': 'تكرار الحقل نفسه بأسماء مختلفة لأن أحدًا لم يوثّق الحقول الموجودة أصلًا.',
            'en': 'Creating the same field twice under different names because nobody documented what already exists.',
        },
        'related': ['odoo-studio', 'computed-field', 'model'],
        'cta': 'xray',
    },
    {
        'slug': 'computed-field', 'category': 'studio', 'term': 'Computed field',
        'title': {'ar': 'حقل محسوب', 'en': 'Computed field'},
        'definition': {
            'ar': 'حقل لا يُدخل المستخدم قيمته يدويًا بل تُحسب آليًا من حقول أخرى عبر كود بايثون. حين يُنشأ عبر Studio يُحفظ كود الحساب داخل قاعدة البيانات نفسها.',
            'en': 'A field whose value is not typed by the user but calculated automatically from other fields via Python code. When created through Studio, the calculation code is saved inside the database itself.',
        },
        'example': {
            'ar': 'حقل "إجمالي الوزن القابل للفوترة" يُحسب تلقائيًا من وزن الشحنة وأبعادها.',
            'en': 'A "chargeable weight" field calculated automatically from a shipment\'s weight and dimensions.',
        },
        'why': {
            'ar': 'هذا منطق عمل حقيقي يعيش خارج أي وحدة برمجية: لا اختبارات ولا مراجعة كود، وسكربتات الترقية لا تنقله — وهو من أوائل ما ينكسر بصمت بعد الترقيات.',
            'en': 'This is real business logic living outside any module: no tests, no code review, and upgrade scripts do not migrate it — one of the first things to break silently after upgrades.',
        },
        'mistake': {
            'ar': 'وضع معادلات تسعير حساسة في حقول محسوبة عبر Studio دون توثيق، ثم تغيّر النتائج بعد ترقية دون أن يلاحظ أحد إلا في نهاية الشهر.',
            'en': 'Putting sensitive pricing formulas in Studio computed fields without documentation, then results changing after an upgrade with nobody noticing until month-end.',
        },
        'related': ['custom-field', 'server-action'],
        'cta': 'xray',
    },
    {
        'slug': 'studio-view', 'category': 'studio', 'term': 'Studio view',
        'title': {'ar': 'واجهة معدّلة عبر Studio', 'en': 'Studio view'},
        'definition': {
            'ar': 'نسخة معدّلة من شاشة قياسية (نموذج إدخال، قائمة، كانبان…) أنشأها Studio لتغيير ترتيب الحقول أو إخفائها أو إضافة عناصر. تُسجَّل كواجهة "وارثة" فوق الواجهة الأصلية.',
            'en': 'A modified version of a standard screen (form, list, kanban…) created by Studio to reorder, hide or add elements. It is registered as a view "inheriting" the original one.',
        },
        'example': {
            'ar': 'إخفاء حقول الشحن من شاشة عرض السعر وإضافة تبويب "مستندات الجمارك" عبر Studio.',
            'en': 'Hiding shipping fields on the quotation form and adding a "Customs documents" tab via Studio.',
        },
        'why': {
            'ar': 'كل واجهة وارثة قد تتعارض مع تغييرات Odoo في الإصدار الجديد — وهي من أكثر أسباب أعطال ما بعد الترقية شيوعًا.',
            'en': 'Every inheriting view can conflict with what Odoo changes in the next version — one of the most common causes of post-upgrade breakage.',
        },
        'mistake': {
            'ar': 'تعديل الشاشة نفسها عدة مرات عبر أشخاص مختلفين حتى تتراكم طبقات وراثة لا يجرؤ أحد على لمسها.',
            'en': 'Editing the same screen repeatedly through different people until inheritance layers pile up that nobody dares touch.',
        },
        'related': ['view-inheritance', 'view', 'odoo-studio'],
        'cta': 'xray',
    },

    # ── Automation ───────────────────────────────────────────────────────────
    {
        'slug': 'automated-action', 'category': 'automation', 'term': 'Automated action',
        'title': {'ar': 'إجراء مؤتمت', 'en': 'Automated action'},
        'definition': {
            'ar': 'قاعدة "إذا حدث كذا فافعل كذا" تُنفَّذ تلقائيًا عند إنشاء سجل أو تعديله أو مرور وقت محدد: إرسال بريد، تحديث حقل، أو تشغيل كود. تُنشأ غالبًا من الإعدادات أو Studio وتُخزَّن في قاعدة البيانات.',
            'en': 'An "if this happens, do that" rule executed automatically when a record is created, updated or after a delay: send an email, update a field, or run code. Usually created from settings or Studio and stored in the database.',
        },
        'example': {
            'ar': 'عند تأكيد أمر بيع يتجاوز 50,000، يُرسل إشعار تلقائي إلى المدير المالي.',
            'en': 'When a sales order above 50,000 is confirmed, a notification is automatically sent to the CFO.',
        },
        'why': {
            'ar': 'الأتمتات سهلة الإنشاء وسهلة النسيان: بعد سنتين تجد عشرات القواعد تتفاعل فيما بينها دون توثيق، وأي تعديل بسيط قد يطلق سلسلة غير متوقعة.',
            'en': 'Automations are easy to create and easy to forget: two years later, dozens of rules interact with each other undocumented, and one small change can trigger an unexpected chain.',
        },
        'mistake': {
            'ar': 'أتمتة ترسل رسائل للعملاء بناء على شرط صار خاطئًا بعد تغيير في العمليات — ولا أحد يتذكر أنها موجودة.',
            'en': 'An automation emailing customers based on a condition that became wrong after a process change — and nobody remembers it exists.',
        },
        'related': ['server-action', 'ir-cron', 'odoo-studio'],
        'cta': 'xray',
    },
    {
        'slug': 'server-action', 'category': 'automation', 'term': 'Server action',
        'title': {'ar': 'إجراء خادم', 'en': 'Server action'},
        'definition': {
            'ar': 'إجراء يُنفَّذ على الخادم عند استدعائه يدويًا أو من أتمتة: تحديث سجلات، إنشاء مستندات، أو — في أخطر صوره — تنفيذ كود بايثون مكتوب داخل سجل في قاعدة البيانات.',
            'en': 'An action executed on the server when triggered manually or by an automation: updating records, creating documents, or — in its riskiest form — running Python code written inside a database record.',
        },
        'example': {
            'ar': 'زر "إعادة احتساب العمولات" في شاشة الفواتير ينفّذ إجراء خادم يكتب القيم في حقول مخصصة.',
            'en': 'A "recompute commissions" button on invoices runs a server action that writes values into custom fields.',
        },
        'why': {
            'ar': 'كود بايثون داخل قاعدة البيانات لا يراه نظام التحكم بالإصدارات ولا تغطيه اختبارات — وعند الترقية ينكسر بصمت لأن لا أداة قياسية تتحقق منه.',
            'en': 'Python code inside the database is invisible to version control and covered by no tests — at upgrade time it breaks silently because no standard tool validates it.',
        },
        'mistake': {
            'ar': 'ترك إجراءات كود كتبها شريك سابق دون معرفة ماذا تفعل، ثم تعديل حقل تعتمد عليه فتتعطل عملية كاملة.',
            'en': 'Keeping code actions written by a former partner without knowing what they do, then changing a field they depend on and breaking an entire process.',
        },
        'related': ['automated-action', 'computed-field'],
        'cta': 'xray',
    },
    {
        'slug': 'ir-cron', 'category': 'automation', 'term': 'ir.cron',
        'title': {'ar': 'مهمة مجدولة (ir.cron)', 'en': 'Scheduled action (ir.cron)'},
        'definition': {
            'ar': 'مهمة تعمل تلقائيًا وفق جدول زمني: كل ساعة، كل ليلة، كل أسبوع. يستخدمها Odoo نفسه (تحديث أسعار الصرف، إرسال البريد) ويمكن إنشاء مهام مخصصة.',
            'en': 'A task that runs automatically on a schedule: hourly, nightly, weekly. Odoo itself uses them (currency rates, mail queue) and custom ones can be created.',
        },
        'example': {
            'ar': 'مهمة ليلية تزامن المخزون مع متجر إلكتروني خارجي عند الساعة الثالثة فجرًا.',
            'en': 'A nightly job syncing stock with an external e-commerce site at 3 AM.',
        },
        'why': {
            'ar': 'المهمة المجدولة المتوقفة لا تصدر صوتًا: تتعطل المزامنة أو الفوترة الدورية ولا يكتشف أحد إلا بعد أيام حين تختل الأرقام.',
            'en': 'A stopped scheduled job makes no noise: syncing or recurring billing halts and nobody notices for days, until the numbers drift.',
        },
        'mistake': {
            'ar': 'تعطيل مهمة "مؤقتًا" أثناء تشخيص مشكلة ثم نسيانها معطلة نهائيًا.',
            'en': 'Disabling a job "temporarily" while debugging, then forgetting it disabled forever.',
        },
        'related': ['automated-action', 'server-action'],
        'cta': 'rescue',
    },

    # ── Models & data (ORM) ─────────────────────────────────────────────────
    {
        'slug': 'model', 'category': 'orm', 'term': 'Model',
        'title': {'ar': 'نموذج (Model)', 'en': 'Model'},
        'definition': {
            'ar': 'الوحدة الأساسية لتخزين البيانات في Odoo: كل نوع من السجلات (عميل، فاتورة، منتج، أمر بيع) هو نموذج له حقوله وقواعده، ويقابل جدولًا في قاعدة البيانات.',
            'en': 'The basic unit of data storage in Odoo: every record type (customer, invoice, product, sales order) is a model with its fields and rules, mapping to a database table.',
        },
        'example': {
            'ar': 'res.partner هو نموذج جهات الاتصال، وsale.order نموذج أوامر البيع.',
            'en': 'res.partner is the contacts model; sale.order is the sales orders model.',
        },
        'why': {
            'ar': 'فهم النماذج هو مفتاح فهم أي تخصيص: السؤال الأول دائمًا "على أي نموذج بُني هذا؟" — فالتعديل على نموذج جوهري أخطر بكثير من نموذج جديد منفصل.',
            'en': 'Understanding models is the key to understanding any customization: the first question is always "which model is this built on?" — changing a core model is far riskier than adding a separate new one.',
        },
        'mistake': {
            'ar': 'إنشاء نموذج مخصص جديد لشيء يملك Odoo نموذجًا قياسيًا له أصلًا.',
            'en': 'Creating a new custom model for something Odoo already has a standard model for.',
        },
        'related': ['orm', 'custom-field', 'external-id'],
        'cta': '',
    },
    {
        'slug': 'orm', 'category': 'orm', 'term': 'ORM',
        'title': {'ar': 'محرك ORM', 'en': 'ORM'},
        'definition': {
            'ar': 'الطبقة التي تترجم بين كود بايثون وقاعدة البيانات في Odoo: بدل كتابة SQL مباشرة، يتعامل الكود مع كائنات وسجلات، والمحرك يتولى القراءة والكتابة والصلاحيات والتحقق.',
            'en': 'The layer translating between Python code and the database in Odoo: instead of raw SQL, code works with objects and records while the ORM handles reads, writes, permissions and validation.',
        },
        'example': {
            'ar': 'سطر واحد مثل partner.invoice_ids يجلب كل فواتير العميل دون أي SQL.',
            'en': 'A single line like partner.invoice_ids fetches all of a customer\'s invoices without any SQL.',
        },
        'why': {
            'ar': 'الكود الذي يتجاوز الـ ORM ويكتب في قاعدة البيانات مباشرة يتخطى الصلاحيات والتحقق — اختصار خطير يكسر سلامة البيانات بصمت.',
            'en': 'Code that bypasses the ORM and writes straight to the database skips permissions and validation — a dangerous shortcut that silently corrupts data integrity.',
        },
        'mistake': {
            'ar': 'استيراد بيانات بسكربتات SQL مباشرة "لتوفير الوقت" ثم قضاء أسابيع في إصلاح سجلات بلا روابط سليمة.',
            'en': 'Importing data with direct SQL scripts "to save time", then spending weeks repairing records with broken relations.',
        },
        'related': ['model', 'xml-rpc'],
        'cta': '',
    },
    {
        'slug': 'external-id', 'category': 'orm', 'term': 'External ID',
        'title': {'ar': 'المعرّف الخارجي (External ID)', 'en': 'External ID'},
        'definition': {
            'ar': 'اسم فريد ثابت يُمنح للسجل (مثل base.main_company) تستخدمه الوحدات والاستيرادات للإشارة إلى السجل دون الاعتماد على رقمه الداخلي المتغيّر بين قواعد البيانات.',
            'en': 'A unique stable name given to a record (like base.main_company) that modules and imports use to reference it without relying on its internal numeric id, which differs across databases.',
        },
        'example': {
            'ar': 'عند استيراد ملف عملاء، عمود External ID يتيح إعادة الاستيراد لتحديث السجلات نفسها بدل تكرارها.',
            'en': 'When importing a customer file, the External ID column lets you re-import to update the same records instead of duplicating them.',
        },
        'why': {
            'ar': 'الاستيراد المتكرر دون معرّفات خارجية هو الطريق الأسرع لقاعدة بيانات مليئة بالتكرارات التي يستحيل تنظيفها لاحقًا.',
            'en': 'Repeated imports without external ids are the fastest road to a database full of duplicates that become impossible to clean later.',
        },
        'mistake': {
            'ar': 'حذف معرّفات خارجية تعتمد عليها وحدة مثبتة، فتفشل ترقيتها التالية بأخطاء غامضة.',
            'en': 'Deleting external ids an installed module depends on, making its next update fail with cryptic errors.',
        },
        'related': ['model', 'migration'],
        'cta': '',
    },
    {
        'slug': 'many2one', 'category': 'orm', 'term': 'Many2one',
        'title': {'ar': 'علاقة Many2one', 'en': 'Many2one'},
        'definition': {
            'ar': 'حقل علاقة يربط السجل بسجل واحد من نموذج آخر: الفاتورة لها عميل واحد، وأمر البيع له مندوب واحد. يظهر للمستخدم كقائمة اختيار.',
            'en': 'A relational field linking a record to ONE record of another model: an invoice has one customer, a sales order has one salesperson. Users see it as a dropdown.',
        },
        'example': {
            'ar': 'حقل "العميل" في الفاتورة هو Many2one نحو نموذج جهات الاتصال res.partner.',
            'en': 'The "Customer" field on an invoice is a Many2one to the contacts model res.partner.',
        },
        'why': {
            'ar': 'العلاقات هي ما يجعل التقارير ممكنة: حقل نصي حر اسمه "العميل" بدل علاقة سليمة يعني أرقام مبيعات لا يمكن تجميعها بثقة أبدًا.',
            'en': 'Relations are what make reporting possible: a free-text "customer" field instead of a proper relation means sales numbers that can never be aggregated reliably.',
        },
        'mistake': {
            'ar': 'إنشاء حقول نصية لأشياء يجب أن تكون علاقات، ثم محاولة "تنظيف" آلاف القيم المكتوبة بطرق مختلفة.',
            'en': 'Creating text fields for things that should be relations, then trying to "clean up" thousands of inconsistently typed values.',
        },
        'related': ['one2many', 'model'],
        'cta': '',
    },
    {
        'slug': 'one2many', 'category': 'orm', 'term': 'One2many',
        'title': {'ar': 'علاقة One2many', 'en': 'One2many'},
        'definition': {
            'ar': 'الوجه المقابل لعلاقة Many2one: من سجل الأب ترى كل السجلات المرتبطة به — من العميل ترى كل فواتيره، ومن أمر البيع كل بنوده.',
            'en': 'The mirror of a Many2one: from the parent record you see all records linked to it — from a customer all their invoices, from a sales order all its lines.',
        },
        'example': {
            'ar': 'بنود الفاتورة هي One2many: فاتورة واحدة تحتوي عدة أسطر منتجات.',
            'en': 'Invoice lines are a One2many: one invoice holds several product lines.',
        },
        'why': {
            'ar': 'فهم اتجاه العلاقة يحدد أين تُبنى الحقول والتقارير؛ الخلط بين الاتجاهين يُنتج تصميمات بيانات معقدة بلا داعٍ.',
            'en': 'Understanding the relation\'s direction decides where fields and reports get built; mixing the directions up produces needlessly convoluted data designs.',
        },
        'mistake': {
            'ar': 'بناء جداول وسيطة مخصصة لعلاقة كان يكفي فيها One2many قياسي.',
            'en': 'Building custom intermediate tables for what a standard One2many already covers.',
        },
        'related': ['many2one', 'model'],
        'cta': '',
    },

    # ── Views & XML ──────────────────────────────────────────────────────────
    {
        'slug': 'view', 'category': 'views', 'term': 'View',
        'title': {'ar': 'واجهة العرض (View)', 'en': 'View'},
        'definition': {
            'ar': 'تعريف بلغة XML يحدد كيف تُعرض بيانات نموذج ما للمستخدم: نموذج إدخال، قائمة، كانبان، تقويم، أو رسم بياني. النموذج الواحد قد تكون له عدة واجهات.',
            'en': 'An XML definition of how a model\'s data is shown to the user: form, list, kanban, calendar or graph. One model can have several views.',
        },
        'example': {
            'ar': 'شاشة أمر البيع التي تراها يوميًا هي واجهة form لنموذج sale.order.',
            'en': 'The sales order screen you use daily is the form view of sale.order.',
        },
        'why': {
            'ar': 'معظم "تخصيصات" Odoo التي يطلبها المستخدمون هي تعديلات واجهات — وكل تعديل يُسجَّل في مكان ما ويجب أن يُحمل عبر كل ترقية.',
            'en': 'Most Odoo "customizations" users ask for are view changes — and each one is recorded somewhere and must be carried through every upgrade.',
        },
        'mistake': {
            'ar': 'تعديل الواجهة الأصلية مباشرة بدل الوراثة، فتضيع التعديلات مع أول تحديث للوحدة.',
            'en': 'Editing the original view directly instead of inheriting, losing the changes on the next module update.',
        },
        'related': ['view-inheritance', 'studio-view'],
        'cta': '',
    },
    {
        'slug': 'view-inheritance', 'category': 'views', 'term': 'View inheritance',
        'title': {'ar': 'وراثة الواجهات', 'en': 'View inheritance'},
        'definition': {
            'ar': 'الطريقة القياسية لتعديل شاشة موجودة دون لمس أصلها: واجهة "وارثة" تحدد نقاط التعديل (أضف حقلًا هنا، أخفِ زرًا هناك) وتُطبَّق فوق الواجهة الأم.',
            'en': 'The standard way to modify an existing screen without touching the original: an "inheriting" view declares modification points (add a field here, hide a button there) applied on top of the parent view.',
        },
        'example': {
            'ar': 'وحدة مخصصة تضيف تبويب "بيانات الشحن" إلى شاشة أمر البيع عبر واجهة وارثة من واجهة Odoo القياسية.',
            'en': 'A custom module adds a "Shipping data" tab to the sales order screen via a view inheriting Odoo\'s standard one.',
        },
        'why': {
            'ar': 'كل واجهة وارثة تتزوج بنية الواجهة الأم؛ حين يغيّر Odoo تلك البنية في إصدار جديد، تتعارض الوراثات — لذلك إحصاؤها قبل الترقية ضروري.',
            'en': 'Every inheriting view marries the parent\'s structure; when Odoo changes that structure in a new release, inheritances conflict — counting them before an upgrade is essential.',
        },
        'mistake': {
            'ar': 'طبقات وراثة فوق وراثة من شركاء مختلفين عبر السنين حتى يصبح ترتيب التطبيق نفسه لغزًا.',
            'en': 'Inheritance layered on inheritance by different partners over the years until the application order itself becomes a puzzle.',
        },
        'related': ['view', 'studio-view', 'version-upgrade'],
        'cta': 'xray',
    },

    # ── Core concepts ────────────────────────────────────────────────────────
    {
        'slug': 'module', 'category': 'core', 'term': 'Module',
        'title': {'ar': 'وحدة (Module)', 'en': 'Module'},
        'definition': {
            'ar': 'حزمة كود مكتملة تضيف وظيفة إلى Odoo: نماذج وواجهات وقواعد وبيانات وترجمات في مجلد واحد قابل للتثبيت والترقية والنقل بين قواعد البيانات. تطبيقات Odoo نفسها (المبيعات، المحاسبة…) وحدات.',
            'en': 'A complete code package adding functionality to Odoo: models, views, rules, data and translations in one folder that can be installed, upgraded and moved between databases. Odoo\'s own apps (Sales, Accounting…) are modules.',
        },
        'example': {
            'ar': 'وحدة مخصصة باسم company_logistics تجمع كل تخصيصات الشحن لديك في مكان واحد مُدار بنظام التحكم بالإصدارات.',
            'en': 'A custom module named company_logistics gathering all your shipping customizations in one version-controlled place.',
        },
        'why': {
            'ar': 'الوحدة هي الشكل "الصحيح" للتخصيص: قابلة للاختبار والمراجعة والترقية — على عكس التعديلات الحبيسة في قاعدة البيانات.',
            'en': 'A module is the "right" shape for customization: testable, reviewable and upgradable — unlike changes trapped inside the database.',
        },
        'mistake': {
            'ar': 'تثبيت وحدات مجانية من مصادر غير موثوقة دون مراجعة، ثم اكتشاف أنها تمنع الترقية أو تفتح ثغرات.',
            'en': 'Installing free modules from untrusted sources without review, then finding they block upgrades or open security holes.',
        },
        'related': ['odoo-studio', 'version-upgrade'],
        'cta': 'xray',
    },
    {
        'slug': 'chatter', 'category': 'core', 'term': 'Chatter',
        'title': {'ar': 'سجل المحادثة (Chatter)', 'en': 'Chatter'},
        'definition': {
            'ar': 'الشريط أسفل أو بجانب معظم السجلات حيث تُسجَّل الرسائل والملاحظات وتغييرات الحالة تلقائيًا: تاريخ كامل لمن فعل ماذا ومتى على هذا السجل.',
            'en': 'The strip below or beside most records where messages, notes and status changes are logged automatically: a full history of who did what and when on that record.',
        },
        'example': {
            'ar': 'في فاتورة متنازع عليها، يُظهر الـ Chatter متى أُرسلت ومن عدّل المبلغ وماذا ردّ العميل.',
            'en': 'On a disputed invoice, the chatter shows when it was sent, who changed the amount and what the customer replied.',
        },
        'why': {
            'ar': 'الـ Chatter هو الذاكرة المؤسسية للنظام؛ الفرق التي تتراسل خارجه (بريد منفصل، واتساب) تفقد سياق القرارات عند أول مغادرة موظف.',
            'en': 'Chatter is the system\'s institutional memory; teams that discuss outside it (separate email, WhatsApp) lose decision context the moment an employee leaves.',
        },
        'mistake': {
            'ar': 'إيقاف تتبع الحقول المهمة "لتقليل الضجيج" ثم العجز عن معرفة من غيّر شروط الدفع.',
            'en': 'Turning off tracking on important fields "to reduce noise", then being unable to tell who changed the payment terms.',
        },
        'related': ['model'],
        'cta': 'rescue',
    },
    {
        'slug': 'sequence', 'category': 'core', 'term': 'Sequence (ir.sequence)',
        'title': {'ar': 'التسلسل الرقمي (Sequence)', 'en': 'Sequence (ir.sequence)'},
        'definition': {
            'ar': 'مولّد الأرقام التسلسلية للمستندات: أرقام الفواتير وأوامر البيع والتحويلات. يحدد الصيغة (بادئة، سنة، عدّاد) ويضمن عدم التكرار.',
            'en': 'The generator of document numbers: invoice, sales order and transfer references. It defines the format (prefix, year, counter) and guarantees uniqueness.',
        },
        'example': {
            'ar': 'صيغة INV/2026/00041 تأتي من تسلسل الفواتير بعدّاد يُعاد سنويًا.',
            'en': 'INV/2026/00041 comes from the invoice sequence with a yearly-reset counter.',
        },
        'why': {
            'ar': 'أرقام الفواتير في كثير من الدول التزام ضريبي: فجوات أو تكرارات في التسلسل تعني مشاكل في التدقيق لا مجرد إزعاج تقني.',
            'en': 'Invoice numbering is a tax obligation in many countries: gaps or duplicates in the sequence mean audit problems, not just technical annoyance.',
        },
        'mistake': {
            'ar': 'تعديل تسلسل الفواتير يدويًا في منتصف السنة المالية دون فهم أثره الضريبي.',
            'en': 'Manually editing the invoice sequence mid-fiscal-year without understanding the tax impact.',
        },
        'related': ['journal-entry'],
        'cta': '',
    },

    # ── Accounting ───────────────────────────────────────────────────────────
    {
        'slug': 'journal-entry', 'category': 'accounting', 'term': 'Journal entry',
        'title': {'ar': 'قيد اليومية', 'en': 'Journal entry'},
        'definition': {
            'ar': 'التسجيل المحاسبي الأساسي في Odoo (نموذج account.move): كل فاتورة ودفعة وتسوية تُنشئ قيدًا بأطراف مدينة ودائنة متوازنة في دفاتر اليومية.',
            'en': 'The fundamental accounting record in Odoo (the account.move model): every invoice, payment and adjustment creates an entry with balanced debit and credit lines in the journals.',
        },
        'example': {
            'ar': 'تأكيد فاتورة بيع يُنشئ قيدًا تلقائيًا: مدين على حساب العميل، دائن لإيرادات المبيعات والضريبة.',
            'en': 'Confirming a customer invoice automatically creates an entry: debit on receivables, credit on sales revenue and tax.',
        },
        'why': {
            'ar': 'حين "لا تتطابق التقارير"، يبدأ التشخيص دائمًا من القيود: هل أُنشئت آليًا كما يجب أم عُدّلت يدويًا خارج المسار؟',
            'en': 'When "the reports don\'t match", diagnosis always starts at the entries: were they generated properly, or hand-edited outside the flow?',
        },
        'mistake': {
            'ar': 'تصحيح الأرقام بقيود يدوية متكررة بدل إصلاح الإعداد الذي يولّد القيود الخاطئة.',
            'en': 'Fixing numbers with repeated manual entries instead of fixing the configuration that generates the wrong ones.',
        },
        'related': ['chart-of-accounts', 'sequence'],
        'cta': 'rescue',
    },
    {
        'slug': 'chart-of-accounts', 'category': 'accounting', 'term': 'Chart of accounts',
        'title': {'ar': 'شجرة الحسابات', 'en': 'Chart of accounts'},
        'definition': {
            'ar': 'القائمة المنظمة لكل الحسابات المحاسبية في الشركة: الأصول والخصوم والإيرادات والمصاريف. يثبّت Odoo شجرة محلية حسب الدولة ويُبنى عليها كل القيود.',
            'en': 'The structured list of all the company\'s accounts: assets, liabilities, income and expenses. Odoo installs a country-specific localization chart on which every entry is built.',
        },
        'example': {
            'ar': 'اختيار حزمة المحاسبة الإسبانية يثبّت شجرة الحسابات الإسبانية القياسية مع الضرائب المحلية.',
            'en': 'Choosing the Spanish accounting package installs the standard Spanish chart with local taxes.',
        },
        'why': {
            'ar': 'شجرة حسابات فوضوية تعني تقارير مالية لا يثق بها أحد؛ وتعديلها بعد سنوات من القيود مشروع كامل وليس نقرة زر.',
            'en': 'A messy chart of accounts means financial reports nobody trusts; restructuring it after years of entries is a full project, not a click.',
        },
        'mistake': {
            'ar': 'إنشاء حسابات جديدة عشوائيًا لكل حالة بدل الاتفاق على هيكل واضح منذ البداية.',
            'en': 'Randomly creating new accounts for every case instead of agreeing on a clear structure from day one.',
        },
        'related': ['journal-entry'],
        'cta': 'rescue',
    },

    # ── Sales & CRM ──────────────────────────────────────────────────────────
    {
        'slug': 'crm-lead', 'category': 'sales', 'term': 'CRM lead',
        'title': {'ar': 'العميل المحتمل (Lead)', 'en': 'CRM lead'},
        'definition': {
            'ar': 'سجل في تطبيق CRM يمثل اهتمامًا أوليًا: استفسار من الموقع، بطاقة من معرض، مكالمة واردة. بعد التأهيل يتحول إلى فرصة بيع تُتابع في مراحل البايبلاين.',
            'en': 'A CRM record representing initial interest: a website inquiry, a trade-show card, an inbound call. Once qualified it becomes an opportunity tracked through pipeline stages.',
        },
        'example': {
            'ar': 'نموذج "اتصل بنا" في موقعك يُنشئ Lead تلقائيًا في Odoo ويُسنده إلى مندوب.',
            'en': 'Your website\'s contact form automatically creates a lead in Odoo and assigns it to a salesperson.',
        },
        'why': {
            'ar': 'بدون مسار موحّد للعملاء المحتملين تتسرب الفرص في صناديق بريد فردية — وتقارير المبيعات المتوقعة تصبح تخمينًا.',
            'en': 'Without one funnel for leads, opportunities leak away in personal inboxes — and sales forecasts become guesswork.',
        },
        'mistake': {
            'ar': 'ترك كل مندوب يدير عملاءه في ملف إكسل خاص "لأنه أسرع"، ففقدان المندوب يعني فقدان السوق.',
            'en': 'Letting each salesperson manage leads in a private Excel "because it\'s faster" — losing the salesperson means losing the market.',
        },
        'related': ['sales-pipeline', 'chatter'],
        'cta': 'rescue',
    },
    {
        'slug': 'sales-pipeline', 'category': 'sales', 'term': 'Sales pipeline',
        'title': {'ar': 'خط أنابيب المبيعات (Pipeline)', 'en': 'Sales pipeline'},
        'definition': {
            'ar': 'عرض كانبان لفرص البيع موزعة على مراحل (جديد، مؤهل, عرض سعر، تفاوض، فوز/خسارة) مع قيمة متوقعة واحتمالية لكل فرصة.',
            'en': 'A kanban view of opportunities across stages (new, qualified, proposal, negotiation, won/lost) with an expected value and probability per deal.',
        },
        'example': {
            'ar': 'اجتماع المبيعات الأسبوعي يُدار مباشرة من شاشة البايبلاين: ما الذي تحرك؟ وما العالق ولماذا؟',
            'en': 'The weekly sales meeting runs straight from the pipeline screen: what moved, what is stuck and why?',
        },
        'why': {
            'ar': 'البايبلاين الصادق هو أداة التنبؤ المالي الأولى للإدارة؛ مراحل غير محدّثة تعني قرارات توظيف وشراء مبنية على وهم.',
            'en': 'An honest pipeline is management\'s first forecasting tool; stale stages mean hiring and purchasing decisions built on fiction.',
        },
        'mistake': {
            'ar': 'عشرون مرحلة مخصصة لا يفهم الفريق الفرق بينها — فيتوقف الجميع عن تحديثها.',
            'en': 'Twenty custom stages nobody can tell apart — so everyone stops updating them.',
        },
        'related': ['crm-lead'],
        'cta': 'rescue',
    },
    {
        'slug': 'pricelist', 'category': 'sales', 'term': 'Pricelist',
        'title': {'ar': 'قائمة الأسعار', 'en': 'Pricelist'},
        'definition': {
            'ar': 'آلية التسعير في Odoo: قواعد تحدد سعر المنتج حسب العميل أو الكمية أو العملة أو الفترة. يمكن أن تتسلسل القوائم وترث بعضها.',
            'en': 'Odoo\'s pricing engine: rules deciding a product\'s price by customer, quantity, currency or period. Pricelists can chain and inherit from each other.',
        },
        'example': {
            'ar': 'قائمة "موزعون" تمنح خصم 15% عن السعر العام، وقائمة "عقد سنوي" تثبّت أسعار أصناف محددة.',
            'en': 'A "Distributors" pricelist gives 15% off the public price; an "Annual contract" list pins prices on specific items.',
        },
        'why': {
            'ar': 'قوائم الأسعار المتشابكة من أكثر أماكن Odoo غموضًا: حين "يظهر سعر غريب" في عرض سعر، يبدأ تشخيص طويل في سلسلة القواعد.',
            'en': 'Chained pricelists are one of Odoo\'s most opaque corners: when "a weird price shows up" on a quote, a long rule-chain diagnosis begins.',
        },
        'mistake': {
            'ar': 'ترميم الأسعار يدويًا في كل عرض بدل إصلاح القاعدة الخاطئة — فيختلف السعر باختلاف من أنشأ العرض.',
            'en': 'Hand-fixing prices on every quote instead of fixing the broken rule — so prices vary by whoever made the quote.',
        },
        'related': ['sales-pipeline'],
        'cta': 'rescue',
    },

    # ── Inventory ────────────────────────────────────────────────────────────
    {
        'slug': 'stock-move', 'category': 'inventory', 'term': 'Stock move',
        'title': {'ar': 'حركة المخزون', 'en': 'Stock move'},
        'definition': {
            'ar': 'أصغر وحدة في مخزون Odoo: انتقال كمية من منتج من موقع إلى آخر — من المورد إلى المستودع، من المستودع إلى العميل، أو بين مواقع داخلية.',
            'en': 'The smallest unit in Odoo inventory: a quantity of a product moving from one location to another — supplier to warehouse, warehouse to customer, or between internal locations.',
        },
        'example': {
            'ar': 'تأكيد أمر تسليم يولّد حركات مخزون من رف التخزين إلى منطقة الشحن ثم إلى موقع العميل.',
            'en': 'Confirming a delivery order generates stock moves from the shelf to the packing zone and on to the customer location.',
        },
        'why': {
            'ar': 'كل رقم مخزون في التقارير هو مجموع حركات؛ فهمها هو الطريق الوحيد لتشخيص "النظام يقول 12 والرف يقول 9".',
            'en': 'Every stock figure in reports is a sum of moves; understanding them is the only way to diagnose "the system says 12 but the shelf says 9".',
        },
        'mistake': {
            'ar': 'تصحيح الكميات بجرد يدوي متكرر دون البحث عن سبب الانحراف في مسار الحركات.',
            'en': 'Repeated manual inventory adjustments without finding why the moves drift in the first place.',
        },
        'related': ['delivery-order'],
        'cta': 'rescue',
    },
    {
        'slug': 'delivery-order', 'category': 'inventory', 'term': 'Delivery order (picking)',
        'title': {'ar': 'أمر التسليم (Picking)', 'en': 'Delivery order (picking)'},
        'definition': {
            'ar': 'مستند العمليات الذي يجمع حركات مخزون متجهة معًا: تسليم لعميل، استلام من مورد، أو تحويل داخلي. يُعرف تقنيًا بنموذج stock.picking.',
            'en': 'The operations document grouping stock moves traveling together: a customer delivery, a supplier receipt or an internal transfer. Technically the stock.picking model.',
        },
        'example': {
            'ar': 'أمر بيع بثلاثة أصناف يولّد أمر تسليم واحدًا (WH/OUT/00123) يجهّزه المستودع دفعة واحدة.',
            'en': 'A sales order with three items generates one delivery order (WH/OUT/00123) the warehouse prepares in one go.',
        },
        'why': {
            'ar': 'أوامر التسليم العالقة في حالة "جاهز" منذ أسابيع علامة كلاسيكية على انفصال النظام عن الواقع التشغيلي.',
            'en': 'Delivery orders stuck "Ready" for weeks are a classic sign the system has detached from operational reality.',
        },
        'mistake': {
            'ar': 'الشحن الفعلي يحدث من الباب، والتأكيد في النظام يحدث "لاحقًا حين يتوفر وقت" — فتنهار دقة المخزون.',
            'en': 'Physical shipping happens at the dock while system validation happens "later when there\'s time" — and stock accuracy collapses.',
        },
        'related': ['stock-move'],
        'cta': 'rescue',
    },

    # ── Migration & upgrades ─────────────────────────────────────────────────
    {
        'slug': 'migration', 'category': 'migration', 'term': 'Migration',
        'title': {'ar': 'الترحيل (Migration)', 'en': 'Migration'},
        'definition': {
            'ar': 'نقل نظام Odoo ببياناته وتخصيصاته من بيئة إلى أخرى: من إصدار أقدم إلى أحدث، من خادم إلى آخر، أو من نظام مختلف إلى Odoo. يشمل البيانات والكود والإعدادات معًا.',
            'en': 'Moving an Odoo system with its data and customizations between environments: from an older version to a newer one, between servers, or from a different system into Odoo. It covers data, code and configuration together.',
        },
        'example': {
            'ar': 'ترحيل قاعدة Odoo 15 إلى Odoo 18: ترقية البيانات عبر ثلاث قفزات وإعادة بناء الوحدات المخصصة لكل إصدار.',
            'en': 'Migrating an Odoo 15 database to Odoo 18: upgrading data through three jumps and reworking custom modules for each version.',
        },
        'why': {
            'ar': 'تكلفة الترحيل لا يحددها حجم البيانات بل حجم التخصيصات غير الموثقة — وهذا قابل للقياس قبل التوقيع على أي عرض.',
            'en': 'Migration cost is driven not by data size but by undocumented customizations — and that is measurable before signing any proposal.',
        },
        'mistake': {
            'ar': 'الموافقة على عرض ترحيل بسعر ثابت دون أن يعرف أحد — ولا حتى المورد — كم تخصيصًا يجب نقله فعلًا.',
            'en': 'Accepting a fixed-price migration proposal when nobody — not even the vendor — knows how many customizations actually need carrying over.',
        },
        'related': ['version-upgrade', 'external-id', 'module'],
        'cta': 'xray',
    },
    {
        'slug': 'version-upgrade', 'category': 'migration', 'term': 'Version upgrade',
        'title': {'ar': 'ترقية الإصدار', 'en': 'Version upgrade'},
        'definition': {
            'ar': 'الانتقال من إصدار رئيسي من Odoo إلى أحدث (مثلًا 16 إلى 18). يصدر Odoo إصدارًا رئيسيًا كل أكتوبر ويصون عادة آخر ثلاثة إصدارات فقط.',
            'en': 'Moving from one major Odoo version to a newer one (e.g. 16 to 18). Odoo releases a major version every October and normally maintains only the last three.',
        },
        'example': {
            'ar': 'شركة على Odoo 16 تخطط القفز إلى 19 قبل خروج 16 من نافذة الصيانة.',
            'en': 'A company on Odoo 16 planning the jump to 19 before 16 leaves the maintenance window.',
        },
        'why': {
            'ar': 'كل إصدار تتخطاه يضاعف خطوات الترقية القادمة؛ والبقاء خارج نافذة الدعم يعني العمل بلا تصحيحات أمنية.',
            'en': 'Every version you skip multiplies the next upgrade\'s steps; staying outside the support window means running without security fixes.',
        },
        'mistake': {
            'ar': 'تأجيل الترقية سنويًا "لأن النظام يعمل" حتى تصبح القفزة أربع نسخ دفعة واحدة بميزانية صادمة.',
            'en': 'Postponing yearly "because it works" until the jump becomes four versions at once with a shocking budget.',
        },
        'related': ['migration', 'view-inheritance', 'module'],
        'cta': 'xray',
    },

    # ── Hosting ──────────────────────────────────────────────────────────────
    {
        'slug': 'odoo-sh', 'category': 'hosting', 'term': 'Odoo.sh',
        'title': {'ar': 'منصة Odoo.sh', 'en': 'Odoo.sh'},
        'definition': {
            'ar': 'منصة الاستضافة السحابية الرسمية للمشاريع المخصصة: تتيح تثبيت وحدات برمجية خاصة مع بيئات تطوير واختبار وإنتاج مربوطة بمستودع GitHub ونسخ احتياطية مُدارة.',
            'en': 'Odoo\'s official cloud platform for customized projects: it allows private code modules with development, staging and production environments wired to a GitHub repository and managed backups.',
        },
        'example': {
            'ar': 'فريق يطوّر وحدة جديدة في فرع staging على Odoo.sh ويجربها بنسخة من بيانات الإنتاج قبل الدمج.',
            'en': 'A team builds a new module on an Odoo.sh staging branch and tests it on a copy of production data before merging.',
        },
        'why': {
            'ar': 'يناسب من يريد كودًا مخصصًا دون إدارة خوادم؛ لكنه التزام باشتراك مستمر وبإيقاع إصدارات Odoo.',
            'en': 'Right for teams wanting custom code without server management; it also commits you to a subscription and Odoo\'s release rhythm.',
        },
        'mistake': {
            'ar': 'اختيار المنصة دون فريق يجيد Git، فتتحول بيئاتها القوية إلى مصدر ارتباك بدل أمان.',
            'en': 'Choosing the platform without Git-fluent people, turning its powerful environments into confusion instead of safety.',
        },
        'related': ['odoo-online', 'module'],
        'cta': '',
    },
    {
        'slug': 'odoo-online', 'category': 'hosting', 'term': 'Odoo Online',
        'title': {'ar': 'أودو أونلاين (SaaS)', 'en': 'Odoo Online (SaaS)'},
        'definition': {
            'ar': 'الاستضافة السحابية المشتركة من Odoo على نطاقات odoo.com: بلا إدارة خوادم وبترقيات تلقائية، مقابل قيد جوهري — لا يمكن تثبيت وحدات برمجية مخصصة، والتخصيص محصور في Studio والإعدادات.',
            'en': 'Odoo\'s shared cloud hosting on odoo.com domains: zero server management and automatic upgrades, with one core constraint — no custom code modules; customization is limited to Studio and configuration.',
        },
        'example': {
            'ar': 'شركة ناشئة تطلق المبيعات والفوترة على Odoo Online في أسبوع دون فريق تقني.',
            'en': 'A startup launches sales and invoicing on Odoo Online in a week with no technical team.',
        },
        'why': {
            'ar': 'بداية ممتازة للأعمال القياسية؛ لكن النمو فوق حدود Studio يعني قرار هجرة لاحقًا إلى Odoo.sh أو استضافة ذاتية — وتخصيصات Studio لا تنتقل وحدها.',
            'en': 'A great start for standard operations; outgrowing Studio\'s limits later means a move to Odoo.sh or self-hosting — and Studio customizations do not move by themselves.',
        },
        'mistake': {
            'ar': 'بناء عمليات معقدة بعشرات حلول Studio الالتفافية على Online بدل الاعتراف مبكرًا بالحاجة إلى كود حقيقي.',
            'en': 'Building complex processes through dozens of Studio workarounds on Online instead of admitting early that real code is needed.',
        },
        'related': ['odoo-sh', 'odoo-studio'],
        'cta': 'xray',
    },

    # ── Security & access ────────────────────────────────────────────────────
    {
        'slug': 'access-rights', 'category': 'security', 'term': 'Access rights',
        'title': {'ar': 'صلاحيات الوصول', 'en': 'Access rights'},
        'definition': {
            'ar': 'الطبقة الأولى من أمان Odoo: لكل مجموعة مستخدمين، ماذا يمكنها أن تفعل على كل نموذج — قراءة، إنشاء، تعديل، حذف. تُمنح عبر مجموعات مثل "مستخدم مبيعات" أو "مدير محاسبة".',
            'en': 'Odoo\'s first security layer: per user group, what it may do on each model — read, create, write, delete. Granted through groups like "Sales user" or "Accounting manager".',
        },
        'example': {
            'ar': 'موظف المستودع يرى أوامر التسليم لكنه لا يستطيع فتح الفواتير أو الرواتب.',
            'en': 'A warehouse worker sees delivery orders but cannot open invoices or payroll.',
        },
        'why': {
            'ar': 'منح الجميع صلاحيات "مدير" لإنهاء شكاوى الوصول هو القنبلة الموقوتة الأكثر شيوعًا في أنظمة Odoo المتعثرة.',
            'en': 'Giving everyone "manager" rights to silence access complaints is the most common time bomb in struggling Odoo systems.',
        },
        'mistake': {
            'ar': 'تشخيص كل خطأ صلاحيات بترقية المستخدم بدل فهم المجموعة الناقصة فعلًا.',
            'en': 'Diagnosing every permission error by promoting the user instead of finding the actually missing group.',
        },
        'related': ['record-rule'],
        'cta': 'rescue',
    },
    {
        'slug': 'record-rule', 'category': 'security', 'term': 'Record rule',
        'title': {'ar': 'قاعدة السجلات', 'en': 'Record rule'},
        'definition': {
            'ar': 'الطبقة الثانية من الأمان: بعد أن تسمح الصلاحيات بالوصول إلى نموذج، تحدد قواعد السجلات أي سجلات بعينها يراها المستخدم — مثل "كل مندوب يرى عملاءه فقط".',
            'en': 'The second security layer: once access rights allow a model, record rules decide WHICH records a user sees — like "each salesperson sees only their own customers".',
        },
        'example': {
            'ar': 'في شركة متعددة الفروع، قاعدة سجلات تجعل كل فرع يرى مستنداته فقط رغم اشتراك الجميع في نفس النظام.',
            'en': 'In a multi-branch company, a record rule lets each branch see only its own documents though all share one system.',
        },
        'why': {
            'ar': 'قاعدة سجلات مكتوبة بلا فهم قد تخفي بيانات عن الإدارة نفسها أو — أسوأ — تكشف بيانات حساسة بين الفروع.',
            'en': 'A record rule written without understanding can hide data from management itself or — worse — leak sensitive data across branches.',
        },
        'mistake': {
            'ar': 'نسخ قواعد من الإنترنت دون اختبار من حسابات مستخدمين حقيقية مختلفة.',
            'en': 'Copying rules from the internet without testing from real different user accounts.',
        },
        'related': ['access-rights'],
        'cta': 'rescue',
    },

    # ── Integration ──────────────────────────────────────────────────────────
    {
        'slug': 'xml-rpc', 'category': 'integration', 'term': 'XML-RPC',
        'title': {'ar': 'واجهة XML-RPC', 'en': 'XML-RPC'},
        'definition': {
            'ar': 'الواجهة البرمجية القياسية للتكامل مع Odoo من الخارج: أنظمة أخرى تقرأ السجلات وتكتبها عبرها بنفس قواعد الصلاحيات المطبقة على المستخدمين. أدوات Bidatia تستخدمها للقراءة فقط.',
            'en': 'Odoo\'s standard external API: other systems read and write records through it under the same permission rules as users. Bidatia tools use it strictly read-only.',
        },
        'example': {
            'ar': 'متجر إلكتروني خارجي ينشئ أوامر البيع في Odoo تلقائيًا عبر XML-RPC عند كل طلب جديد.',
            'en': 'An external web shop creates sales orders in Odoo automatically over XML-RPC for each new purchase.',
        },
        'why': {
            'ar': 'التكاملات شريان الحياة بين الأنظمة — وكل تكامل يجب التحقق منه عند كل ترقية لأنه يعتمد على حقول ونماذج قد تتغير.',
            'en': 'Integrations are the lifeline between systems — and every one must be re-verified at each upgrade because it depends on fields and models that may change.',
        },
        'mistake': {
            'ar': 'تشغيل تكامل بحساب مدير عام كامل الصلاحيات بدل مستخدم تكامل محدود — فيستطيع أي خلل خارجي العبث بكل شيء.',
            'en': 'Running an integration as a full administrator instead of a limited integration user — letting any external glitch tamper with everything.',
        },
        'related': ['api-key', 'orm'],
        'cta': 'xray',
    },
    {
        'slug': 'api-key', 'category': 'integration', 'term': 'API key',
        'title': {'ar': 'مفتاح API', 'en': 'API key'},
        'definition': {
            'ar': 'رمز سري يُنشأ من إعدادات حساب المستخدم في Odoo ويُستخدم بدل كلمة المرور في الاتصالات البرمجية. يحمل صلاحيات المستخدم الذي أنشأه نفسها ويمكن إلغاؤه في أي وقت.',
            'en': 'A secret token generated from a user\'s account settings in Odoo, used instead of the password for API connections. It carries the creating user\'s exact permissions and can be revoked anytime.',
        },
        'example': {
            'ar': 'إنشاء مفتاح API لمستخدم "قراءة فقط" لتشغيل فحص Studio X-Ray دون كشف كلمة مرور أحد.',
            'en': 'Creating an API key on a read-only user to run a Studio X-Ray scan without exposing anyone\'s password.',
        },
        'why': {
            'ar': 'المفاتيح تتيح وصولًا دائمًا بلا تحقق ثنائي؛ مفتاح منسي لموظف غادر هو باب خلفي مفتوح إلى بياناتك.',
            'en': 'Keys grant standing access without two-factor prompts; a forgotten key of a departed employee is an open back door to your data.',
        },
        'mistake': {
            'ar': 'مشاركة مفتاح واحد بين عدة أنظمة وأشخاص، فيستحيل إلغاؤه لاحقًا دون كسر كل شيء معًا.',
            'en': 'Sharing one key across several systems and people, making it impossible to revoke later without breaking everything at once.',
        },
        'related': ['xml-rpc', 'access-rights'],
        'cta': '',
    },
]

_BY_SLUG = {t['slug']: t for t in TERMS}


def get_term(slug):
    return _BY_SLUG.get(slug)


def terms_by_category():
    """Ordered {category: [terms]} for the index page."""
    grouped = {c: [] for c in CATEGORY_ORDER}
    for term in TERMS:
        grouped[term['category']].append(term)
    return {c: items for c, items in grouped.items() if items}


def localized(term, language):
    """Flatten a term's per-language fields for one language.
    Arabic and English are authored; anything else falls back to English."""
    lang = language if language in ('ar', 'en') else 'en'
    return {
        'slug': term['slug'],
        'category': term['category'],
        'term': term['term'],
        'cta': term['cta'],
        'title': term['title'][lang],
        'definition': term['definition'][lang],
        'example': term['example'][lang],
        'why': term['why'][lang],
        'mistake': term['mistake'][lang],
        'related': [
            {'slug': r, 'title': _BY_SLUG[r]['title'][lang]}
            for r in term['related'] if r in _BY_SLUG
        ],
    }
