from django.core.management.base import BaseCommand
from django.utils.text import slugify

from blog.models import BlogPost, CaseStudy
from services.models import Service, ServiceFAQ, ServiceFeature


def L(en, es, ar):
    """A localized value: English (source) + natural Spanish + natural Arabic."""
    return {'en': en, 'es': es, 'ar': ar}


# Translatable field names per model (so we can expand L() dicts into _en/_es/_ar).
SERVICE_TR = {'title', 'short_description', 'description', 'outcome', 'price_label', 'delivery_time', 'meta_description'}
CASE_TR = {'title', 'client_summary', 'challenge', 'approach', 'results', 'meta_description'}
POST_TR = {'title', 'excerpt', 'content', 'meta_description'}


SERVICES = [
    {
        'title': L(
            'Paid Odoo Consultation',
            'Consultoría técnica de Odoo',
            'استشارة Odoo التقنية'),
        'short_description': L(
            'A focused 45–60 minute technical session to get expert answers on your Odoo questions or problems.',
            'Una sesión técnica de 45–60 minutos para obtener respuestas expertas a tus dudas o problemas con Odoo.',
            'جلسة تقنية مركّزة من 45–60 دقيقة للحصول على إجابات خبيرة حول أسئلتك أو مشكلاتك في Odoo.'),
        'description': L(
            "Sometimes you don't need a full project — you need 45 focused minutes with someone who has "
            "actually solved this problem before. This paid consultation gives you direct access to a senior "
            "Odoo and Django consultant to discuss your situation, ask technical questions, and walk away with "
            "a clear sense of direction.\n"
            "It's ideal if you're evaluating an idea, stuck on a technical decision, choosing between approaches, "
            "or simply want a second, experienced opinion before committing budget or time.\n"
            "Sessions are paid in advance to keep them focused and valuable for both sides — no sales pitch, "
            "just a direct technical conversation.",

            "A veces no necesitas un proyecto completo, sino 45 minutos bien aprovechados con alguien que ya ha "
            "resuelto este tipo de problemas. Esta consultoría te da acceso directo a un consultor sénior de Odoo "
            "y Django para analizar tu situación, plantear tus dudas técnicas y salir con una dirección clara.\n"
            "Es ideal si estás valorando una idea, te has atascado en una decisión técnica, dudas entre varios "
            "enfoques o simplemente quieres una segunda opinión experta antes de invertir tiempo o presupuesto.\n"
            "Las sesiones se abonan por adelantado para que sean enfocadas y útiles para ambas partes: sin discurso "
            "comercial, solo una conversación técnica directa.",

            "أحيانًا لا تحتاج إلى مشروع كامل، بل إلى 45 دقيقة مركّزة مع شخص سبق أن حلّ هذا النوع من المشكلات. تمنحك "
            "هذه الاستشارة تواصلًا مباشرًا مع استشاري خبير في Odoo و Django لمناقشة وضعك، وطرح أسئلتك التقنية، "
            "والخروج برؤية واضحة للخطوات التالية.\n"
            "وهي مثالية إذا كنت تقيّم فكرة، أو توقّفت عند قرار تقني، أو تتردّد بين عدّة مقاربات، أو ترغب ببساطة في "
            "رأي خبير ثانٍ قبل تخصيص الوقت أو الميزانية.\n"
            "تُدفع الجلسات مسبقًا لتظلّ مركّزة ومفيدة للطرفين — بلا عروض بيعية، فقط حوار تقني مباشر."),
        'outcome': L(
            'Walk away with a clear answer, a recommended path forward, and next steps you can act on.',
            'Termina con una respuesta clara, una vía recomendada y unos próximos pasos que puedes poner en marcha.',
            'اختم الجلسة بإجابة واضحة، ومسار موصى به، وخطوات تالية قابلة للتنفيذ.'),
        'icon': 'consultation',
        'price_label': L('From €49', 'Desde 49 €', 'من 49 €'),
        'delivery_time': L('45–60 minutes, scheduled within days', '45–60 minutos, agendada en pocos días', '45–60 دقيقة، تُحجز خلال أيام'),
        'is_featured': False,
        'order': 1,
        'meta_description': L(
            'Book a paid 45-60 minute Odoo consultation with a senior technical consultant in Madrid. Get clear, expert answers to your ERP questions.',
            'Reserva una consultoría de Odoo de 45-60 minutos con un consultor técnico sénior en Madrid. Obtén respuestas claras y expertas sobre tu ERP.',
            'احجز استشارة Odoo مدفوعة من 45-60 دقيقة مع استشاري تقني خبير في مدريد، واحصل على إجابات واضحة لأسئلتك حول نظام ERP لديك.'),
        'features': [
            L('Direct conversation with a senior Odoo & Django consultant',
              'Conversación directa con un consultor sénior de Odoo y Django',
              'حوار مباشر مع استشاري خبير في Odoo و Django'),
            L('Focused on your specific question, system, or decision',
              'Centrada en tu pregunta, sistema o decisión concreta',
              'تركيز على سؤالك أو نظامك أو قرارك تحديدًا'),
            L('Practical recommendations you can act on immediately',
              'Recomendaciones prácticas que puedes aplicar de inmediato',
              'توصيات عملية يمكنك تطبيقها فورًا'),
            L('Optional written summary of key points after the call',
              'Resumen escrito opcional de los puntos clave tras la llamada',
              'ملخّص كتابي اختياري لأهم النقاط بعد المكالمة'),
        ],
        'faqs': [
            (L('Why is the consultation paid?', '¿Por qué es de pago la consultoría?', 'لماذا تكون الاستشارة مدفوعة؟'),
             L("Charging for the session keeps it focused and valuable — for you and for us. It filters for genuine technical needs and guarantees you get undivided attention rather than a generic sales call.",
               "Cobrar por la sesión la mantiene enfocada y útil, para ti y para nosotros. Garantiza atención plena ante una necesidad técnica real, en lugar de una llamada comercial genérica.",
               "تحصيل رسوم على الجلسة يبقيها مركّزة ومفيدة لك ولنا، ويضمن اهتمامًا كاملًا بحاجة تقنية حقيقية بدلًا من مكالمة بيعية عامة.")),
            (L('What should I prepare beforehand?', '¿Qué debo preparar de antemano?', 'ما الذي ينبغي تحضيره مسبقًا؟'),
             L("A short written description of your situation, your Odoo version, and the specific question or decision you want help with. This lets us use the full session productively.",
               "Una breve descripción de tu situación, tu versión de Odoo y la pregunta o decisión concreta con la que necesitas ayuda. Así aprovechamos al máximo toda la sesión.",
               "وصف موجز لوضعك، وإصدار Odoo لديك، والسؤال أو القرار المحدّد الذي تحتاج المساعدة فيه؛ فهذا يتيح لنا استثمار الجلسة كاملةً بفعالية.")),
            (L('Can this lead to a bigger project?', '¿Puede dar lugar a un proyecto mayor?', 'هل يمكن أن تؤدّي إلى مشروع أكبر؟'),
             L("Yes — many engagements start this way. If it makes sense to continue, we will outline a clear scope and price for the next step.",
               "Sí; muchos proyectos empiezan así. Si tiene sentido continuar, definiremos un alcance y un precio claros para el siguiente paso.",
               "نعم — كثير من المشاريع تبدأ بهذه الطريقة. وإذا كان الاستمرار منطقيًا، فسنحدّد نطاقًا وسعرًا واضحين للخطوة التالية.")),
        ],
    },
    {
        'title': L('Odoo ERP Implementation', 'Implantación de Odoo ERP', 'تطبيق نظام Odoo ERP'),
        'short_description': L(
            'End-to-end Odoo implementation designed around your processes and your data model — not a generic template.',
            'Implantación de Odoo de principio a fin, diseñada en torno a tus procesos y tu modelo de datos, no una plantilla genérica.',
            'تطبيق Odoo من البداية إلى النهاية مصمَّم حول عملياتك ونموذج بياناتك — لا قالب عام.'),
        'description': L(
            "A new ERP is a chance to fix how your business runs — or a chance to carry old chaos into a new "
            "system. We run implementation as an engineering project: we map your processes, design a clean data "
            "model, configure the Odoo apps you actually need, and migrate your existing data with validation and "
            "deduplication so day one starts on numbers you can trust.\n"
            "Because Bidatia lives in data and governance, we set up your Odoo so it can feed a warehouse, BI and "
            "AI from the start — not as a bolt-on two years later.",

            "Un ERP nuevo es la oportunidad de arreglar cómo funciona tu negocio, o de arrastrar el viejo caos a un "
            "sistema nuevo. Abordamos la implantación como un proyecto de ingeniería: mapeamos tus procesos, "
            "diseñamos un modelo de datos limpio, configuramos las apps de Odoo que realmente necesitas y migramos "
            "tus datos con validación y deduplicación, para que el primer día empiece con cifras fiables.\n"
            "Como Bidatia vive en los datos y el gobierno del dato, dejamos tu Odoo preparado para alimentar un "
            "almacén de datos, BI e IA desde el principio, no como un añadido dos años después.",

            "النظام الجديد فرصة لإصلاح طريقة عمل شركتك، أو فرصة لنقل الفوضى القديمة إلى نظام جديد. ننفّذ التطبيق "
            "كمشروع هندسي: نرسم عملياتك، ونصمّم نموذج بيانات نظيفًا، ونعدّ تطبيقات Odoo التي تحتاجها فعلًا، ونرحّل "
            "بياناتك مع التحقّق وإزالة التكرار، ليبدأ اليوم الأول بأرقام موثوقة.\n"
            "ولأن Bidatia متخصّصة في البيانات وحوكمتها، نُعدّ Odoo لديك ليغذّي مستودع البيانات وأدوات BI والذكاء "
            "الاصطناعي منذ البداية، لا كإضافة بعد عامين."),
        'outcome': L(
            'A live Odoo, tailored to your operation, with clean migrated data and a model built to scale.',
            'Un Odoo en producción, adaptado a tu operación, con datos migrados limpios y un modelo preparado para crecer.',
            'نظام Odoo حيّ، مُفصَّل على تشغيلك، ببيانات مُرحَّلة نظيفة ونموذج مبني للتوسّع.'),
        'icon': 'module',
        'price_label': L('Project-based', 'Por proyecto', 'حسب المشروع'),
        'delivery_time': L('Scope-based, typically 4–12 weeks', 'Según el alcance, normalmente 4–12 semanas', 'حسب النطاق، عادةً 4–12 أسبوعًا'),
        'is_featured': False,
        'order': 2,
        'meta_description': L(
            'Odoo ERP implementation by Bidatia: process mapping, clean data model, app configuration and validated data migration, built to feed your BI and AI from day one.',
            'Implantación de Odoo ERP por Bidatia: mapeo de procesos, modelo de datos limpio, configuración de apps y migración de datos validada, lista para alimentar tu BI e IA desde el primer día.',
            'تطبيق Odoo ERP من Bidatia: رسم العمليات، ونموذج بيانات نظيف، وإعداد التطبيقات، وترحيل بيانات مُتحقَّق منه، جاهز لتغذية BI والذكاء الاصطناعي منذ اليوم الأول.'),
        'features': [
            L('Process discovery and clean data-model design',
              'Descubrimiento de procesos y diseño de un modelo de datos limpio',
              'اكتشاف العمليات وتصميم نموذج بيانات نظيف'),
            L('Configuration of the Odoo apps your operation actually needs',
              'Configuración de las apps de Odoo que tu operación realmente necesita',
              'إعداد تطبيقات Odoo التي يحتاجها تشغيلك فعلًا'),
            L('Validated, deduplicated data migration from your old systems',
              'Migración de datos validada y deduplicada desde tus sistemas anteriores',
              'ترحيل بيانات مُتحقَّق منه وخالٍ من التكرار من أنظمتك السابقة'),
            L('Ready to connect to a data warehouse, BI and AI from the start',
              'Lista para conectarse a un almacén de datos, BI e IA desde el inicio',
              'جاهز للاتصال بمستودع بيانات و BI وذكاء اصطناعي منذ البداية'),
        ],
        'faqs': [
            (L('Do you migrate our existing data?', '¿Migráis nuestros datos actuales?', 'هل ترحّلون بياناتنا الحالية؟'),
             L("Yes. Data migration — with cleansing, validation and deduplication — is a core part of every implementation, so you go live on trustworthy records.",
               "Sí. La migración de datos —con limpieza, validación y deduplicación— es parte central de cada implantación, para que arranques con registros fiables.",
               "نعم. ترحيل البيانات — مع التنظيف والتحقّق وإزالة التكرار — جزء أساسي من كل تطبيق، لتنطلق بسجلّات موثوقة.")),
            (L('Can you phase the rollout?', '¿Podéis desplegarlo por fases?', 'هل يمكن الإطلاق على مراحل؟'),
             L("Yes — we often start with a core set of apps and expand once the team is comfortable, which lowers risk and speeds up adoption.",
               "Sí: solemos empezar con un conjunto básico de apps y ampliar cuando el equipo se siente cómodo, lo que reduce el riesgo y acelera la adopción.",
               "نعم — غالبًا نبدأ بمجموعة أساسية من التطبيقات ونوسّع عندما يرتاح الفريق، ما يقلّل المخاطر ويسرّع التبنّي.")),
        ],
    },
    {
        'title': L('ERP + Data Integration', 'Integración de ERP y datos', 'تكامل ERP والبيانات'),
        'short_description': L(
            'Connect Odoo to your data warehouse, BI tools and the apps around it with governed, well-tested ETL and APIs.',
            'Conecta Odoo con tu almacén de datos, tus herramientas de BI y las apps de su entorno mediante ETL y APIs gobernados y bien probados.',
            'اربط Odoo بمستودع بياناتك وأدوات BI والتطبيقات المحيطة عبر ETL وواجهات برمجية مَحوكمة ومُختبَرة جيدًا.'),
        'description': L(
            "Your ERP is one source of truth — but leadership needs all of them in one place. We build the "
            "pipelines that move data between Odoo, your data warehouse, your BI layer and the rest of your stack: "
            "scheduled ETL, real-time APIs, and change-data capture where it matters.\n"
            "Every integration is documented, monitored and built with governance in mind, so you always know "
            "where a number came from and trust it when it lands on a dashboard.",

            "Tu ERP es una fuente de verdad, pero la dirección necesita todas en un mismo lugar. Construimos los "
            "flujos que mueven datos entre Odoo, tu almacén de datos, tu capa de BI y el resto de tu stack: ETL "
            "programado, APIs en tiempo real y captura de cambios donde importa.\n"
            "Cada integración queda documentada, monitorizada y construida con el gobierno del dato en mente, para "
            "que siempre sepas de dónde viene una cifra y confíes en ella cuando aparece en un panel.",

            "نظامك مصدر حقيقة واحد، لكن الإدارة تحتاجها جميعًا في مكان واحد. نبني المسارات التي تنقل البيانات بين "
            "Odoo ومستودع بياناتك وطبقة BI وبقية منظومتك: ETL مجدوَل، وواجهات برمجية فورية، والتقاط التغييرات حيث "
            "يلزم.\n"
            "كل تكامل موثَّق ومُراقَب ومبني مع مراعاة الحوكمة، لتعرف دائمًا مصدر أي رقم وتثق به عند ظهوره على لوحة."),
        'outcome': L(
            'One connected data flow, so every report and dashboard agrees with your ERP.',
            'Un flujo de datos conectado, para que cada informe y panel coincida con tu ERP.',
            'تدفّق بيانات واحد متّصل، ليتوافق كل تقرير ولوحة مع نظامك.'),
        'icon': 'integration',
        'price_label': L('From €1,200', 'Desde 1.200 €', 'من 1٬200 €'),
        'delivery_time': L('Scope-based, typically 2–6 weeks', 'Según el alcance, normalmente 2–6 semanas', 'حسب النطاق، عادةً 2–6 أسابيع'),
        'is_featured': False,
        'order': 3,
        'meta_description': L(
            'ERP and data integration by Bidatia: governed ETL and APIs connecting Odoo to your data warehouse, BI and the rest of your stack, with monitoring and documentation.',
            'Integración de ERP y datos por Bidatia: ETL y APIs gobernados que conectan Odoo con tu almacén de datos, tu BI y el resto de tu stack, con monitorización y documentación.',
            'تكامل ERP والبيانات من Bidatia: ETL وواجهات برمجية مَحوكمة تربط Odoo بمستودع بياناتك و BI وبقية منظومتك، مع مراقبة وتوثيق.'),
        'features': [
            L('Scheduled ETL and real-time API integrations',
              'ETL programado e integraciones de API en tiempo real',
              'ETL مجدوَل وتكاملات واجهات برمجية فورية'),
            L('Connections to data warehouses and BI platforms',
              'Conexiones con almacenes de datos y plataformas de BI',
              'اتصالات بمستودعات البيانات ومنصّات BI'),
            L('Monitoring and alerting so broken syncs surface fast',
              'Monitorización y alertas para detectar a tiempo las sincronizaciones rotas',
              'مراقبة وتنبيهات لاكتشاف المزامنات المعطّلة بسرعة'),
            L('Documented data lineage you can audit',
              'Linaje de datos documentado y auditable',
              'تتبُّع مصدر البيانات موثَّق وقابل للتدقيق'),
        ],
        'faqs': [
            (L('Which systems can you connect?', '¿Con qué sistemas podéis conectar?', 'ما الأنظمة التي يمكنكم ربطها؟'),
             L("Anything with an API or database access — warehouses, BI tools, payment and logistics providers, marketplaces and custom apps. If it has no API, we design a safe integration path.",
               "Cualquier sistema con API o acceso a base de datos: almacenes de datos, herramientas de BI, pasarelas de pago y logística, marketplaces y apps a medida. Si no tiene API, diseñamos una vía de integración segura.",
               "أي نظام له واجهة برمجية أو وصول لقاعدة بيانات: المستودعات، وأدوات BI، ومزوّدو الدفع واللوجستيات، والأسواق، والتطبيقات المخصّصة. وإن لم تكن له واجهة، نصمّم مسار تكامل آمنًا.")),
            (L('How do you handle data quality?', '¿Cómo gestionáis la calidad de los datos?', 'كيف تتعاملون مع جودة البيانات؟'),
             L("Validation and reconciliation are built into the pipelines, and we can pair this with our data-governance service for ongoing quality rules.",
               "La validación y la conciliación van integradas en los flujos, y podemos combinarlo con nuestro servicio de gobierno del dato para reglas de calidad continuas.",
               "التحقّق والمطابقة مدمجان في المسارات، ويمكننا دمج ذلك مع خدمة حوكمة البيانات لقواعد جودة مستمرّة.")),
        ],
    },
    {
        'title': L('BI Dashboards & Management Reporting', 'Cuadros de mando de BI e informes de gestión', 'لوحات BI وتقارير الإدارة'),
        'short_description': L(
            'Turn your Odoo operation into dashboards and KPIs leadership can actually trust and act on.',
            'Convierte tu operación de Odoo en cuadros de mando y KPIs en los que la dirección puede confiar y actuar.',
            'حوّل تشغيل Odoo لديك إلى لوحات ومؤشّرات أداء يمكن للإدارة الوثوق بها والتصرّف بناءً عليها.'),
        'description': L(
            "Most teams have data everywhere and answers nowhere. We design management dashboards on top of your "
            "Odoo and warehouse data — sales, margins, cash, inventory, operations — with clearly defined metrics "
            "so everyone reads the same number the same way.\n"
            "We build in the BI tool you already use (or recommend one), define the metric layer, and document "
            "every KPI so 'revenue' or 'margin' means exactly one thing across the company.",

            "La mayoría de los equipos tienen datos por todas partes y respuestas en ninguna. Diseñamos cuadros de "
            "mando de gestión sobre tus datos de Odoo y del almacén —ventas, márgenes, caja, inventario, "
            "operaciones— con métricas bien definidas para que todos lean la misma cifra del mismo modo.\n"
            "Trabajamos en la herramienta de BI que ya usas (o te recomendamos una), definimos la capa de métricas "
            "y documentamos cada KPI para que 'ingresos' o 'margen' signifiquen exactamente una cosa en toda la empresa.",

            "معظم الفرق لديها بيانات في كل مكان وإجابات في لا مكان. نصمّم لوحات إدارية فوق بيانات Odoo والمستودع "
            "— المبيعات والهوامش والنقد والمخزون والعمليات — بمقاييس واضحة التعريف ليقرأ الجميع الرقم نفسه بالطريقة "
            "نفسها.\n"
            "نعمل داخل أداة BI التي تستخدمها (أو نوصي بواحدة)، ونعرّف طبقة المقاييس، ونوثّق كل مؤشّر أداء ليعني "
            "'الإيراد' أو 'الهامش' شيئًا واحدًا بالضبط عبر الشركة."),
        'outcome': L(
            'Dashboards your leadership trusts, with every KPI defined and traceable to source.',
            'Cuadros de mando en los que confía tu dirección, con cada KPI definido y trazable hasta su origen.',
            'لوحات تثق بها إدارتك، مع كل مؤشّر معرَّف وقابل للتتبّع حتى المصدر.'),
        'icon': 'bi',
        'price_label': L('From €900', 'Desde 900 €', 'من 900 €'),
        'delivery_time': L('Scope-based, typically 2–4 weeks', 'Según el alcance, normalmente 2–4 semanas', 'حسب النطاق، عادةً 2–4 أسابيع'),
        'is_featured': False,
        'order': 4,
        'meta_description': L(
            'BI dashboards and management reporting by Bidatia: trustworthy KPIs on top of your Odoo and warehouse data, with a documented metric layer and clear definitions.',
            'Cuadros de mando de BI e informes de gestión por Bidatia: KPIs fiables sobre tus datos de Odoo y del almacén, con una capa de métricas documentada y definiciones claras.',
            'لوحات BI وتقارير الإدارة من Bidatia: مؤشّرات موثوقة فوق بيانات Odoo والمستودع، مع طبقة مقاييس موثَّقة وتعريفات واضحة.'),
        'features': [
            L('Management dashboards for sales, margin, cash and operations',
              'Cuadros de mando de gestión para ventas, margen, caja y operaciones',
              'لوحات إدارية للمبيعات والهامش والنقد والعمليات'),
            L('A documented metric layer with single KPI definitions',
              'Una capa de métricas documentada con definiciones únicas de KPI',
              'طبقة مقاييس موثَّقة بتعريفات موحَّدة للمؤشّرات'),
            L('Built in your existing BI tool, or one we recommend',
              'Construido en tu herramienta de BI actual, o en una que te recomendemos',
              'مبني في أداة BI الحالية لديك، أو واحدة نوصي بها'),
            L('Self-service views so teams answer their own questions',
              'Vistas de autoservicio para que los equipos respondan sus propias preguntas',
              'عروض خدمة ذاتية لتجيب الفرق عن أسئلتها بنفسها'),
        ],
        'faqs': [
            (L('Which BI tools do you support?', '¿Qué herramientas de BI soportáis?', 'ما أدوات BI التي تدعمونها؟'),
             L("We work with the major BI platforms and Odoo's own reporting. If you don't have one yet, we'll recommend a fit for your size and budget.",
               "Trabajamos con las principales plataformas de BI y con los informes propios de Odoo. Si aún no tienes una, te recomendaremos la adecuada para tu tamaño y presupuesto.",
               "نعمل مع منصّات BI الرئيسية ومع تقارير Odoo نفسها. وإن لم تكن لديك أداة بعد، نوصي بما يناسب حجمك وميزانيتك.")),
            (L('Why define metrics formally?', '¿Por qué definir las métricas formalmente?', 'لماذا تعريف المقاييس رسميًا؟'),
             L("Because most reporting disputes are really definition disputes. A documented metric layer ends the 'whose number is right' argument.",
               "Porque la mayoría de las discusiones sobre informes son en realidad discusiones de definición. Una capa de métricas documentada acaba con el debate de 'qué cifra es la correcta'.",
               "لأن معظم الخلافات حول التقارير هي خلافات تعريف في حقيقتها. طبقة مقاييس موثَّقة تُنهي جدال 'أي رقم هو الصحيح'.")),
        ],
    },
    {
        'title': L('AI Agents for Business Processes', 'Agentes de IA para procesos de negocio', 'وكلاء ذكاء اصطناعي للعمليات'),
        'short_description': L(
            'Put AI agents to work on the repetitive parts of your ERP — with humans in the loop and clear guardrails.',
            'Pon agentes de IA a trabajar en las partes repetitivas de tu ERP, con personas supervisando y límites claros.',
            'شغّل وكلاء الذكاء الاصطناعي على الأجزاء المتكرّرة من نظامك — مع إشراف بشري وحدود واضحة.'),
        'description': L(
            "Not every task needs a person, and not every task should be left to a model alone. We design practical "
            "AI agents around real ERP workflows: triaging incoming documents, drafting responses, classifying "
            "records, summarizing cases and flagging anomalies — always with a human approval step where it counts.\n"
            "Drawing on Bidatia's AI and RAG expertise, every agent is grounded in your own governed data, scoped "
            "to a clear task, logged and auditable. No black boxes deciding your business.",

            "No todas las tareas necesitan a una persona, ni todas deben dejarse solo a un modelo. Diseñamos agentes "
            "de IA prácticos sobre flujos reales del ERP: clasificar documentos entrantes, redactar respuestas, "
            "categorizar registros, resumir casos y señalar anomalías, siempre con un paso de aprobación humana "
            "donde importa.\n"
            "Apoyándonos en la experiencia de Bidatia en IA y RAG, cada agente se basa en tus propios datos "
            "gobernados, se acota a una tarea clara y queda registrado y auditable. Sin cajas negras decidiendo tu negocio.",

            "ليست كل مهمّة تحتاج إلى شخص، وليست كل مهمّة يجب تركها لنموذج وحده. نصمّم وكلاء ذكاء اصطناعي عمليين حول "
            "تدفّقات ERP حقيقية: فرز المستندات الواردة، وصياغة الردود، وتصنيف السجلّات، وتلخيص الحالات، ورصد "
            "الشذوذ — دائمًا مع خطوة موافقة بشرية حيث يلزم.\n"
            "بالاعتماد على خبرة Bidatia في الذكاء الاصطناعي و RAG، يُبنى كل وكيل على بياناتك المَحوكمة، ويُحصَر في "
            "مهمّة واضحة، ويكون مسجَّلًا وقابلًا للتدقيق. بلا صناديق سوداء تقرّر عن عملك."),
        'outcome': L(
            'Less manual busywork, faster cycle times, and AI you can actually trust in production.',
            'Menos trabajo manual repetitivo, ciclos más rápidos e IA en la que puedes confiar en producción.',
            'عمل يدوي أقلّ، ودورات أسرع، وذكاء اصطناعي يمكنك الوثوق به في الإنتاج.'),
        'icon': 'ai',
        'price_label': L('From €1,500', 'Desde 1.500 €', 'من 1٬500 €'),
        'delivery_time': L('Scope-based, typically 3–8 weeks', 'Según el alcance, normalmente 3–8 semanas', 'حسب النطاق، عادةً 3–8 أسابيع'),
        'is_featured': False,
        'order': 6,
        'meta_description': L(
            'AI agents for business processes by Bidatia: practical, human-in-the-loop automation grounded in your governed ERP data, scoped, logged and auditable.',
            'Agentes de IA para procesos de negocio por Bidatia: automatización práctica con supervisión humana, basada en tus datos de ERP gobernados, acotada, registrada y auditable.',
            'وكلاء ذكاء اصطناعي للعمليات من Bidatia: أتمتة عملية بإشراف بشري، مبنية على بيانات ERP مَحوكمة، محصورة ومسجَّلة وقابلة للتدقيق.'),
        'features': [
            L('Document triage, drafting, classification and summarization',
              'Clasificación, redacción, categorización y resumen de documentos',
              'فرز المستندات وصياغتها وتصنيفها وتلخيصها'),
            L('Grounded in your own governed data (RAG), not generic models',
              'Basados en tus propios datos gobernados (RAG), no en modelos genéricos',
              'مبنية على بياناتك المَحوكمة (RAG)، لا على نماذج عامة'),
            L('Human-in-the-loop approval where decisions matter',
              'Aprobación humana en el bucle donde las decisiones importan',
              'موافقة بشرية ضمن المسار حيث تهمّ القرارات'),
            L('Logged, auditable actions — no black boxes',
              'Acciones registradas y auditables, sin cajas negras',
              'إجراءات مسجَّلة وقابلة للتدقيق، بلا صناديق سوداء'),
        ],
        'faqs': [
            (L('Is our data sent to a third party?', '¿Se envían nuestros datos a terceros?', 'هل تُرسَل بياناتنا إلى طرف ثالث؟'),
             L("We design for your risk profile — including private or local model deployments — so sensitive data stays where your governance requires.",
               "Diseñamos según tu perfil de riesgo —incluidos despliegues de modelos privados o locales— para que los datos sensibles permanezcan donde tu gobierno del dato lo exija.",
               "نصمّم وفق ملف المخاطر لديك — بما في ذلك نشر نماذج خاصة أو محلّية — لتبقى البيانات الحسّاسة حيث تتطلّب حوكمتك.")),
            (L('What if the AI gets it wrong?', '¿Y si la IA se equivoca?', 'وماذا لو أخطأ الذكاء الاصطناعي؟'),
             L("Agents are scoped and supervised: high-impact steps require human approval, and every action is logged so you can review and correct.",
               "Los agentes están acotados y supervisados: los pasos de alto impacto requieren aprobación humana y cada acción queda registrada para revisarla y corregirla.",
               "الوكلاء محصورون ومُراقَبون: الخطوات عالية التأثير تتطلّب موافقة بشرية، وكل إجراء مسجَّل لمراجعته وتصحيحه.")),
        ],
    },
    {
        'title': L('Data Governance for ERP & CRM', 'Gobierno del dato para ERP y CRM', 'حوكمة البيانات لـ ERP و CRM'),
        'short_description': L(
            'Make your Odoo and CRM data a governed asset: clear ownership, quality rules, definitions and a trusted single source of truth.',
            'Convierte los datos de tu Odoo y CRM en un activo gobernado: propiedad clara, reglas de calidad, definiciones y una fuente única de verdad fiable.',
            'اجعل بيانات Odoo و CRM لديك أصلًا مَحوكمًا: ملكية واضحة، وقواعد جودة، وتعريفات، ومصدر حقيقة واحد موثوق.'),
        'description': L(
            "Bad ERP decisions usually start with bad data: duplicate customers, inconsistent product codes, "
            "empty mandatory fields, three definitions of 'active'. We bring Bidatia's data-governance practice to "
            "your operational systems — defining ownership, data-quality rules, naming standards and validation so "
            "the records people rely on stay clean over time.\n"
            "You get a practical governance framework, quality dashboards that surface issues early, and the "
            "controls to keep Odoo and your CRM as a single source of truth — not a swamp.",

            "Las malas decisiones de ERP suelen empezar con malos datos: clientes duplicados, códigos de producto "
            "inconsistentes, campos obligatorios vacíos, tres definiciones de 'activo'. Llevamos la práctica de "
            "gobierno del dato de Bidatia a tus sistemas operativos: definimos propiedad, reglas de calidad, "
            "estándares de nomenclatura y validaciones para que los registros de los que dependes se mantengan "
            "limpios con el tiempo.\n"
            "Obtienes un marco de gobierno práctico, cuadros de calidad que detectan problemas a tiempo y los "
            "controles para mantener Odoo y tu CRM como una fuente única de verdad, no como un pantano.",

            "تبدأ قرارات ERP السيّئة عادةً ببيانات سيّئة: عملاء مكرّرون، ورموز منتجات غير متّسقة، وحقول إلزامية "
            "فارغة، وثلاثة تعريفات لكلمة 'نشِط'. ننقل ممارسة حوكمة البيانات لدى Bidatia إلى أنظمتك التشغيلية: نحدّد "
            "الملكية، وقواعد الجودة، ومعايير التسمية، وعمليات التحقّق ليبقى ما تعتمد عليه من سجلّات نظيفًا مع الوقت.\n"
            "تحصل على إطار حوكمة عملي، ولوحات جودة تكشف المشكلات مبكّرًا، والضوابط للحفاظ على Odoo و CRM كمصدر "
            "حقيقة واحد، لا كمستنقع."),
        'outcome': L(
            'Clean, owned, well-defined data you can finally build reporting and AI on.',
            'Datos limpios, con propietario y bien definidos sobre los que por fin construir informes e IA.',
            'بيانات نظيفة ومملوكة وواضحة التعريف يمكنك أخيرًا بناء التقارير والذكاء الاصطناعي عليها.'),
        'icon': 'governance',
        'price_label': L('From €1,100', 'Desde 1.100 €', 'من 1٬100 €'),
        'delivery_time': L('Scope-based, typically 2–6 weeks', 'Según el alcance, normalmente 2–6 semanas', 'حسب النطاق، عادةً 2–6 أسابيع'),
        'is_featured': False,
        'order': 8,
        'meta_description': L(
            'Data governance for ERP and CRM by Bidatia: ownership, quality rules, naming standards and validation that keep your Odoo and CRM a trusted single source of truth.',
            'Gobierno del dato para ERP y CRM por Bidatia: propiedad, reglas de calidad, estándares de nomenclatura y validación que mantienen tu Odoo y CRM como una fuente única de verdad fiable.',
            'حوكمة البيانات لـ ERP و CRM من Bidatia: ملكية، وقواعد جودة، ومعايير تسمية، وتحقّق تحافظ على Odoo و CRM كمصدر حقيقة واحد موثوق.'),
        'features': [
            L('Data ownership, quality rules and naming standards',
              'Propiedad de datos, reglas de calidad y estándares de nomenclatura',
              'ملكية البيانات وقواعد الجودة ومعايير التسمية'),
            L('De-duplication and validation for customers, products and more',
              'Deduplicación y validación de clientes, productos y más',
              'إزالة التكرار والتحقّق للعملاء والمنتجات وغيرها'),
            L('Data-quality dashboards that surface issues early',
              'Cuadros de calidad de datos que detectan problemas a tiempo',
              'لوحات جودة بيانات تكشف المشكلات مبكّرًا'),
            L('A governance framework your team can maintain',
              'Un marco de gobierno que tu equipo puede mantener',
              'إطار حوكمة يستطيع فريقك الحفاظ عليه'),
        ],
        'faqs': [
            (L('Is this only for big companies?', '¿Es solo para grandes empresas?', 'هل هذا للشركات الكبيرة فقط؟'),
             L("No. Smaller teams benefit most, because clean data early prevents the expensive cleanup later. We scope governance to your size.",
               "No. Los equipos más pequeños son los que más se benefician, porque tener datos limpios pronto evita la costosa limpieza posterior. Adaptamos el gobierno a tu tamaño.",
               "لا. الفرق الأصغر هي الأكثر استفادة، لأن البيانات النظيفة مبكّرًا تمنع التنظيف المكلف لاحقًا. نضبط الحوكمة على حجمك.")),
            (L('Does this pair with the assessment?', '¿Se combina con la evaluación?', 'هل يتكامل مع التقييم؟'),
             L("Yes — the ERP & Data Assessment is the ideal starting point; it identifies exactly where governance will pay off first.",
               "Sí: la Evaluación de ERP y datos es el punto de partida ideal; identifica exactamente dónde el gobierno del dato rendirá antes.",
               "نعم — تقييم ERP والبيانات هو نقطة البداية المثلى؛ فهو يحدّد بالضبط أين ستثمر الحوكمة أولًا.")),
        ],
    },
    {
        'slug': 'odoo-health-check',
        'title': L('ERP & Data Assessment', 'Evaluación de ERP y datos', 'تقييم نظام ERP والبيانات'),
        'short_description': L(
            'A fixed-scope audit of your Odoo system and its data: configuration, customizations, automations, performance, security, data quality and governance.',
            'Una auditoría de alcance cerrado de tu sistema Odoo y de sus datos: configuración, personalizaciones, automatizaciones, rendimiento, seguridad, calidad de los datos y gobierno.',
            'تدقيق محدّد النطاق لنظام Odoo لديك ولبياناته: الإعدادات، والتخصيصات، والأتمتة، والأداء، والأمان، وجودة البيانات وحوكمتها.'),
        'description': L(
            "If your Odoo feels slower, messier, or harder to trust than it used to, the Health Check gives you "
            "an honest, structured picture of what's really going on — and what to do about it.\n"
            "We review your configuration, custom code and Studio changes, automated actions, performance "
            "bottlenecks, access/security rules, and overall data quality. Instead of vague impressions, you "
            "get a written report that separates urgent issues from nice-to-haves, so you can prioritize with confidence.\n"
            "The engagement closes with a 30-minute review call where we walk through the findings together and "
            "answer your questions.",

            "Si tu Odoo se ha vuelto más lento, más desordenado o menos fiable que antes, el diagnóstico te ofrece "
            "una imagen honesta y estructurada de lo que realmente ocurre, y de qué hacer al respecto.\n"
            "Revisamos tu configuración, el código a medida y los cambios de Studio, las acciones automatizadas, "
            "los cuellos de botella de rendimiento, las reglas de acceso y seguridad y la calidad general de los "
            "datos. En lugar de impresiones vagas, recibes un informe escrito que separa lo urgente de lo accesorio "
            "para que priorices con seguridad.\n"
            "El servicio se cierra con una llamada de revisión de 30 minutos en la que repasamos juntos las "
            "conclusiones y resolvemos tus dudas.",

            "إذا أصبح Odoo لديك أبطأ أو أكثر فوضى أو أقلّ موثوقية مما كان، يمنحك الفحص الفني صورة صادقة ومنظَّمة لما "
            "يجري فعلًا — وما الذي ينبغي فعله حياله.\n"
            "نراجع الإعدادات، والشيفرة المخصّصة وتغييرات Studio، والإجراءات الآلية، ونقاط ضعف الأداء، وقواعد الوصول "
            "والأمان، وجودة البيانات بشكل عام. وبدلًا من انطباعات غامضة، تحصل على تقرير مكتوب يفصل المسائل العاجلة "
            "عن التحسينات الثانوية لتتمكّن من ترتيب الأولويات بثقة.\n"
            "وتُختتم الخدمة بمكالمة مراجعة مدّتها 30 دقيقة نستعرض فيها النتائج معًا ونجيب عن أسئلتك."),
        'outcome': L(
            'A prioritized, written roadmap that tells you exactly what to fix first — and why.',
            'Una hoja de ruta escrita y priorizada que te dice exactamente qué corregir primero, y por qué.',
            'خارطة طريق مكتوبة ومرتّبة حسب الأولوية تحدّد لك بالضبط ما يجب إصلاحه أولًا — ولماذا.'),
        'icon': 'audit',
        'price_label': L('From €690', 'Desde 690 €', 'من 690 €'),
        'delivery_time': L('3–5 business days', '3–5 días laborables', '3–5 أيام عمل'),
        'is_featured': True,
        'order': 5,
        'meta_description': L(
            'Get a fixed-scope Odoo Health Check: a full technical audit covering configuration, customizations, performance, security and data quality, delivered as a prioritized PDF report.',
            'Solicita un diagnóstico técnico de Odoo de alcance cerrado: una auditoría completa de configuración, personalizaciones, rendimiento, seguridad y calidad de los datos, entregada como informe PDF priorizado.',
            'اطلب الفحص الفني لنظام Odoo بنطاق محدّد: تدقيق شامل يغطّي الإعدادات والتخصيصات والأداء والأمان وجودة البيانات، يُسلَّم كتقرير PDF مرتّب حسب الأولوية.'),
        'features': [
            L('Full review of configuration, customizations and Studio usage',
              'Revisión completa de la configuración, las personalizaciones y el uso de Studio',
              'مراجعة كاملة للإعدادات والتخصيصات واستخدام Studio'),
            L('Assessment of automated actions, workflows and integrations',
              'Evaluación de acciones automatizadas, flujos de trabajo e integraciones',
              'تقييم الإجراءات الآلية وسير العمل والتكاملات'),
            L('Performance, security rules and data quality review',
              'Análisis de rendimiento, reglas de seguridad y calidad de los datos',
              'فحص الأداء وقواعد الأمان وجودة البيانات'),
            L('Prioritized PDF report with clear, actionable recommendations',
              'Informe PDF priorizado con recomendaciones claras y accionables',
              'تقرير PDF مرتّب حسب الأولوية مع توصيات واضحة وقابلة للتنفيذ'),
            L('30-minute review call to walk through the findings together',
              'Llamada de revisión de 30 minutos para repasar juntos las conclusiones',
              'مكالمة مراجعة مدّتها 30 دقيقة لاستعراض النتائج معًا'),
        ],
        'faqs': [
            (L('How long does the Health Check take?', '¿Cuánto tarda el diagnóstico?', 'كم يستغرق الفحص الفني؟'),
             L("Most Health Checks are delivered within 3-5 business days from the moment we receive access to your system and the information we need.",
               "La mayoría de los diagnósticos se entregan en 3-5 días laborables desde que recibimos acceso a tu sistema y la información necesaria.",
               "تُسلَّم معظم عمليات الفحص خلال 3-5 أيام عمل من لحظة حصولنا على صلاحية الوصول إلى نظامك والمعلومات المطلوبة.")),
            (L('Do you need access to our live system?', '¿Necesitáis acceso a nuestro sistema en producción?', 'هل تحتاجون إلى الوصول إلى نظامنا الفعلي؟'),
             L("Typically yes — read access to your Odoo instance (or a recent copy/staging environment) lets us give you an accurate, evidence-based report rather than guesses.",
               "Normalmente sí: el acceso de lectura a tu instancia de Odoo (o a una copia reciente o entorno de pruebas) nos permite ofrecerte un informe preciso y basado en evidencias, no en suposiciones.",
               "غالبًا نعم — صلاحية الاطّلاع على نظام Odoo لديك (أو نسخة حديثة أو بيئة اختبار) تتيح لنا تقديم تقرير دقيق مبني على أدلة لا على تخمينات.")),
            (L('What happens after the report?', '¿Qué ocurre después del informe?', 'ماذا يحدث بعد التقرير؟'),
             L("You're free to act on it yourself, hand it to your existing team, or ask Bidatia to implement the recommended fixes as a follow-up engagement.",
               "Puedes aplicarlo por tu cuenta, entregárselo a tu equipo o pedir a Bidatia que implemente las correcciones recomendadas como servicio de seguimiento.",
               "أنت حرّ في تنفيذه بنفسك، أو تسليمه لفريقك الحالي، أو الطلب من Bidatia تنفيذ الإصلاحات الموصى بها كخدمة متابعة.")),
        ],
    },
    {
        'title': L('Odoo Studio Cleanup', 'Migración de personalizaciones de Odoo Studio', 'تحويل تخصيصات Odoo Studio'),
        'short_description': L(
            'Convert fragile Odoo Studio customizations into clean, maintainable custom modules that survive upgrades.',
            'Convierte las personalizaciones frágiles de Odoo Studio en módulos a medida limpios y mantenibles que sobreviven a las actualizaciones.',
            'حوِّل تخصيصات Odoo Studio الهشّة إلى وحدات مخصّصة نظيفة وقابلة للصيانة تصمد أمام الترقيات.'),
        'description': L(
            "Odoo Studio is a great tool for prototyping — but Studio-only customizations tend to become "
            "fragile over time: they're hard to version, easy to break during upgrades, and difficult for "
            "developers to extend safely.\n"
            "This service takes your existing Studio changes — fields, views, automations, reports — and "
            "rebuilds them as proper, version-controlled custom modules following Odoo development best practices. "
            "The result behaves the same (or better) for your users, but is dramatically easier to maintain, "
            "audit, and upgrade going forward.\n"
            "We start by mapping exactly what your Studio setup currently does, then design a clean module "
            "structure before writing a single line of code — so nothing important gets lost in translation.",

            "Odoo Studio es una gran herramienta para crear prototipos, pero las personalizaciones hechas solo con "
            "Studio tienden a volverse frágiles con el tiempo: son difíciles de versionar, se rompen con facilidad "
            "en las actualizaciones y resultan complicadas de ampliar con seguridad.\n"
            "Este servicio toma tus cambios actuales de Studio —campos, vistas, automatizaciones, informes— y los "
            "reconstruye como módulos a medida bien versionados, siguiendo las buenas prácticas de desarrollo de "
            "Odoo. El resultado funciona igual (o mejor) para tus usuarios, pero es muchísimo más fácil de mantener, "
            "auditar y actualizar.\n"
            "Empezamos por documentar con precisión qué hace hoy tu configuración de Studio y diseñamos una "
            "estructura de módulos limpia antes de escribir una sola línea de código, para que no se pierda nada "
            "importante por el camino.",

            "يُعدّ Odoo Studio أداة ممتازة لبناء النماذج الأولية، لكن التخصيصات المعتمدة على Studio وحده تميل إلى أن "
            "تصبح هشّة مع الوقت: يصعب إصدارها، وتنكسر بسهولة أثناء الترقيات، ويصعب على المطوّرين توسيعها بأمان.\n"
            "تأخذ هذه الخدمة تغييرات Studio الحالية لديك — الحقول والواجهات والأتمتة والتقارير — وتعيد بناءها كوحدات "
            "مخصّصة خاضعة لإدارة الإصدارات، وفق أفضل ممارسات تطوير Odoo. والنتيجة تعمل بالطريقة نفسها (أو أفضل) "
            "لمستخدميك، لكنها أسهل بكثير في الصيانة والتدقيق والترقية لاحقًا.\n"
            "نبدأ بتوثيق ما يفعله إعداد Studio لديك بدقّة، ثم نصمّم بنية وحدات نظيفة قبل كتابة سطر برمجي واحد — حتى "
            "لا يضيع أي شيء مهمّ في أثناء التحويل."),
        'outcome': L(
            'The same functionality your team relies on, rebuilt as clean code your next developer can actually maintain.',
            'La misma funcionalidad de la que depende tu equipo, reconstruida como código limpio que tu próximo desarrollador podrá mantener de verdad.',
            'الوظائف نفسها التي يعتمد عليها فريقك، معاد بناؤها كشيفرة نظيفة يستطيع مطوّرك التالي صيانتها فعلًا.'),
        'icon': 'cleanup',
        'price_label': L('From €600', 'Desde 600 €', 'من 600 €'),
        'delivery_time': L('Scope-based, typically 1–3 weeks', 'Según el alcance, normalmente 1–3 semanas', 'حسب النطاق، عادةً 1–3 أسابيع'),
        'is_featured': False,
        'order': 3,
        'meta_description': L(
            'Convert fragile Odoo Studio customizations into clean, maintainable custom modules. Bidatia rebuilds your Studio changes as proper, upgrade-safe Odoo code.',
            'Convierte las personalizaciones frágiles de Odoo Studio en módulos a medida limpios y mantenibles. Bidatia reconstruye tus cambios de Studio como código Odoo seguro ante actualizaciones.',
            'حوِّل تخصيصات Odoo Studio الهشّة إلى وحدات مخصّصة نظيفة وقابلة للصيانة. يعيد Bidatia بناء تغييرات Studio لديك كشيفرة Odoo آمنة أمام الترقيات.'),
        'features': [
            L('Full mapping of existing Studio fields, views, automations and reports',
              'Documentación completa de los campos, vistas, automatizaciones e informes actuales de Studio',
              'توثيق كامل لحقول Studio وواجهاته وأتمتته وتقاريره الحالية'),
            L('Clean module architecture designed before any code is written',
              'Arquitectura de módulos limpia diseñada antes de escribir código',
              'بنية وحدات نظيفة تُصمَّم قبل كتابة أي شيفرة'),
            L('Rebuilt functionality delivered as version-controlled custom modules',
              'Funcionalidad reconstruida y entregada como módulos a medida versionados',
              'وظائف معاد بناؤها تُسلَّم كوحدات مخصّصة خاضعة لإدارة الإصدارات'),
            L('Testing to confirm parity with the original Studio behaviour',
              'Pruebas para confirmar la equivalencia con el comportamiento original de Studio',
              'اختبارات للتأكّد من تطابق السلوك مع إعداد Studio الأصلي'),
            L('Documentation so your team understands what changed and why',
              'Documentación para que tu equipo entienda qué cambió y por qué',
              'توثيق ليفهم فريقك ما الذي تغيّر ولماذا'),
        ],
        'faqs': [
            (L('Will my users notice any difference?', '¿Notarán algún cambio mis usuarios?', 'هل سيلاحظ مستخدمونا أي فرق؟'),
             L("In most cases, no — the goal is to preserve the experience your team is used to while making the underlying implementation solid and maintainable.",
               "En la mayoría de los casos, no: el objetivo es conservar la experiencia a la que tu equipo está acostumbrado, haciendo que la implementación interna sea sólida y mantenible.",
               "في معظم الحالات لا — فالهدف هو الحفاظ على التجربة التي اعتاد عليها فريقك، مع جعل التنفيذ الداخلي متينًا وقابلًا للصيانة.")),
            (L('Is this only for large Studio setups?', '¿Es solo para configuraciones grandes de Studio?', 'هل هذه الخدمة للإعدادات الكبيرة فقط؟'),
             L("No. Even a handful of fragile customizations can cause outsized pain during upgrades — cleaning them up early is usually cheaper than fixing a broken migration later.",
               "No. Incluso unas pocas personalizaciones frágiles pueden causar grandes problemas en las actualizaciones; limpiarlas a tiempo suele salir más barato que arreglar una migración rota después.",
               "لا. حتى عدد قليل من التخصيصات الهشّة قد يسبّب متاعب كبيرة أثناء الترقيات — ومعالجتها مبكرًا غالبًا أقلّ كلفة من إصلاح ترقية فاشلة لاحقًا.")),
            (L('How is the price determined?', '¿Cómo se determina el precio?', 'كيف يُحدَّد السعر؟'),
             L("After reviewing your current Studio setup, we provide a fixed price based on the actual scope — so you know the investment before work begins.",
               "Tras revisar tu configuración actual de Studio, te damos un precio cerrado según el alcance real, para que conozcas la inversión antes de empezar.",
               "بعد مراجعة إعداد Studio الحالي لديك، نقدّم سعرًا ثابتًا بناءً على النطاق الفعلي — لتعرف قيمة الاستثمار قبل بدء العمل.")),
        ],
    },
    {
        'title': L('Odoo Migration Assessment', 'Evaluación de migración de Odoo', 'تقييم ترقية Odoo'),
        'short_description': L(
            'A clear-eyed analysis of the risks, effort and roadmap for moving from your current Odoo version to a newer one.',
            'Un análisis riguroso de los riesgos, el esfuerzo y la hoja de ruta para pasar de tu versión actual de Odoo a una más reciente.',
            'تحليل واقعي للمخاطر والجهد وخارطة الطريق للانتقال من إصدار Odoo الحالي إلى إصدار أحدث.'),
        'description': L(
            "Migrating Odoo versions can unlock real benefits — but it can also turn into a costly, "
            "drawn-out project if the risks aren't understood up front. This assessment gives you an "
            "honest, technical view of what a migration would actually involve for your specific system.\n"
            "We review your current version, customizations, integrations, data volume and complexity, "
            "and identify the areas most likely to cause friction during an upgrade. You receive a written "
            "roadmap covering recommended approach, estimated effort, risk areas, and a realistic recommendation "
            "on timing and strategy.\n"
            "This is the assessment to run before committing budget to a migration project — so decisions "
            "are based on evidence, not guesswork.",

            "Actualizar la versión de Odoo puede aportar beneficios reales, pero también puede convertirse en un "
            "proyecto largo y caro si no se entienden los riesgos desde el principio. Esta evaluación te ofrece una "
            "visión técnica y honesta de lo que implicaría realmente la migración de tu sistema concreto.\n"
            "Revisamos tu versión actual, las personalizaciones, las integraciones, el volumen de datos y su "
            "complejidad, e identificamos las áreas con más probabilidad de generar fricción durante la "
            "actualización. Recibes una hoja de ruta escrita con el enfoque recomendado, el esfuerzo estimado, "
            "las zonas de riesgo y una recomendación realista sobre el momento y la estrategia.\n"
            "Es la evaluación que conviene hacer antes de comprometer presupuesto en una migración, para que las "
            "decisiones se basen en evidencias y no en suposiciones.",

            "قد تُتيح ترقية إصدار Odoo فوائد حقيقية، لكنها قد تتحوّل أيضًا إلى مشروع طويل ومكلف إذا لم تُفهم المخاطر "
            "مسبقًا. يمنحك هذا التقييم رؤية تقنية صادقة لما تتطلّبه الترقية فعليًا لنظامك تحديدًا.\n"
            "نراجع إصدارك الحالي والتخصيصات والتكاملات وحجم البيانات ومدى تعقيدها، ونحدّد المجالات الأكثر احتمالًا "
            "لإحداث صعوبات أثناء الترقية. وتحصل على خارطة طريق مكتوبة تتضمّن المقاربة الموصى بها، والجهد المقدَّر، "
            "ومناطق الخطر، وتوصية واقعية بشأن التوقيت والاستراتيجية.\n"
            "هذا هو التقييم الذي ينبغي إجراؤه قبل تخصيص ميزانية لمشروع ترقية — لتكون القرارات مبنية على أدلة لا على "
            "تخمين."),
        'outcome': L(
            'A realistic migration roadmap with risks and effort clearly laid out — before you commit any budget.',
            'Una hoja de ruta de migración realista con los riesgos y el esfuerzo claramente expuestos, antes de comprometer presupuesto.',
            'خارطة طريق واقعية للترقية تُبيّن المخاطر والجهد بوضوح — قبل أن تخصّص أي ميزانية.'),
        'icon': 'migration',
        'price_label': L('€450 – €700', '450 € – 700 €', '450 € – 700 €'),
        'delivery_time': L('5–7 business days', '5–7 días laborables', '5–7 أيام عمل'),
        'is_featured': False,
        'order': 4,
        'meta_description': L(
            'Get an Odoo Migration Assessment: a clear roadmap covering risks, effort estimates and recommendations for upgrading to a newer Odoo version, from Bidatia Madrid.',
            'Solicita una evaluación de migración de Odoo: una hoja de ruta clara con riesgos, estimación de esfuerzo y recomendaciones para actualizar a una versión más reciente, de Bidatia Madrid.',
            'اطلب تقييم ترقية Odoo: خارطة طريق واضحة تغطّي المخاطر وتقديرات الجهد والتوصيات للانتقال إلى إصدار أحدث من Odoo، من Bidatia مدريد.'),
        'features': [
            L('Review of your current Odoo version, customizations and integrations',
              'Revisión de tu versión actual de Odoo, las personalizaciones y las integraciones',
              'مراجعة لإصدار Odoo الحالي والتخصيصات والتكاملات'),
            L('Identification of high-risk areas likely to cause migration friction',
              'Identificación de las áreas de mayor riesgo durante la migración',
              'تحديد المجالات عالية الخطورة التي قد تعيق الترقية'),
            L('Estimated effort and realistic timeline for the migration project',
              'Estimación de esfuerzo y un calendario realista para el proyecto de migración',
              'تقدير الجهد وجدول زمني واقعي لمشروع الترقية'),
            L('Written roadmap with a clear, actionable recommendation',
              'Hoja de ruta escrita con una recomendación clara y accionable',
              'خارطة طريق مكتوبة مع توصية واضحة وقابلة للتنفيذ'),
            L('Optional follow-up support during the actual migration',
              'Soporte opcional de seguimiento durante la migración',
              'دعم متابعة اختياري أثناء تنفيذ الترقية'),
        ],
        'faqs': [
            (L('Do you also perform the migration itself?', '¿Realizáis también la migración en sí?', 'هل تنفّذون الترقية نفسها أيضًا؟'),
             L("Yes — the assessment can be followed by a migration engagement scoped on the findings, either fully managed by Bidatia or supporting your existing team.",
               "Sí: tras la evaluación puede venir un proyecto de migración definido a partir de las conclusiones, gestionado íntegramente por Bidatia o como apoyo a tu equipo.",
               "نعم — يمكن أن يلي التقييمَ مشروعُ ترقية يُحدَّد نطاقه بناءً على النتائج، سواء بإدارة كاملة من Bidatia أو بدعم فريقك الحالي.")),
            (L('What Odoo versions do you support?', '¿Qué versiones de Odoo abarcáis?', 'ما إصدارات Odoo التي تدعمونها؟'),
             L("We work across recent Community and Enterprise versions. Tell us your current version and target version, and we will confirm fit during the initial conversation.",
               "Trabajamos con las versiones recientes de Community y Enterprise. Indícanos tu versión actual y la de destino y confirmaremos la viabilidad en la conversación inicial.",
               "نعمل على الإصدارات الحديثة من Community و Enterprise. أخبرنا بإصدارك الحالي والإصدار المستهدف وسنؤكّد ملاءمته في المحادثة الأولى.")),
            (L('Is this useful if we are not sure we want to migrate yet?', '¿Sirve si aún no tenemos claro si queremos migrar?', 'هل يفيد إن لم نكن متأكّدين بعد من رغبتنا في الترقية؟'),
             L("Especially then — the assessment is designed to help you decide whether, when, and how to migrate, based on facts rather than assumptions.",
               "Especialmente entonces: la evaluación está pensada para ayudarte a decidir si migrar, cuándo y cómo, con datos en lugar de suposiciones.",
               "في تلك الحالة تحديدًا — فالتقييم مصمَّم لمساعدتك على تقرير ما إذا كنت ستُجري الترقية، ومتى، وكيف، بناءً على حقائق لا افتراضات.")),
        ],
    },
    {
        'title': L('Custom Odoo Module Development', 'Desarrollo de módulos a medida para Odoo', 'تطوير وحدات Odoo مخصّصة'),
        'short_description': L(
            'New models, views, workflows, automations and reports — built as clean, maintainable custom modules tailored to your business.',
            'Nuevos modelos, vistas, flujos de trabajo, automatizaciones e informes, desarrollados como módulos a medida limpios y mantenibles, adaptados a tu negocio.',
            'نماذج وواجهات وتدفّقات عمل وأتمتة وتقارير جديدة — مبنية كوحدات مخصّصة نظيفة وقابلة للصيانة ومصمَّمة وفق احتياجات عملك.'),
        'description': L(
            "When Odoo doesn't quite fit how your business actually works, the right answer is rarely more "
            "Studio patches — it's a properly engineered custom module. We design and build models, views, "
            "security rules, workflows, automations and reports that extend Odoo the way it was meant to be extended.\n"
            "Every module is built with maintainability in mind: clear structure, sensible naming, "
            "appropriate tests, and documentation — so it remains an asset to your business rather than "
            "a liability at the next upgrade.\n"
            "Whether you need a small, focused addition or a more substantial extension to your ERP, "
            "we scope the work clearly before development starts, so you always know what you're getting.",

            "Cuando Odoo no encaja del todo con la forma real de trabajar de tu empresa, la solución rara vez son "
            "más parches de Studio: es un módulo a medida bien diseñado. Diseñamos y desarrollamos modelos, vistas, "
            "reglas de seguridad, flujos de trabajo, automatizaciones e informes que amplían Odoo como está pensado "
            "que se amplíe.\n"
            "Cada módulo se construye pensando en su mantenimiento: estructura clara, nombres coherentes, pruebas "
            "adecuadas y documentación, para que siga siendo un activo y no un problema en la próxima actualización.\n"
            "Tanto si necesitas una pequeña incorporación como una ampliación más amplia de tu ERP, definimos el "
            "alcance con claridad antes de empezar a desarrollar, para que siempre sepas qué vas a recibir.",

            "عندما لا يناسب Odoo تمامًا الطريقة التي يعمل بها نشاطك فعلًا، نادرًا ما يكون الحل مزيدًا من ترقيعات "
            "Studio — بل وحدة مخصّصة مصمَّمة هندسيًا بشكل سليم. نصمّم ونبني النماذج والواجهات وقواعد الأمان وتدفّقات "
            "العمل والأتمتة والتقارير التي توسّع Odoo بالطريقة التي صُمّم للتوسّع بها.\n"
            "تُبنى كل وحدة مع وضع قابلية الصيانة في الاعتبار: بنية واضحة، وتسمية منطقية، واختبارات مناسبة، وتوثيق — "
            "لتظلّ أصلًا لعملك لا عبئًا عند الترقية التالية.\n"
            "وسواء احتجت إلى إضافة صغيرة محدّدة أو توسعة أكبر لنظام ERP لديك، نحدّد نطاق العمل بوضوح قبل بدء التطوير، "
            "لتعرف دائمًا ما الذي ستحصل عليه."),
        'outcome': L(
            'A purpose-built feature that fits your business process — engineered to last, not just to work today.',
            'Una funcionalidad hecha a medida que encaja con tu proceso de negocio, diseñada para durar y no solo para funcionar hoy.',
            'وظيفة مصمَّمة لغرضك تناسب سير عمل نشاطك — مهندَسة لتدوم، لا لتعمل اليوم فقط.'),
        'icon': 'module',
        'price_label': L('From €800 or hourly', 'Desde 800 € o por horas', 'من 800 € أو بالساعة'),
        'delivery_time': L('Scope-based', 'Según el alcance', 'حسب النطاق'),
        'is_featured': False,
        'order': 5,
        'meta_description': L(
            'Custom Odoo module development by Bidatia: models, views, security, workflows, automations and reports built as clean, maintainable code for your business.',
            'Desarrollo de módulos a medida para Odoo por Bidatia: modelos, vistas, seguridad, flujos de trabajo, automatizaciones e informes como código limpio y mantenible para tu negocio.',
            'تطوير وحدات Odoo مخصّصة من Bidatia: نماذج وواجهات وأمان وتدفّقات عمل وأتمتة وتقارير مبنية كشيفرة نظيفة وقابلة للصيانة لعملك.'),
        'features': [
            L('Requirements mapping and module design before development starts',
              'Definición de requisitos y diseño del módulo antes de empezar a desarrollar',
              'تحديد المتطلبات وتصميم الوحدة قبل بدء التطوير'),
            L('Clean implementation following Odoo development best practices',
              'Implementación limpia siguiendo las buenas prácticas de desarrollo de Odoo',
              'تنفيذ نظيف وفق أفضل ممارسات تطوير Odoo'),
            L('Custom views, workflows, automations, and report templates',
              'Vistas, flujos de trabajo, automatizaciones y plantillas de informe a medida',
              'واجهات وتدفّقات عمل وأتمتة وقوالب تقارير مخصّصة'),
            L('Testing and quality checks before delivery',
              'Pruebas y controles de calidad antes de la entrega',
              'اختبارات وفحوصات جودة قبل التسليم'),
            L('Documentation and a short handover walkthrough',
              'Documentación y una breve sesión de traspaso',
              'توثيق وجلسة تسليم قصيرة'),
        ],
        'faqs': [
            (L('Can you work alongside our existing developer or partner?', '¿Podéis trabajar junto a nuestro desarrollador o partner actual?', 'هل يمكنكم العمل بالتوازي مع مطوّرنا أو شريكنا الحالي؟'),
             L("Yes — Bidatia regularly works alongside in-house teams and partner agencies, including under white-label arrangements where appropriate.",
               "Sí: Bidatia colabora habitualmente con equipos internos y agencias partner, incluso en modalidad de marca blanca cuando procede.",
               "نعم — يعمل Bidatia بانتظام إلى جانب الفرق الداخلية ووكالات الشركاء، بما في ذلك ترتيبات العلامة البيضاء عند الاقتضاء.")),
            (L('Do you provide ongoing maintenance for the module?', '¿Ofrecéis mantenimiento continuo del módulo?', 'هل تقدّمون صيانة مستمرة للوحدة؟'),
             L("Yes, either as part of the project agreement or through a Monthly Odoo Support package once the module is live.",
               "Sí, ya sea como parte del acuerdo del proyecto o mediante un paquete de Soporte mensual de Odoo una vez que el módulo esté en producción.",
               "نعم، سواء كجزء من اتفاق المشروع أو عبر باقة دعم Odoo الشهري بعد إطلاق الوحدة.")),
            (L('How is pricing decided — fixed or hourly?', '¿El precio es cerrado o por horas?', 'كيف يُحدَّد السعر — ثابت أم بالساعة؟'),
             L("For well-defined scopes we prefer fixed pricing so you know the investment up front. For exploratory or evolving work, an hourly arrangement may be more appropriate — we will recommend what fits best.",
               "Para alcances bien definidos preferimos precio cerrado, para que conozcas la inversión de antemano. Para trabajos exploratorios o cambiantes, puede encajar mejor un acuerdo por horas; te recomendaremos lo más adecuado.",
               "للنطاقات المحدّدة جيدًا نفضّل السعر الثابت لتعرف قيمة الاستثمار مسبقًا. أمّا للأعمال الاستكشافية أو المتغيّرة، فقد يكون الترتيب بالساعة أنسب — وسنوصي بما يناسب أكثر.")),
        ],
    },
    {
        'title': L('Django ↔ Odoo Integration', 'Integración Django ↔ Odoo', 'تكامل Django ↔ Odoo'),
        'short_description': L(
            'Reliable API integrations connecting Odoo with external platforms — payment providers, shipping, marketplaces and custom Django systems.',
            'Integraciones de API fiables que conectan Odoo con plataformas externas: pasarelas de pago, transporte, marketplaces y sistemas Django a medida.',
            'تكاملات API موثوقة تربط Odoo بالمنصّات الخارجية — مزوّدي الدفع، والشحن، والأسواق الإلكترونية، وأنظمة Django المخصّصة.'),
        'description': L(
            "Modern businesses rarely run on a single system. This service builds robust, well-tested "
            "integrations between Odoo and the other platforms your business depends on — payment providers, "
            "shipping and logistics platforms, marketplaces, or your own custom Django applications.\n"
            "We design the integration around your actual data flows: what should sync, how often, what "
            "happens on errors, and how to keep both systems consistent over time. The result is automation "
            "that quietly does its job — saving your team from manual data entry and costly mistakes.\n"
            "Because this work sits at the intersection of Odoo and Django, it benefits directly from "
            "engineering experience on both sides — not just configuration knowledge of one.",

            "Las empresas actuales rara vez funcionan con un solo sistema. Este servicio crea integraciones robustas "
            "y bien probadas entre Odoo y las demás plataformas de las que depende tu negocio: pasarelas de pago, "
            "plataformas de transporte y logística, marketplaces o tus propias aplicaciones Django.\n"
            "Diseñamos la integración en torno a tus flujos de datos reales: qué debe sincronizarse, con qué "
            "frecuencia, qué ocurre ante errores y cómo mantener ambos sistemas coherentes con el tiempo. El "
            "resultado es una automatización que hace su trabajo en silencio, evitando a tu equipo la introducción "
            "manual de datos y los errores costosos.\n"
            "Como este trabajo se sitúa en la intersección de Odoo y Django, se beneficia directamente de la "
            "experiencia de ingeniería en ambos lados, y no solo del conocimiento de configuración de uno.",

            "نادرًا ما تعمل الشركات الحديثة على نظام واحد. تبني هذه الخدمة تكاملات متينة ومختبَرة جيدًا بين Odoo "
            "والمنصّات الأخرى التي يعتمد عليها عملك — مزوّدي الدفع، ومنصّات الشحن والخدمات اللوجستية، والأسواق "
            "الإلكترونية، أو تطبيقات Django الخاصة بك.\n"
            "نصمّم التكامل حول تدفّقات بياناتك الفعلية: ما الذي يجب مزامنته، وكم مرّة، وماذا يحدث عند الأخطاء، وكيف "
            "نُبقي النظامين متّسقين مع الوقت. والنتيجة أتمتة تؤدّي عملها بهدوء — تُجنّب فريقك الإدخال اليدوي للبيانات "
            "والأخطاء المكلفة.\n"
            "ولأنّ هذا العمل يقع عند تقاطع Odoo و Django، فإنه يستفيد مباشرةً من الخبرة الهندسية في الجانبين معًا — "
            "لا من معرفة إعداد أحدهما فقط."),
        'outcome': L(
            'Two systems that talk to each other reliably — less manual work, fewer errors, better data consistency.',
            'Dos sistemas que se comunican de forma fiable: menos trabajo manual, menos errores y mejor coherencia de los datos.',
            'نظامان يتواصلان معًا بموثوقية — عمل يدوي أقل، وأخطاء أقل، واتّساق أفضل للبيانات.'),
        'icon': 'integration',
        'price_label': L('From €900', 'Desde 900 €', 'من 900 €'),
        'delivery_time': L('Scope-based', 'Según el alcance', 'حسب النطاق'),
        'is_featured': False,
        'order': 6,
        'meta_description': L(
            'Django and Odoo API integrations by Bidatia: connect Odoo with payment providers, shipping platforms, marketplaces and custom systems reliably and securely.',
            'Integraciones de API entre Django y Odoo por Bidatia: conecta Odoo con pasarelas de pago, plataformas de transporte, marketplaces y sistemas a medida de forma fiable y segura.',
            'تكاملات API بين Django و Odoo من Bidatia: اربط Odoo بمزوّدي الدفع ومنصّات الشحن والأسواق الإلكترونية والأنظمة المخصّصة بموثوقية وأمان.'),
        'features': [
            L('Mapping of data flows and integration requirements between systems',
              'Análisis de los flujos de datos y los requisitos de integración entre sistemas',
              'تحليل تدفّقات البيانات ومتطلّبات التكامل بين الأنظمة'),
            L('Secure, well-structured API integration design and implementation',
              'Diseño e implementación de una integración de API segura y bien estructurada',
              'تصميم وتنفيذ تكامل API آمن ومنظَّم جيدًا'),
            L('Error handling, retries and monitoring considerations built in',
              'Gestión de errores, reintentos y monitorización incorporados desde el diseño',
              'معالجة الأخطاء وإعادة المحاولة والمراقبة مدمجة من التصميم'),
            L('Testing across realistic scenarios before go-live',
              'Pruebas con escenarios realistas antes de la puesta en producción',
              'اختبارات على سيناريوهات واقعية قبل الإطلاق'),
            L('Documentation covering how the integration works and how to maintain it',
              'Documentación sobre cómo funciona la integración y cómo mantenerla',
              'توثيق يشرح كيفية عمل التكامل وكيفية صيانته'),
        ],
        'faqs': [
            (L('What platforms can you integrate with Odoo?', '¿Qué plataformas podéis integrar con Odoo?', 'ما المنصّات التي يمكنكم دمجها مع Odoo؟'),
             L("Most platforms that expose an API can be integrated — common examples include payment providers, shipping/logistics services, marketplaces, and custom Django or other backend systems.",
               "Se puede integrar la mayoría de plataformas que ofrecen una API; ejemplos habituales son pasarelas de pago, servicios de transporte y logística, marketplaces y sistemas backend a medida en Django u otras tecnologías.",
               "يمكن دمج معظم المنصّات التي توفّر واجهة API — ومن الأمثلة الشائعة مزوّدو الدفع، وخدمات الشحن والخدمات اللوجستية، والأسواق الإلكترونية، وأنظمة Django المخصّصة أو غيرها من الأنظمة الخلفية.")),
            (L('Can you also build the other side of the integration?', '¿Podéis desarrollar también el otro lado de la integración?', 'هل يمكنكم بناء الطرف الآخر من التكامل أيضًا؟'),
             L("Yes — if the external system is a custom Django application (existing or new), Bidatia can design and build that side too, ensuring both ends are engineered to work well together.",
               "Sí: si el sistema externo es una aplicación Django a medida (existente o nueva), Bidatia también puede diseñar y construir ese lado, asegurando que ambos extremos encajen bien.",
               "نعم — إذا كان النظام الخارجي تطبيق Django مخصّصًا (قائمًا أو جديدًا)، يستطيع Bidatia تصميم وبناء ذلك الطرف أيضًا، بما يضمن انسجام الطرفين معًا.")),
            (L('How do you handle ongoing reliability?', '¿Cómo garantizáis la fiabilidad a largo plazo?', 'كيف تضمنون الموثوقية على المدى الطويل؟'),
             L("We design integrations with error handling and monitoring in mind from the start, and offer Monthly Odoo Support for ongoing monitoring and adjustments after go-live.",
               "Diseñamos las integraciones con la gestión de errores y la monitorización en mente desde el principio, y ofrecemos Soporte mensual de Odoo para la supervisión y los ajustes posteriores a la puesta en marcha.",
               "نصمّم التكاملات مع مراعاة معالجة الأخطاء والمراقبة منذ البداية، ونوفّر دعم Odoo الشهري للمراقبة والتعديلات المستمرّة بعد الإطلاق.")),
        ],
    },
    {
        'title': L('Monthly Odoo Support', 'Soporte mensual de Odoo', 'دعم Odoo الشهري'),
        'short_description': L(
            'A recurring support package giving you direct access to a senior Odoo consultant for fixes, improvements and questions.',
            'Un paquete de soporte recurrente que te da acceso directo a un consultor sénior de Odoo para correcciones, mejoras y consultas.',
            'باقة دعم متجدّدة تمنحك تواصلًا مباشرًا مع استشاري Odoo خبير للإصلاحات والتحسينات والاستفسارات.'),
        'description': L(
            "Not every business needs a full-time Odoo developer — but most benefit from having one within "
            "reach. Monthly Odoo Support gives you a fixed number of hours each month with a senior consultant "
            "who already understands (or quickly learns) your system, so issues get resolved fast and small "
            "improvements don't pile up.\n"
            "Each plan includes priority support for urgent issues and a monthly summary covering what was "
            "worked on, what's outstanding, and any recommendations — so you always have visibility into "
            "where your Odoo system stands.\n"
            "It's a practical alternative to ad-hoc freelance help or expensive enterprise retainers — "
            "predictable cost, direct access, and continuity over time.",

            "No todas las empresas necesitan un desarrollador de Odoo a jornada completa, pero a casi todas les "
            "viene bien tener uno a mano. El Soporte mensual de Odoo te ofrece un número fijo de horas al mes con "
            "un consultor sénior que ya conoce (o aprende rápido) tu sistema, de modo que las incidencias se "
            "resuelven pronto y las pequeñas mejoras no se acumulan.\n"
            "Cada plan incluye soporte prioritario para incidencias urgentes y un resumen mensual con lo trabajado, "
            "lo pendiente y las recomendaciones, para que siempre tengas visibilidad del estado de tu sistema Odoo.\n"
            "Es una alternativa práctica a la ayuda freelance puntual o a los costosos contratos de soporte "
            "enterprise: coste previsible, acceso directo y continuidad en el tiempo.",

            "لا تحتاج كل شركة إلى مطوّر Odoo بدوام كامل، لكن معظمها يستفيد من وجود واحد في المتناول. يمنحك دعم Odoo "
            "الشهري عددًا ثابتًا من الساعات كل شهر مع استشاري خبير يعرف نظامك بالفعل (أو يتعلّمه بسرعة)، فتُحلّ "
            "المشكلات بسرعة ولا تتراكم التحسينات الصغيرة.\n"
            "تتضمّن كل باقة دعمًا ذا أولوية للمسائل العاجلة، وملخّصًا شهريًا يغطّي ما تمّ العمل عليه، وما هو معلّق، "
            "وأي توصيات — لتبقى لديك رؤية دائمة لحالة نظام Odoo لديك.\n"
            "وهو بديل عملي عن المساعدة المستقلّة العشوائية أو عقود الدعم المؤسسية الباهظة — كلفة متوقّعة، وتواصل "
            "مباشر، واستمرارية عبر الزمن."),
        'outcome': L(
            'A trusted technical partner on call every month — so small issues get fixed before they become big ones.',
            'Un socio técnico de confianza disponible cada mes, para que los pequeños problemas se resuelvan antes de convertirse en grandes.',
            'شريك تقني موثوق متاح كل شهر — لتُعالَج المشكلات الصغيرة قبل أن تكبر.'),
        'icon': 'support',
        'price_label': L('€300 – €1,000 / month', '300 € – 1000 € / mes', '300 € – 1000 € / شهريًا'),
        'delivery_time': L('Ongoing, monthly billing', 'Continuo, facturación mensual', 'مستمر، فوترة شهرية'),
        'is_featured': False,
        'order': 7,
        'meta_description': L(
            'Monthly Odoo Support from Bidatia: Starter, Standard and Pro plans with fixed hours, priority support and monthly summaries — a reliable technical partner for your ERP.',
            'Soporte mensual de Odoo de Bidatia: planes Starter, Standard y Pro con horas fijas, soporte prioritario y resúmenes mensuales, un socio técnico fiable para tu ERP.',
            'دعم Odoo الشهري من Bidatia: باقات Starter و Standard و Pro بساعات ثابتة ودعم ذي أولوية وملخّصات شهرية — شريك تقني موثوق لنظام ERP لديك.'),
        'features': [
            L('Starter — €300/month: fixed monthly hours for fixes and small changes',
              'Starter — 300 €/mes: horas mensuales fijas para correcciones y pequeños cambios',
              'Starter — 300 €/شهر: ساعات شهرية ثابتة للإصلاحات والتغييرات الصغيرة'),
            L('Standard — €600/month: more hours plus priority response times',
              'Standard — 600 €/mes: más horas y tiempos de respuesta prioritarios',
              'Standard — 600 €/شهر: ساعات أكثر وأوقات استجابة ذات أولوية'),
            L('Pro — €1,000/month: extended hours, fastest priority, and proactive recommendations',
              'Pro — 1000 €/mes: horas ampliadas, máxima prioridad y recomendaciones proactivas',
              'Pro — 1000 €/شهر: ساعات موسّعة، وأعلى أولوية، وتوصيات استباقية'),
            L('Direct access to a senior consultant — no ticket queues',
              'Acceso directo a un consultor sénior, sin colas de tickets',
              'تواصل مباشر مع استشاري خبير — دون طوابير تذاكر'),
            L('Monthly summary covering work completed and recommendations',
              'Resumen mensual con el trabajo realizado y las recomendaciones',
              'ملخّص شهري يغطّي العمل المنجز والتوصيات'),
        ],
        'faqs': [
            (L('What counts as "support" in these plans?', '¿Qué se considera «soporte» en estos planes?', 'ما الذي يُعدّ «دعمًا» في هذه الباقات؟'),
             L("Bug fixes, small configuration changes, automation tweaks, questions from your team, and minor improvements. Larger projects are scoped separately and can run alongside your support plan.",
               "Corrección de errores, pequeños cambios de configuración, ajustes de automatizaciones, consultas de tu equipo y mejoras menores. Los proyectos más grandes se presupuestan aparte y pueden convivir con tu plan de soporte.",
               "إصلاح الأخطاء، والتغييرات الصغيرة في الإعدادات، وتعديلات الأتمتة، وأسئلة فريقك، والتحسينات الطفيفة. أمّا المشاريع الأكبر فتُسعَّر على حدة ويمكن أن تسير بالتوازي مع باقة الدعم.")),
            (L('What happens if we need more than our monthly hours?', '¿Qué pasa si necesitamos más horas de las incluidas?', 'ماذا لو احتجنا أكثر من ساعاتنا الشهرية؟'),
             L("Unused hours and overage handling are agreed upfront so there are no surprises — typically extra work is quoted separately or carried over depending on the plan.",
               "Las horas no usadas y el exceso se acuerdan de antemano para que no haya sorpresas; normalmente el trabajo adicional se presupuesta aparte o se traslada al mes siguiente, según el plan.",
               "تُتّفق مسبقًا آلية الساعات غير المستخدمة وتجاوز الحدّ حتى لا تكون هناك مفاجآت — وعادةً يُسعَّر العمل الإضافي على حدة أو يُرحَّل حسب الباقة.")),
            (L('Can we change plans later?', '¿Podemos cambiar de plan más adelante?', 'هل يمكننا تغيير الباقة لاحقًا؟'),
             L("Yes — plans can be adjusted as your needs evolve, with notice agreed at the start of the engagement.",
               "Sí: los planes pueden ajustarse a medida que evolucionan tus necesidades, con el preaviso acordado al inicio.",
               "نعم — يمكن تعديل الباقات مع تطوّر احتياجاتك، وفق مهلة إشعار يُتّفق عليها عند البدء.")),
        ],
    },
    {
        'title': L('Odoo CRM & Sales Workflow Optimization',
                   'Optimización del flujo de CRM y ventas en Odoo',
                   'تحسين سير عمل CRM والمبيعات في Odoo'),
        'short_description': L(
            'Streamline how leads, quotations and orders flow through Odoo so your sales team sells instead of fighting the system.',
            'Agiliza el recorrido de tus leads, presupuestos y pedidos en Odoo para que tu equipo venda en lugar de pelearse con el sistema.',
            'بسِّط تدفّق العملاء المحتملين وعروض الأسعار والطلبات في Odoo ليبيع فريقك بدل أن يصارع النظام.'),
        'description': L(
            "When your sales process lives half in Odoo and half in spreadsheets and inboxes, deals slip, "
            "quotations take too long, and nobody fully trusts the pipeline. This service makes Odoo CRM and "
            "Sales work the way your team actually sells.\n"
            "We map your real lead-to-order process, then configure pipeline stages, lead assignment, quotation "
            "templates, follow-up reminders and the automations that remove repetitive manual steps. We also tidy "
            "up the reporting so your pipeline and forecasts reflect reality.\n"
            "The goal isn't more features — it's a smoother path from first contact to signed order, with fewer "
            "clicks, fewer dropped leads, and numbers you can rely on.",

            "Cuando tu proceso de ventas vive a medias entre Odoo, hojas de cálculo y el correo, se pierden "
            "oportunidades, los presupuestos tardan demasiado y nadie confía del todo en el pipeline. Este servicio "
            "hace que el CRM y las Ventas de Odoo funcionen como vende realmente tu equipo.\n"
            "Documentamos tu proceso real desde el lead hasta el pedido y configuramos las etapas del pipeline, la "
            "asignación de leads, las plantillas de presupuesto, los recordatorios de seguimiento y las "
            "automatizaciones que eliminan tareas manuales repetitivas. También ordenamos los informes para que tu "
            "pipeline y tus previsiones reflejen la realidad.\n"
            "El objetivo no son más funciones, sino un camino más fluido desde el primer contacto hasta el pedido "
            "firmado: menos clics, menos oportunidades perdidas y cifras fiables.",

            "عندما يكون نشاط مبيعاتك موزّعًا بين Odoo وجداول البيانات والبريد، تضيع الفرص، وتتأخّر عروض الأسعار، ولا "
            "أحد يثق تمامًا في مسار الصفقات. تجعل هذه الخدمة وحدتي CRM والمبيعات في Odoo تعملان بالطريقة التي يبيع بها "
            "فريقك فعلًا.\n"
            "نوثّق مسارك الحقيقي من العميل المحتمل حتى الطلب، ثم نضبط مراحل المسار، وتوزيع العملاء المحتملين، وقوالب "
            "عروض الأسعار، وتذكيرات المتابعة، والأتمتة التي تُزيل المهام اليدوية المتكرّرة. كما ننظّم التقارير لتعكس "
            "مسارك وتوقّعاتك الواقع.\n"
            "الهدف ليس مزيدًا من الميزات، بل مسارًا أكثر سلاسة من أول تواصل حتى الطلب الموقّع: نقرات أقل، وفرص ضائعة "
            "أقل، وأرقام يمكن الاعتماد عليها."),
        'outcome': L(
            'A sales process your team actually follows — fewer manual steps, cleaner pipeline data, and more reliable forecasts.',
            'Un proceso de ventas que tu equipo sí sigue: menos pasos manuales, datos de pipeline más limpios y previsiones más fiables.',
            'عملية مبيعات يتّبعها فريقك فعلًا: خطوات يدوية أقل، وبيانات مسار أنظف، وتوقّعات أكثر موثوقية.'),
        'icon': 'crm',
        'price_label': L('From €450', 'Desde 450 €', 'من 450 €'),
        'delivery_time': L('Scope-based, typically 1–2 weeks', 'Según el alcance, normalmente 1–2 semanas', 'حسب النطاق، عادةً 1–2 أسبوع'),
        'is_featured': False,
        'order': 8,
        'meta_description': L(
            'Optimize your Odoo CRM and Sales workflow: cleaner pipeline stages, automated follow-ups and reliable reporting, built around how your team actually sells.',
            'Optimiza el flujo de CRM y Ventas de Odoo: etapas de pipeline más claras, seguimientos automáticos e informes fiables, adaptados a cómo vende tu equipo.',
            'حسّن سير عمل CRM والمبيعات في Odoo مع Bidatia: مراحل مسار أوضح، ومتابعات آلية، وتقارير مبيعات موثوقة، مضبوطة وفق طريقة بيع فريقك.'),
        'features': [
            L('Mapping of your real lead-to-order sales process',
              'Documentación de tu proceso real de venta, del lead al pedido',
              'توثيق عملية البيع الفعلية لديك من العميل المحتمل إلى الطلب'),
            L('Pipeline stages, lead assignment and quotation templates built around how you sell',
              'Etapas de pipeline, asignación de leads y plantillas de presupuesto adaptadas a tu forma de vender',
              'ضبط مراحل المسار وتوزيع العملاء المحتملين وقوالب عروض الأسعار وفق طريقة بيعك'),
            L('Automated follow-ups and reminders so leads stop going cold',
              'Seguimientos y recordatorios automáticos para que ningún lead se enfríe',
              'متابعات وتذكيرات آلية حتى لا يبرد أيّ عميل محتمل'),
            L('Cleaner sales reporting and a pipeline you can trust',
              'Informes de ventas más claros y un pipeline fiable',
              'تقارير مبيعات أوضح ومسار صفقات موثوق'),
            L('A team walkthrough so the new workflow actually sticks',
              'Una sesión con el equipo para que el nuevo flujo se mantenga',
              'جلسة مع الفريق لضمان استمرار التبنّي للسير الجديد'),
        ],
        'faqs': [
            (L('Is this configuration or custom development?', '¿Esto es configuración o desarrollo a medida?', 'هل هذه إعدادات أم تطوير مخصّص؟'),
             L("Mostly configuration and automation within Odoo. Where a real gap remains, we'll flag it and scope a small custom module separately.",
               "Sobre todo configuración y automatización dentro de Odoo. Si queda una carencia real, te la señalamos y presupuestamos un pequeño módulo a medida aparte.",
               "غالبًا إعدادات وأتمتة داخل Odoo. وإن بقيت فجوة حقيقية، فسننبّهك إليها ونحدّد نطاق وحدة مخصّصة صغيرة على حدة.")),
            (L('Do you work with both Odoo Community and Enterprise?', '¿Trabajáis con Odoo Community y Enterprise?', 'هل تعملون مع Odoo Community و Enterprise؟'),
             L("Yes — we adapt to the CRM and Sales features available in your edition and version.",
               "Sí: nos adaptamos a las funciones de CRM y Ventas disponibles en tu edición y versión.",
               "نعم — نتكيّف مع ميزات CRM والمبيعات المتاحة في إصدارك ونسختك.")),
            (L('Will this disrupt our sales team while you work?', '¿Interrumpirá esto a nuestro equipo de ventas mientras trabajáis?', 'هل سيعطّل هذا فريق المبيعات أثناء عملكم؟'),
             L("No — we prepare and test changes carefully and roll them out with your team, not around them.",
               "No: preparamos y probamos los cambios con cuidado y los desplegamos con tu equipo, no a sus espaldas.",
               "لا — نُعِدّ التغييرات ونختبرها بعناية ونطرحها مع فريقك لا من حوله.")),
        ],
    },
    {
        'title': L('Odoo Accounting & Invoicing Process Review',
                   'Revisión de procesos de contabilidad y facturación en Odoo',
                   'مراجعة عمليات المحاسبة والفوترة في Odoo'),
        'short_description': L(
            'A focused technical review of your Odoo invoicing, tax and reconciliation workflows to cut manual work and month-end errors.',
            'Una revisión técnica centrada en tus flujos de facturación, impuestos y conciliación en Odoo para reducir el trabajo manual y los errores de cierre.',
            'مراجعة تقنية مركّزة لتدفّقات الفوترة والضرائب والتسويات في Odoo لتقليل العمل اليدوي وأخطاء نهاية الشهر.'),
        'description': L(
            "Invoicing and accounting are where small Odoo problems turn into real money and wasted hours: "
            "invoices created by hand, tax positions nobody is quite sure about, payments that don't reconcile "
            "cleanly, and a stressful scramble at month-end.\n"
            "This is a technical process review — not tax advice. We look at how invoices, taxes, payments and "
            "reconciliation actually flow through your Odoo, where the manual and error-prone points are, and which "
            "parts can be safely automated or simplified. Where your accountant or local rules require something "
            "specific, we make Odoo support those requirements rather than work against them.\n"
            "You get a clear write-up of what's slowing your finance team down and a prioritized set of practical "
            "improvements — from configuration fixes to automation — so invoicing gets faster and month-end gets calmer.",

            "La facturación y la contabilidad son donde los pequeños problemas de Odoo se convierten en dinero real "
            "y horas perdidas: facturas creadas a mano, configuraciones de impuestos que generan dudas, cobros que "
            "no se concilian bien y un cierre de mes lleno de prisas.\n"
            "Esto es una revisión técnica de procesos, no asesoramiento fiscal. Analizamos cómo fluyen realmente las "
            "facturas, los impuestos, los pagos y la conciliación en tu Odoo, dónde están los pasos manuales y los "
            "puntos propensos a error, y qué partes se pueden automatizar o simplificar con seguridad. Cuando tu "
            "asesoría o la normativa local exijan algo concreto, hacemos que Odoo dé soporte a esos requisitos en "
            "lugar de complicarlos.\n"
            "Recibes un documento claro de qué frena a tu equipo financiero y un conjunto priorizado de mejoras "
            "prácticas —desde ajustes de configuración hasta automatización— para que facturar sea más rápido y el "
            "cierre de mes, más tranquilo.",

            "الفوترة والمحاسبة هما حيث تتحوّل مشكلات Odoo الصغيرة إلى أموال حقيقية وساعات ضائعة: فواتير تُنشأ يدويًا، "
            "وإعدادات ضرائب غير مؤكَّدة، ومدفوعات لا تُسوَّى بسلاسة، وسباق مرهق في نهاية الشهر.\n"
            "هذه مراجعة تقنية للعمليات وليست استشارة ضريبية. ننظر في كيفية تدفّق الفواتير والضرائب والمدفوعات "
            "والتسويات فعليًا في Odoo لديك، وأين توجد الخطوات اليدوية والنقاط المعرّضة للخطأ، وأي الأجزاء يمكن أتمتتها "
            "أو تبسيطها بأمان. وحيثما يتطلّب محاسبك أو الأنظمة المحلية أمرًا محدّدًا، نجعل Odoo يدعم تلك المتطلّبات بدل "
            "أن يعرقلها.\n"
            "تحصل على تقرير واضح بما يبطئ فريقك المالي، ومجموعة مرتّبة من التحسينات العملية — من إصلاحات الإعداد إلى "
            "الأتمتة — لتصبح الفوترة أسرع ونهاية الشهر أهدأ."),
        'outcome': L(
            'Faster, more automated invoicing and reconciliation — with a calmer, more reliable month-end close.',
            'Una facturación y conciliación más rápidas y automatizadas, con un cierre de mes más tranquilo y fiable.',
            'فوترة وتسويات أسرع وأكثر أتمتة — مع إغلاق شهري أهدأ وأكثر موثوقية.'),
        'icon': 'accounting',
        'price_label': L('From €400', 'Desde 400 €', 'من 400 €'),
        'delivery_time': L('3–6 business days', '3–6 días laborables', '3–6 أيام عمل'),
        'is_featured': False,
        'order': 9,
        'meta_description': L(
            'An Odoo invoicing and accounting process review: cut manual work and reconciliation errors with practical automation. A technical review, not tax advice.',
            'Revisión técnica de procesos de facturación y contabilidad en Odoo: menos trabajo manual y errores de conciliación. No es asesoramiento fiscal.',
            'مراجعة عمليات المحاسبة والفوترة في Odoo من Bidatia: قلّل العمل اليدوي وأخطاء التسوية عبر الأتمتة وتحسينات الإعداد. مراجعة تقنية وليست استشارة ضريبية.'),
        'features': [
            L('Review of your invoicing, tax and reconciliation workflows in Odoo',
              'Revisión de tus flujos de facturación, impuestos y conciliación en Odoo',
              'مراجعة تدفّقات الفوترة والضرائب والتسويات في Odoo'),
            L('Identification of manual, repetitive and error-prone steps',
              'Identificación de pasos manuales, repetitivos y propensos a error',
              'تحديد الخطوات اليدوية والمتكرّرة والمعرّضة للخطأ'),
            L('Practical automation and configuration recommendations',
              'Recomendaciones prácticas de automatización y configuración',
              'توصيات عملية للأتمتة والإعداد'),
            L('A prioritized written summary your finance team can act on',
              'Un resumen escrito priorizado que tu equipo financiero puede aplicar',
              'ملخّص مكتوب مرتّب يمكن لفريقك المالي تنفيذه'),
            L('Optional implementation of the recommended fixes',
              'Implementación opcional de las mejoras recomendadas',
              'تنفيذ اختياري للتحسينات الموصى بها'),
        ],
        'faqs': [
            (L('Do you provide tax or legal advice?', '¿Ofrecéis asesoramiento fiscal o legal?', 'هل تقدّمون استشارات ضريبية أو قانونية؟'),
             L("No. This is a technical review of how your processes run in Odoo. We work with your accountant's requirements rather than replace them.",
               "No. Es una revisión técnica de cómo funcionan tus procesos en Odoo. Trabajamos con los requisitos de tu asesoría, no la sustituimos.",
               "لا. هذه مراجعة تقنية لكيفية سير عملياتك في Odoo. نعمل وفق متطلّبات محاسبك ولا نحلّ محلّه.")),
            (L('Can you help with e-invoicing or local tax requirements?', '¿Podéis ayudar con la facturación electrónica o requisitos fiscales locales?', 'هل يمكنكم المساعدة في الفوترة الإلكترونية أو المتطلّبات الضريبية المحلية؟'),
             L("We can configure Odoo to support the requirements you and your accountant define, and integrate the right tools where needed.",
               "Podemos configurar Odoo para dar soporte a los requisitos que tú y tu asesoría defináis, e integrar las herramientas adecuadas cuando haga falta.",
               "يمكننا ضبط Odoo لدعم المتطلّبات التي تحدّدها أنت ومحاسبك، ودمج الأدوات المناسبة عند الحاجة.")),
            (L("We're not sure where our problems are — is that ok?", 'No tenemos claro dónde están nuestros problemas, ¿es un problema?', 'لسنا متأكّدين أين تكمن مشكلاتنا — هل هذا مقبول؟'),
             L("Yes — pinpointing exactly that is the main purpose of the review.",
               "No: identificar precisamente eso es el objetivo principal de la revisión.",
               "نعم — تحديد ذلك بدقّة هو الغرض الأساسي من المراجعة.")),
        ],
    },
    {
        'title': L('Odoo Automation & Server Actions Review',
                   'Revisión de automatizaciones y acciones de servidor en Odoo',
                   'مراجعة الأتمتة وإجراءات الخادم في Odoo'),
        'short_description': L(
            'Audit and stabilize your automated actions, server actions and scheduled jobs so they stop failing silently.',
            'Audita y estabiliza tus acciones automatizadas, acciones de servidor y tareas programadas para que dejen de fallar en silencio.',
            'تدقيق وتثبيت الإجراءات الآلية وإجراءات الخادم والمهام المجدوَلة في Odoo حتى تتوقّف عن الفشل الصامت.'),
        'description': L(
            "Automated actions, server actions and scheduled jobs are the quiet machinery behind a healthy Odoo — "
            "until one fails silently and nobody notices for weeks. Over time, rules accumulate, overlap, and "
            "occasionally fight each other, with no clear record of what runs, when, or why.\n"
            "This service inventories every automation in your system: automated and server actions, scheduled "
            "(cron) jobs, and the email or webhook triggers attached to them. We identify what's redundant, what's "
            "risky, what's silently failing, and what conflicts with something else — then rebuild the fragile "
            "pieces as clear, maintainable logic with sensible safeguards and logging.\n"
            "The result is automation you can actually trust: documented, conflict-free, and far less likely to "
            "surprise you at the worst possible moment.",

            "Las acciones automatizadas, las acciones de servidor y las tareas programadas son la maquinaria "
            "silenciosa detrás de un Odoo sano… hasta que una falla sin avisar y nadie se da cuenta durante "
            "semanas. Con el tiempo, las reglas se acumulan, se solapan y a veces entran en conflicto, sin un "
            "registro claro de qué se ejecuta, cuándo y por qué.\n"
            "Este servicio inventaría todas las automatizaciones de tu sistema: acciones automatizadas y de "
            "servidor, tareas programadas (cron) y los disparadores de correo o webhook asociados. Identificamos "
            "qué es redundante, qué es arriesgado, qué falla en silencio y qué entra en conflicto con otra cosa, y "
            "reconstruimos las piezas frágiles como una lógica clara y mantenible, con salvaguardas y registro.\n"
            "El resultado es una automatización en la que puedes confiar de verdad: documentada, sin conflictos y "
            "mucho menos propensa a sorprenderte en el peor momento.",

            "الإجراءات الآلية وإجراءات الخادم والمهام المجدوَلة هي الآلية الصامتة خلف نظام Odoo سليم — إلى أن يفشل "
            "أحدها بصمت دون أن يلاحظ أحد لأسابيع. ومع الوقت، تتراكم القواعد وتتداخل وتتعارض أحيانًا، دون سجلّ واضح لما "
            "يُنفَّذ ومتى ولماذا.\n"
            "تُحصي هذه الخدمة كل أتمتة في نظامك: الإجراءات الآلية وإجراءات الخادم، والمهام المجدوَلة (cron)، ومشغّلات "
            "البريد أو الـ webhook المرتبطة بها. نحدّد ما هو زائد، وما هو خطِر، وما يفشل بصمت، وما يتعارض مع غيره، ثم "
            "نعيد بناء الأجزاء الهشّة كمنطق واضح وقابل للصيانة مع ضمانات وتسجيل.\n"
            "والنتيجة أتمتة يمكنك الوثوق بها فعلًا: موثّقة، وخالية من التعارض، وأقلّ احتمالًا بكثير لمفاجأتك في أسوأ "
            "وقت."),
        'outcome': L(
            'Automations you can trust — documented, conflict-free, and rebuilt where they were fragile.',
            'Automatizaciones fiables: documentadas, sin conflictos y reconstruidas donde eran frágiles.',
            'أتمتة يمكن الوثوق بها: موثّقة، وخالية من التعارض، ومعاد بناؤها حيثما كانت هشّة.'),
        'icon': 'automation',
        'price_label': L('From €350', 'Desde 350 €', 'من 350 €'),
        'delivery_time': L('3–5 business days', '3–5 días laborables', '3–5 أيام عمل'),
        'is_featured': False,
        'order': 10,
        'meta_description': L(
            'Audit and stabilize your Odoo automations: find silently failing automated actions and scheduled jobs, resolve conflicts, and rebuild fragile logic.',
            'Audita y estabiliza las automatizaciones de Odoo: detecta acciones y tareas programadas que fallan en silencio, resuelve conflictos y reconstruye la lógica frágil.',
            'دقّق وثبّت أتمتة Odoo مع Bidatia: اكتشف الإجراءات الآلية وإجراءات الخادم والمهام المجدوَلة التي تفشل بصمت، وحلّ التعارضات، وأعد بناء المنطق الهشّ.'),
        'features': [
            L('Full inventory of automated actions, server actions and scheduled jobs',
              'Inventario completo de acciones automatizadas, de servidor y tareas programadas',
              'جرد كامل للإجراءات الآلية وإجراءات الخادم والمهام المجدوَلة'),
            L('Detection of silent failures, conflicts and redundant rules',
              'Detección de fallos silenciosos, conflictos y reglas redundantes',
              'كشف الأعطال الصامتة والتعارضات والقواعد الزائدة'),
            L('Fragile automations rebuilt as clear, maintainable logic',
              'Reconstrucción de las automatizaciones frágiles como lógica clara y mantenible',
              'إعادة بناء الأتمتة الهشّة كمنطق واضح وقابل للصيانة'),
            L('Safeguards and logging so failures surface early',
              'Salvaguardas y registro para que los fallos se detecten pronto',
              'ضمانات وتسجيل لتظهر الأعطال مبكرًا'),
            L('Documentation of what runs, when and why',
              'Documentación de qué se ejecuta, cuándo y por qué',
              'توثيق لما يُنفَّذ ومتى ولماذا'),
        ],
        'faqs': [
            (L('How is this different from a Health Check?', '¿En qué se diferencia de un diagnóstico técnico?', 'كيف يختلف هذا عن الفحص الفني؟'),
             L("The Health Check is a broad audit of your whole system; this is a deep, focused engagement on automations specifically — including rebuilding the fragile ones.",
               "El diagnóstico es una auditoría amplia de todo el sistema; esto es un trabajo profundo y centrado solo en las automatizaciones, incluida la reconstrucción de las frágiles.",
               "الفحص تدقيق واسع لكامل النظام؛ أمّا هذا فعمل عميق مركّز على الأتمتة تحديدًا — بما في ذلك إعادة بناء الهشّ منها.")),
            (L('Can you set up monitoring so we know when something fails?', '¿Podéis configurar monitorización para saber cuándo algo falla?', 'هل يمكنكم إعداد مراقبة لنعرف متى يفشل شيء؟'),
             L("Yes — adding logging and failure visibility is a core part of the work, and we can extend it through a monthly support plan.",
               "Sí: añadir registro y visibilidad de fallos es parte central del trabajo, y podemos ampliarlo con un plan de soporte mensual.",
               "نعم — إضافة التسجيل ووضوح الأعطال جزء أساسي من العمل، ويمكننا توسيعه عبر باقة دعم شهري.")),
            (L('Will reviewing automations interrupt our operations?', '¿Revisar las automatizaciones interrumpirá nuestra operativa?', 'هل ستعطّل مراجعة الأتمتة عملياتنا؟'),
             L("No — we review safely and test rebuilds before they replace anything live.",
               "No: revisamos con seguridad y probamos las reconstrucciones antes de que sustituyan nada en producción.",
               "لا — نراجع بأمان ونختبر ما نعيد بناءه قبل أن يحلّ محلّ أي شيء فعلي.")),
        ],
    },
]


CASE_STUDIES = [
    {
        'title': L(
            'Cleaning up five years of Odoo Studio changes for a distribution company',
            'Cómo ordenamos cinco años de cambios en Odoo Studio para una empresa de distribución',
            'ترتيب خمس سنوات من تغييرات Odoo Studio لشركة توزيع'),
        'client_summary': L(
            'Mid-size distribution company, Spain · Odoo 16',
            'Empresa de distribución mediana, España · Odoo 16',
            'شركة توزيع متوسطة الحجم، إسبانيا · Odoo 16'),
        'challenge': L(
            "After five years of organic growth, this company's Odoo system had accumulated dozens of Studio "
            "customizations layered on top of each other — fields nobody remembered the purpose of, automated "
            "actions that occasionally conflicted, and reports that broke every time the system was updated.\n"
            "Their internal team could keep daily operations running, but were afraid to touch anything for "
            "fear of breaking something else — and an upcoming Odoo upgrade made the situation urgent.",

            "Tras cinco años de crecimiento orgánico, el sistema Odoo de esta empresa había acumulado decenas de "
            "personalizaciones de Studio superpuestas: campos cuyo propósito nadie recordaba, acciones "
            "automatizadas que a veces entraban en conflicto e informes que se rompían con cada actualización.\n"
            "Su equipo interno podía mantener la operativa diaria, pero temía tocar nada por miedo a romper otra "
            "cosa, y una actualización de Odoo inminente hacía la situación urgente.",

            "بعد خمس سنوات من النمو التدريجي، تراكمت في نظام Odoo لدى هذه الشركة عشرات تخصيصات Studio المتراكبة — "
            "حقول لم يعد أحد يتذكّر الغرض منها، وإجراءات آلية تتعارض أحيانًا، وتقارير تتعطّل مع كل تحديث للنظام.\n"
            "كان فريقهم الداخلي قادرًا على إبقاء العمليات اليومية تسير، لكنه كان يخشى تعديل أي شيء خوفًا من كسر شيء "
            "آخر — وجعلت ترقية Odoo الوشيكة الأمر عاجلًا."),
        'approach': L(
            "We started with a full Health Check to map exactly what existed and why, separating critical "
            "business logic from unused leftovers. From there, we redesigned the necessary functionality as "
            "a small set of clean, version-controlled custom modules, validating each one against real "
            "business workflows before replacing the original Studio version.\n"
            "Throughout the project we worked closely with their internal team, documenting decisions so "
            "they could maintain the new setup confidently going forward.",

            "Empezamos con un diagnóstico completo para documentar con exactitud qué existía y por qué, separando "
            "la lógica de negocio crítica de los restos sin uso. A partir de ahí, rediseñamos la funcionalidad "
            "necesaria como un pequeño conjunto de módulos a medida limpios y versionados, validando cada uno con "
            "los flujos de trabajo reales antes de sustituir la versión original de Studio.\n"
            "Durante todo el proyecto trabajamos estrechamente con su equipo interno, documentando las decisiones "
            "para que pudieran mantener la nueva configuración con confianza.",

            "بدأنا بفحص فني كامل لتوثيق ما هو موجود ولماذا بدقّة، مع فصل منطق العمل الجوهري عن البقايا غير المستخدمة. "
            "ومن هناك أعدنا تصميم الوظائف الضرورية كمجموعة صغيرة من الوحدات المخصّصة النظيفة الخاضعة لإدارة "
            "الإصدارات، مع التحقّق من كلٍّ منها مقابل تدفّقات العمل الفعلية قبل استبدال نسخة Studio الأصلية.\n"
            "وطوال المشروع عملنا عن قرب مع فريقهم الداخلي، موثّقين القرارات لتمكينهم من صيانة الإعداد الجديد بثقة "
            "لاحقًا."),
        'results': L(
            "The company entered their Odoo upgrade with a system their team finally understood and trusted. "
            "Report errors dropped to zero, automation conflicts disappeared, and the internal team reported "
            "feeling confident making small changes themselves for the first time in years.",

            "La empresa afrontó su actualización de Odoo con un sistema que su equipo por fin entendía y en el que "
            "confiaba. Los errores en los informes desaparecieron, los conflictos de automatización se eliminaron y "
            "el equipo interno se sintió capaz de hacer pequeños cambios por sí mismo por primera vez en años.",

            "دخلت الشركة ترقية Odoo بنظام بات فريقها يفهمه ويثق به أخيرًا. اختفت أخطاء التقارير، وزالت تعارضات "
            "الأتمتة، وأفاد الفريق الداخلي بأنه شعر بالثقة في إجراء تغييرات صغيرة بنفسه لأول مرة منذ سنوات."),
        'order': 1,
        'meta_description': L(
            'How Bidatia helped a Spanish distribution company turn five years of fragile Odoo Studio customizations into clean, maintainable custom modules before a major upgrade.',
            'Cómo Bidatia ayudó a una empresa de distribución española a convertir cinco años de frágiles personalizaciones de Odoo Studio en módulos a medida limpios y mantenibles antes de una gran actualización.',
            'كيف ساعد Bidatia شركة توزيع إسبانية على تحويل خمس سنوات من تخصيصات Odoo Studio الهشّة إلى وحدات مخصّصة نظيفة وقابلة للصيانة قبل ترقية كبرى.'),
    },
    {
        'title': L(
            'Connecting a custom Django storefront to Odoo for real-time inventory sync',
            'Conexión de una tienda Django a medida con Odoo para sincronizar el inventario en tiempo real',
            'ربط متجر Django مخصّص بـ Odoo لمزامنة المخزون في الوقت الفعلي'),
        'client_summary': L(
            'E-commerce retailer, Gulf region · Odoo 17 + custom Django storefront',
            'Comercio electrónico, región del Golfo · Odoo 17 + tienda Django a medida',
            'متجر إلكتروني، منطقة الخليج · Odoo 17 + متجر Django مخصّص'),
        'challenge': L(
            "This retailer ran a custom Django storefront alongside Odoo for inventory and order management, "
            "but the two systems were only loosely connected through manual exports — leading to overselling, "
            "stock discrepancies, and frustrated customers during peak periods.\n"
            "They needed a reliable, real-time link between the storefront and Odoo without disrupting "
            "either system's daily operations.",

            "Este comercio tenía una tienda Django a medida junto a Odoo para la gestión de inventario y pedidos, "
            "pero ambos sistemas estaban conectados de forma poco fiable mediante exportaciones manuales, lo que "
            "provocaba sobreventa, descuadres de stock y clientes molestos en los picos de demanda.\n"
            "Necesitaban un enlace fiable y en tiempo real entre la tienda y Odoo sin interrumpir la operativa "
            "diaria de ninguno de los dos sistemas.",

            "كان هذا المتجر يشغّل متجر Django مخصّصًا إلى جانب Odoo لإدارة المخزون والطلبات، لكن النظامين كانا مرتبطين "
            "ارتباطًا ضعيفًا عبر تصدير يدوي — ما أدّى إلى بيع يفوق المتوفّر، وتفاوت في المخزون، وإحباط للعملاء في "
            "أوقات الذروة.\n"
            "كانوا بحاجة إلى رابط موثوق وفوري بين المتجر و Odoo دون تعطيل العمليات اليومية لأيٍّ من النظامين."),
        'approach': L(
            "We designed a structured API integration covering inventory levels, order creation, and status "
            "updates between the Django storefront and Odoo, with clear rules for what should sync, how "
            "often, and how to handle conflicts or failures gracefully.\n"
            "The integration was built and tested in a staging environment against realistic order volumes "
            "before being rolled out gradually, with monitoring in place from day one.",

            "Diseñamos una integración de API estructurada que abarcaba niveles de inventario, creación de pedidos "
            "y actualizaciones de estado entre la tienda Django y Odoo, con reglas claras sobre qué sincronizar, "
            "con qué frecuencia y cómo gestionar conflictos o fallos con elegancia.\n"
            "La integración se desarrolló y se probó en un entorno de pruebas con volúmenes de pedidos realistas "
            "antes de desplegarse de forma gradual, con monitorización desde el primer día.",

            "صمّمنا تكامل API منظَّمًا يغطّي مستويات المخزون، وإنشاء الطلبات، وتحديثات الحالة بين متجر Django و Odoo، "
            "مع قواعد واضحة لما يجب مزامنته، وعدد مرّاته، وكيفية التعامل مع التعارضات أو الأعطال بسلاسة.\n"
            "بُني التكامل واختُبر في بيئة اختبار مقابل أحجام طلبات واقعية قبل طرحه تدريجيًا، مع وجود مراقبة منذ اليوم "
            "الأول."),
        'results': L(
            "Stock discrepancies and overselling incidents dropped dramatically within the first month. "
            "The retailer's team no longer needed to manually reconcile inventory between systems, freeing "
            "up hours each week — and Bidatia continues to support the integration through a monthly support plan.",

            "Los descuadres de stock y los casos de sobreventa se redujeron drásticamente en el primer mes. El "
            "equipo del comercio dejó de tener que cuadrar manualmente el inventario entre sistemas, ahorrando "
            "horas cada semana, y Bidatia sigue dando soporte a la integración mediante un plan de soporte mensual.",

            "انخفض تفاوت المخزون وحالات البيع الزائد بشكل كبير خلال الشهر الأول. ولم يعد فريق المتجر بحاجة إلى تسوية "
            "المخزون يدويًا بين النظامين، ما وفّر ساعات كل أسبوع — ويواصل Bidatia دعم التكامل عبر باقة دعم شهري."),
        'order': 2,
        'meta_description': L(
            'A case study on how Bidatia built a real-time Django-Odoo integration for a Gulf-region e-commerce retailer, eliminating overselling and manual inventory reconciliation.',
            'Un caso de éxito sobre cómo Bidatia construyó una integración Django-Odoo en tiempo real para un comercio electrónico de la región del Golfo, eliminando la sobreventa y el cuadre manual del inventario.',
            'دراسة حالة حول كيفية بناء Bidatia تكامل Django-Odoo فوريًا لمتجر إلكتروني في منطقة الخليج، ما أنهى البيع الزائد والتسوية اليدوية للمخزون.'),
    },
    {
        'title': L('Auditing years of Odoo Studio changes at a freight-forwarding company',
                   'Auditoría de años de cambios en Odoo Studio en una empresa de transporte de mercancías',
                   'تدقيق سنوات من تغييرات Odoo Studio لدى شركة شحن دولي'),
        'client_summary': L('Freight forwarding & import/export · Odoo',
                            'Transporte de mercancías e importación/exportación · Odoo',
                            'الشحن الدولي والاستيراد/التصدير · Odoo'),
        'challenge': L(
            "After years of growth, this freight-forwarding company had accumulated a large layer of Odoo Studio "
            "customizations on top of its core operations — custom fields, server actions, automated rules and "
            "reports added over time to handle shipments, documents and invoicing.\n"
            "The setup still worked day to day, but it had become hard to audit and risky to change, and the team "
            "wanted to understand exactly what was there before considering a future migration.",
            "Tras años de crecimiento, esta empresa de transporte de mercancías había acumulado una gran capa de "
            "personalizaciones de Odoo Studio sobre su operativa principal: campos a medida, acciones de servidor, "
            "reglas automatizadas e informes añadidos con el tiempo para gestionar envíos, documentos y facturación.\n"
            "El sistema seguía funcionando en el día a día, pero se había vuelto difícil de auditar y arriesgado de "
            "modificar, y el equipo quería entender exactamente qué había antes de plantear una futura migración.",
            "بعد سنوات من النمو، تراكمت لدى شركة الشحن هذه طبقة كبيرة من تخصيصات Odoo Studio فوق عملياتها الأساسية: "
            "حقول مخصّصة، وإجراءات خادم، وقواعد آلية، وتقارير أُضيفت مع الوقت لإدارة الشحنات والمستندات والفوترة.\n"
            "كان النظام لا يزال يعمل يوميًا، لكنه أصبح صعب التدقيق ومحفوفًا بالمخاطر عند التعديل، وأراد الفريق أن يفهم "
            "بدقّة ما هو موجود قبل التفكير في ترقية مستقبلية."),
        'approach': L(
            "We carried out a structured audit of the Studio customizations and mapped the real operational flow "
            "end to end — from CRM and shipment handling to documents and invoicing — documenting what each custom "
            "field, action and report actually did and which parts were business-critical versus unused.\n"
            "From that map we proposed a cleaner, module-based direction: which logic should become proper "
            "version-controlled custom modules, which Studio changes could be retired, and a realistic sequence to "
            "prepare the system for a future migration.\n"
            "Delivered: a documented inventory of the customizations, a CRM → shipment → documents → invoicing "
            "process map, and a prioritized cleanup-and-migration roadmap. Technologies: Odoo (Studio + custom "
            "modules), Python and PostgreSQL.",
            "Realizamos una auditoría estructurada de las personalizaciones de Studio y mapeamos el flujo operativo "
            "real de principio a fin —desde el CRM y la gestión de envíos hasta los documentos y la facturación—, "
            "documentando qué hacía realmente cada campo, acción e informe y qué partes eran críticas frente a las "
            "que ya no se usaban.\n"
            "A partir de ese mapa propusimos una dirección más limpia basada en módulos: qué lógica debía "
            "convertirse en módulos a medida versionados, qué cambios de Studio podían retirarse y una secuencia "
            "realista para preparar el sistema de cara a una futura migración.\n"
            "Entregado: un inventario documentado de las personalizaciones, un mapa de procesos CRM → envío → "
            "documentos → facturación y una hoja de ruta priorizada de limpieza y migración. Tecnologías: Odoo "
            "(Studio + módulos a medida), Python y PostgreSQL.",
            "أجرينا تدقيقًا منظَّمًا لتخصيصات Studio ورسمنا مسار العمل الفعلي من البداية إلى النهاية — من إدارة "
            "العملاء والشحنات إلى المستندات والفوترة — موثّقين ما يفعله فعلًا كل حقل وإجراء وتقرير، وأي الأجزاء جوهري "
            "مقابل غير المستخدَم.\n"
            "وانطلاقًا من تلك الخريطة اقترحنا اتجاهًا أنظف قائمًا على الوحدات: أي منطق ينبغي تحويله إلى وحدات مخصّصة "
            "خاضعة لإدارة الإصدارات، وأي تغييرات Studio يمكن الاستغناء عنها، وتسلسلًا واقعيًا لتهيئة النظام لترقية "
            "مستقبلية.\n"
            "ما سُلّم: جرد موثَّق للتخصيصات، وخريطة عمليات «العميل ← الشحنة ← المستندات ← الفوترة»، وخارطة طريق مرتّبة "
            "للتنظيف والترقية. التقنيات: Odoo (Studio + وحدات مخصّصة)، وPython، وPostgreSQL."),
        'results': L(
            "The company moved from an opaque, fragile setup to a clear picture of its own system — what exists, "
            "why, and what to do next. The documentation made the eventual migration far less risky and gave the "
            "internal team the confidence to plan changes deliberately rather than avoid them.\n"
            "Related services: Odoo Studio Cleanup, Odoo Migration Assessment and Odoo Health Check.",
            "La empresa pasó de una configuración opaca y frágil a una imagen clara de su propio sistema: qué "
            "existe, por qué y qué hacer a continuación. La documentación redujo notablemente el riesgo de la "
            "futura migración y dio al equipo interno la confianza para planificar los cambios con criterio en "
            "lugar de evitarlos.\n"
            "Servicios relacionados: limpieza de Odoo Studio, evaluación de migración de Odoo y diagnóstico técnico "
            "de Odoo.",
            "انتقلت الشركة من إعداد غامض وهشّ إلى صورة واضحة لنظامها: ما الموجود، ولماذا، وما الخطوة التالية. وقلّل "
            "التوثيق من مخاطر الترقية المقبلة بشكل ملحوظ، ومنح الفريق الداخلي الثقة لتخطيط التغييرات بوعي بدل "
            "تجنّبها.\n"
            "خدمات ذات صلة: تنظيف Odoo Studio، وتقييم ترقية Odoo، والفحص الفني لنظام Odoo."),
        'order': 3,
        'meta_description': L(
            'How Bidatia audited years of Odoo Studio customizations at a freight-forwarding company and prepared a clear, lower-risk path toward a future migration.',
            'Cómo Bidatia auditó años de personalizaciones de Odoo Studio en una empresa de transporte de mercancías y preparó un camino claro y de menor riesgo hacia una futura migración.',
            'كيف دقّق Bidatia سنوات من تخصيصات Odoo Studio لدى شركة شحن دولي، وهيّأ مسارًا واضحًا وأقلّ مخاطرة نحو ترقية مستقبلية.'),
    },
    {
        'title': L('Automating messy Excel cost reports for a logistics team',
                   'Automatización de informes de costes en Excel para un equipo de logística',
                   'أتمتة تقارير التكاليف المبعثرة على Excel لفريق لوجستي'),
        'client_summary': L('Logistics & international operations · Excel automation',
                            'Logística y operaciones internacionales · automatización de Excel',
                            'اللوجستيات والعمليات الدولية · أتمتة Excel'),
        'challenge': L(
            "The operations team ran much of its cost and shipment reporting through Excel files whose templates "
            "kept changing — manual columns, supplier fees and customs concepts were re-entered and re-arranged by "
            "hand for every report.\n"
            "This was slow, easy to get wrong, and painful to repeat each time a template or a charge structure "
            "changed.",
            "El equipo de operaciones gestionaba gran parte de sus informes de costes y envíos con archivos de "
            "Excel cuyas plantillas cambiaban constantemente: columnas manuales, tarifas de proveedores y conceptos "
            "de aduana que se reintroducían y reorganizaban a mano en cada informe.\n"
            "Era lento, propenso a errores y agotador de repetir cada vez que cambiaba una plantilla o una "
            "estructura de cargos.",
            "كان فريق العمليات ينجز جزءًا كبيرًا من تقارير التكاليف والشحنات عبر ملفات Excel تتغيّر قوالبها باستمرار: "
            "أعمدة يدوية، ورسوم موردين، ومفاهيم جمركية تُعاد إدخالها وترتيبها يدويًا في كل تقرير.\n"
            "كان ذلك بطيئًا وعرضة للخطأ ومرهقًا في كل مرة يتغيّر فيها قالب أو هيكل رسوم."),
        'approach': L(
            "We built and refined automation logic that normalizes the Excel output into a consistent structure, "
            "updates the charge columns automatically, and tolerates template changes without breaking — so the "
            "same report no longer had to be rebuilt by hand.\n"
            "Delivered: reusable automation that standardizes the spreadsheets and reduces repetitive editing. "
            "Technologies: Python and spreadsheet automation, designed to fit the team's existing Excel-based "
            "workflow.",
            "Construimos y refinamos una lógica de automatización que normaliza la salida de Excel en una "
            "estructura coherente, actualiza las columnas de cargos automáticamente y tolera los cambios de "
            "plantilla sin romperse, de modo que el mismo informe ya no había que rehacerlo a mano.\n"
            "Entregado: una automatización reutilizable que estandariza las hojas de cálculo y reduce la edición "
            "repetitiva. Tecnologías: Python y automatización de hojas de cálculo, adaptadas al flujo de trabajo "
            "en Excel existente del equipo.",
            "بنينا وطوّرنا منطق أتمتة يوحّد مخرجات Excel في بنية متّسقة، ويحدّث أعمدة الرسوم تلقائيًا، ويتحمّل تغييرات "
            "القوالب دون أن ينكسر — فلم يعد يلزم إعادة بناء التقرير نفسه يدويًا.\n"
            "ما سُلّم: أتمتة قابلة لإعادة الاستخدام توحّد الجداول وتقلّل التحرير المتكرّر. التقنيات: Python وأتمتة "
            "الجداول، مصمّمة لتلائم سير عمل الفريق القائم على Excel."),
        'results': L(
            "The team spent far less time massaging spreadsheets and more time on the actual operations, with "
            "reports that came out consistent run after run. The logic was built to absorb template changes "
            "instead of breaking on them.\n"
            "Related services: Odoo Automation & Server Actions Review, Django/Odoo Integration and custom workflow "
            "automation.",
            "El equipo dedicó mucho menos tiempo a manipular hojas de cálculo y más a la operativa real, con "
            "informes que salían coherentes una y otra vez. La lógica se diseñó para absorber los cambios de "
            "plantilla en lugar de fallar con ellos.\n"
            "Servicios relacionados: revisión de automatizaciones y acciones de servidor de Odoo, integración "
            "Django/Odoo y automatización de flujos a medida.",
            "أمضى الفريق وقتًا أقلّ بكثير في معالجة الجداول ووقتًا أكثر في العمليات الفعلية، مع تقارير تخرج متّسقة "
            "مرّة بعد أخرى. وصُمّم المنطق ليستوعب تغييرات القوالب بدل أن يتعطّل بها.\n"
            "خدمات ذات صلة: مراجعة الأتمتة وإجراءات الخادم في Odoo، وتكامل Django/Odoo، وأتمتة سير العمل المخصّصة."),
        'order': 4,
        'meta_description': L(
            'How Bidatia automated changing Excel cost and shipment reports for a logistics team, cutting repetitive manual editing and keeping outputs consistent.',
            'Cómo Bidatia automatizó los cambiantes informes de costes y envíos en Excel de un equipo de logística, reduciendo la edición manual repetitiva y manteniendo resultados coherentes.',
            'كيف أتمتت Bidatia تقارير التكاليف والشحنات المتغيّرة على Excel لفريق لوجستي، فقلّلت التحرير اليدوي المتكرّر وحافظت على اتّساق المخرجات.'),
    },
    {
        'title': L('An ERP foundation for a professional training institute',
                   'Una base ERP para un instituto de formación profesional',
                   'أساس نظام ERP لمعهد تدريب مهني'),
        'client_summary': L('Professional training & education · Odoo (cloud)',
                            'Formación profesional y educación · Odoo (en la nube)',
                            'التدريب المهني والتعليم · Odoo (سحابي)'),
        'challenge': L(
            "A training institute was managing registrations, courses and finance-related tracking across "
            "disconnected spreadsheets and manual notes, which made day-to-day operations hard to coordinate and "
            "easy to lose track of.\n"
            "They needed one structured system instead of scattered files.",
            "Un instituto de formación gestionaba las inscripciones, los cursos y el seguimiento financiero en "
            "hojas de cálculo inconexas y notas manuales, lo que dificultaba coordinar el día a día y era fácil "
            "perder el hilo.\n"
            "Necesitaban un único sistema estructurado en lugar de archivos dispersos.",
            "كان معهد تدريب يدير التسجيلات والدورات والمتابعة المالية عبر جداول بيانات منفصلة وملاحظات يدوية، ما "
            "صعّب تنسيق العمل اليومي وسهّل ضياع المعلومات.\n"
            "كانوا بحاجة إلى نظام واحد منظَّم بدل ملفات متفرّقة."),
        'approach': L(
            "We designed ERP workflows around how the institute actually runs — course and registration "
            "management, finance-related tracking and the internal operational steps in between — and deployed it "
            "to the cloud so the team could work from one place.\n"
            "Delivered: configured Odoo workflows for training and registration, finance-related tracking, a cloud "
            "deployment and hands-on user training. Technologies: Odoo, PostgreSQL and a cloud server setup.",
            "Diseñamos flujos de trabajo ERP en torno a cómo funciona realmente el instituto —gestión de cursos e "
            "inscripciones, seguimiento financiero y los pasos operativos internos intermedios— y lo desplegamos "
            "en la nube para que el equipo trabajara desde un único lugar.\n"
            "Entregado: flujos de Odoo configurados para formación e inscripciones, seguimiento financiero, "
            "despliegue en la nube y formación práctica a los usuarios. Tecnologías: Odoo, PostgreSQL y un servidor "
            "en la nube.",
            "صمّمنا تدفّقات عمل ERP حول الطريقة التي يعمل بها المعهد فعلًا — إدارة الدورات والتسجيلات، والمتابعة "
            "المالية، والخطوات التشغيلية الداخلية بينها — ونشرناه سحابيًا ليعمل الفريق من مكان واحد.\n"
            "ما سُلّم: تدفّقات Odoo مُعدّة للتدريب والتسجيل، ومتابعة مالية، ونشر سحابي، وتدريب عملي للمستخدمين. "
            "التقنيات: Odoo وPostgreSQL وخادم سحابي."),
        'results': L(
            "The institute replaced scattered manual processes with a single, structured system, making "
            "registrations and operations easier to follow and maintain. The user training helped the team adopt "
            "it with confidence.\n"
            "Related services: Custom Odoo Module Development, Odoo CRM & Sales Workflow Optimization and Monthly "
            "Odoo Support.",
            "El instituto sustituyó procesos manuales dispersos por un único sistema estructurado, lo que hizo las "
            "inscripciones y la operativa más fáciles de seguir y mantener. La formación ayudó al equipo a "
            "adoptarlo con confianza.\n"
            "Servicios relacionados: desarrollo de módulos a medida para Odoo, optimización del flujo de CRM y "
            "ventas, y soporte mensual de Odoo.",
            "استبدل المعهد العمليات اليدوية المتفرّقة بنظام واحد منظَّم، فأصبحت التسجيلات والعمليات أسهل في المتابعة "
            "والصيانة. وساعد التدريب الفريق على تبنّيه بثقة.\n"
            "خدمات ذات صلة: تطوير وحدات Odoo مخصّصة، وتحسين سير عمل CRM والمبيعات، ودعم Odoo الشهري."),
        'order': 5,
        'meta_description': L(
            'How Bidatia gave a professional training institute a structured Odoo ERP for registrations, courses and finance-related tracking, replacing scattered spreadsheets.',
            'Cómo Bidatia dotó a un instituto de formación profesional de un ERP en Odoo estructurado para inscripciones, cursos y seguimiento financiero, sustituyendo hojas de cálculo dispersas.',
            'كيف زوّد Bidatia معهد تدريب مهني بنظام Odoo ERP منظَّم للتسجيلات والدورات والمتابعة المالية، بديلًا عن جداول البيانات المتفرّقة.'),
    },
    {
        'title': L('Bringing structure to operations at a printing and production company',
                   'Dar estructura a las operaciones de una empresa de impresión y producción',
                   'هيكلة العمليات في شركة طباعة وإنتاج'),
        'client_summary': L('Printing, production & manufacturing · Odoo',
                            'Impresión, producción y fabricación · Odoo',
                            'الطباعة والإنتاج والتصنيع · Odoo'),
        'challenge': L(
            "A printing and production company needed better control over its operational records, customer "
            "requests and finance-related workflows, with clearer visibility into what was happening across the "
            "business.\n"
            "Much of this lived in manual records that were hard to consolidate or review.",
            "Una empresa de impresión y producción necesitaba un mejor control de sus registros operativos, las "
            "solicitudes de clientes y los flujos financieros, con una visibilidad más clara de lo que ocurría en "
            "el negocio.\n"
            "Gran parte de esto vivía en registros manuales difíciles de consolidar o revisar.",
            "احتاجت شركة طباعة وإنتاج إلى تحكّم أفضل في سجلّاتها التشغيلية وطلبات العملاء والتدفّقات المالية، مع رؤية "
            "أوضح لما يجري في النشاط.\n"
            "كان جزء كبير من ذلك في سجلّات يدوية يصعب تجميعها أو مراجعتها."),
        'approach': L(
            "We implemented a clear ERP process structure and configured the workflows around the company's "
            "operations — customer requests, operational tracking and accounting-related steps — then trained the "
            "team to run it day to day.\n"
            "Delivered: a configured Odoo process structure, operational and accounting-related tracking, and user "
            "training. Technologies: Odoo and PostgreSQL.",
            "Implementamos una estructura de procesos ERP clara y configuramos los flujos en torno a la operativa "
            "de la empresa —solicitudes de clientes, seguimiento operativo y pasos relacionados con contabilidad— "
            "y formamos al equipo para gestionarla en el día a día.\n"
            "Entregado: una estructura de procesos en Odoo configurada, seguimiento operativo y contable, y "
            "formación de usuarios. Tecnologías: Odoo y PostgreSQL.",
            "طبّقنا بنية عمليات ERP واضحة، وأعددنا التدفّقات حول عمليات الشركة — طلبات العملاء، والمتابعة التشغيلية، "
            "والخطوات المتعلّقة بالمحاسبة — ودرّبنا الفريق على تشغيلها يوميًا.\n"
            "ما سُلّم: بنية عمليات مُعدّة في Odoo، ومتابعة تشغيلية ومحاسبية، وتدريب للمستخدمين. التقنيات: Odoo "
            "وPostgreSQL."),
        'results': L(
            "The company gained a more organized, visible operation: records centralized in one place and "
            "workflows that were easier to follow and maintain than the previous manual approach.\n"
            "Related services: Odoo Health Check, Custom Odoo Module Development and the Odoo Accounting & "
            "Invoicing Process Review.",
            "La empresa ganó una operativa más organizada y visible: registros centralizados en un solo lugar y "
            "flujos más fáciles de seguir y mantener que el enfoque manual anterior.\n"
            "Servicios relacionados: diagnóstico técnico de Odoo, desarrollo de módulos a medida y revisión de "
            "procesos de contabilidad y facturación.",
            "حصلت الشركة على عمليات أكثر تنظيمًا ووضوحًا: سجلّات مركزية في مكان واحد، وتدفّقات أسهل في المتابعة "
            "والصيانة من النهج اليدوي السابق.\n"
            "خدمات ذات صلة: الفحص الفني لـ Odoo، وتطوير وحدات مخصّصة، ومراجعة عمليات المحاسبة والفوترة."),
        'order': 6,
        'meta_description': L(
            'How Bidatia structured operations for a printing and production company in Odoo, centralizing records and making finance-related workflows easier to maintain.',
            'Cómo Bidatia estructuró en Odoo las operaciones de una empresa de impresión y producción, centralizando registros y facilitando el mantenimiento de los flujos financieros.',
            'كيف هيكل Bidatia عمليات شركة طباعة وإنتاج في Odoo، فمركز السجلّات وسهّل صيانة التدفّقات المالية.'),
    },
    {
        'title': L('Clearer daily operations for a food-service business',
                   'Operaciones diarias más claras para un negocio de restauración',
                   'عمليات يومية أوضح لنشاط في قطاع المطاعم'),
        'client_summary': L('Restaurant & food service · operations reporting',
                            'Restauración y servicios de comida · informes operativos',
                            'المطاعم وخدمات الطعام · تقارير العمليات'),
        'challenge': L(
            "A food-service business needed better daily visibility over staff attendance, delivery operations, "
            "expenses and operational controls, which were spread across separate tools and manual checks.\n"
            "Without consolidated reporting it was hard to see how each day, week and month was really going.",
            "Un negocio de restauración necesitaba mejor visibilidad diaria sobre la asistencia del personal, las "
            "operaciones de reparto, los gastos y los controles operativos, repartidos entre herramientas "
            "separadas y comprobaciones manuales.\n"
            "Sin informes consolidados era difícil ver cómo iba realmente cada día, semana y mes.",
            "احتاج نشاط في قطاع المطاعم إلى رؤية يومية أفضل لحضور الموظفين وعمليات التوصيل والمصروفات والضوابط "
            "التشغيلية، وكانت موزّعة بين أدوات منفصلة وفحوص يدوية.\n"
            "ومن دون تقارير موحّدة كان من الصعب معرفة كيف يسير كل يوم وأسبوع وشهر فعلًا."),
        'approach': L(
            "We built and supported operational reporting workflows that bring daily, weekly and monthly "
            "visibility together — covering HR attendance, delivery handling and cost tracking — so the team could "
            "review operations from a clearer, more consolidated view.\n"
            "Delivered: operational reporting workflows, attendance and delivery tracking, and cost visibility. "
            "Technologies: Odoo / Python-based automation tailored to the business's operations.",
            "Construimos y dimos soporte a flujos de informes operativos que reúnen la visibilidad diaria, semanal "
            "y mensual —asistencia de RR. HH., gestión de repartos y seguimiento de costes— para que el equipo "
            "pudiera revisar la operativa desde una vista más clara y consolidada.\n"
            "Entregado: flujos de informes operativos, seguimiento de asistencia y repartos, y visibilidad de "
            "costes. Tecnologías: automatización basada en Odoo / Python adaptada a la operativa del negocio.",
            "بنينا ودعمنا تدفّقات تقارير تشغيلية تجمع الرؤية اليومية والأسبوعية والشهرية — حضور الموارد البشرية، "
            "وإدارة التوصيل، وتتبّع التكاليف — ليتمكّن الفريق من مراجعة العمليات من منظور أوضح وأكثر تجميعًا.\n"
            "ما سُلّم: تدفّقات تقارير تشغيلية، وتتبّع الحضور والتوصيل، ووضوح التكاليف. التقنيات: أتمتة قائمة على Odoo "
            "/ Python مصمّمة لعمليات النشاط."),
        'results': L(
            "The business gained clearer day-to-day visibility and a more reliable way to review attendance, "
            "deliveries and costs, helping the team spot issues sooner.\n"
            "Related services: business automation, an Odoo operations review and Monthly Odoo Support.",
            "El negocio ganó una visibilidad diaria más clara y una forma más fiable de revisar la asistencia, los "
            "repartos y los costes, ayudando al equipo a detectar problemas antes.\n"
            "Servicios relacionados: automatización de negocio, una revisión de operaciones de Odoo y soporte "
            "mensual de Odoo.",
            "حصل النشاط على رؤية يومية أوضح وطريقة أكثر موثوقية لمراجعة الحضور والتوصيل والتكاليف، ما ساعد الفريق على "
            "اكتشاف المشكلات مبكرًا.\n"
            "خدمات ذات صلة: أتمتة الأعمال، ومراجعة عمليات Odoo، ودعم Odoo الشهري."),
        'order': 7,
        'meta_description': L(
            'How Bidatia gave a food-service business clearer daily, weekly and monthly visibility over attendance, deliveries and costs through structured operational reporting.',
            'Cómo Bidatia dio a un negocio de restauración una visibilidad diaria, semanal y mensual más clara sobre asistencia, repartos y costes mediante informes operativos estructurados.',
            'كيف منح Bidatia نشاطًا في قطاع المطاعم رؤية يومية وأسبوعية وشهرية أوضح للحضور والتوصيل والتكاليف عبر تقارير تشغيلية منظَّمة.'),
    },
    {
        'title': L('A structured records platform for a humanitarian organization',
                   'Una plataforma de registros estructurados para una organización humanitaria',
                   'منصّة سجلّات منظَّمة لمنظمة إنسانية'),
        'client_summary': L('Humanitarian / NGO operations · Django platform',
                            'Operaciones humanitarias / ONG · plataforma Django',
                            'العمليات الإنسانية / منظمة غير حكومية · منصّة Django'),
        'challenge': L(
            "A humanitarian organization needed to manage sensitive person records, related companion data, "
            "dynamic documents, validations and exports in a structured, controlled way — something spreadsheets "
            "could not handle safely or consistently.\n"
            "The data was sensitive, so structure, validation and careful handling mattered as much as the "
            "features themselves.",
            "Una organización humanitaria necesitaba gestionar registros sensibles de personas, datos de "
            "acompañantes, documentos dinámicos, validaciones y exportaciones de forma estructurada y controlada, "
            "algo que las hojas de cálculo no podían manejar con seguridad ni coherencia.\n"
            "Los datos eran sensibles, así que la estructura, la validación y el tratamiento cuidadoso importaban "
            "tanto como las propias funciones.",
            "احتاجت منظمة إنسانية إلى إدارة سجلّات حسّاسة للأشخاص، وبيانات المرافقين، ومستندات ديناميكية، وعمليات "
            "تحقّق وتصدير بطريقة منظَّمة ومُتحكَّم بها — وهو ما لم تستطع الجداول التعامل معه بأمان واتّساق.\n"
            "كانت البيانات حسّاسة، لذا كانت البنية والتحقّق والتعامل الدقيق بأهمية الميزات نفسها."),
        'approach': L(
            "We built a Django-based platform for structured records, with document generation, validation logic "
            "and export workflows designed around the organization's real processes — keeping the data organized "
            "and the handling consistent.\n"
            "Delivered: a Django records platform with dynamic document generation, validation rules and "
            "structured exports. Technologies: Python, Django and PostgreSQL.",
            "Construimos una plataforma basada en Django para registros estructurados, con generación de "
            "documentos, lógica de validación y flujos de exportación diseñados en torno a los procesos reales de "
            "la organización, manteniendo los datos organizados y el tratamiento coherente.\n"
            "Entregado: una plataforma de registros en Django con generación dinámica de documentos, reglas de "
            "validación y exportaciones estructuradas. Tecnologías: Python, Django y PostgreSQL.",
            "بنينا منصّة قائمة على Django للسجلّات المنظَّمة، مع توليد المستندات، ومنطق التحقّق، وتدفّقات التصدير، "
            "مصمّمة حول عمليات المنظمة الفعلية، مع إبقاء البيانات منظَّمة والتعامل متّسقًا.\n"
            "ما سُلّم: منصّة سجلّات بـ Django مع توليد مستندات ديناميكي، وقواعد تحقّق، وتصدير منظَّم. التقنيات: "
            "Python وDjango وPostgreSQL."),
        'results': L(
            "The organization moved from fragile spreadsheets to a structured platform that kept its sensitive "
            "records organized, validated and easier to work with, with documents and exports generated "
            "consistently.\n"
            "Related services: Django/Python development, business automation and API/data workflow design.",
            "La organización pasó de hojas de cálculo frágiles a una plataforma estructurada que mantenía sus "
            "registros sensibles organizados, validados y más fáciles de manejar, con documentos y exportaciones "
            "generados de forma coherente.\n"
            "Servicios relacionados: desarrollo en Django/Python, automatización de negocio y diseño de flujos de "
            "datos/API.",
            "انتقلت المنظمة من جداول هشّة إلى منصّة منظَّمة أبقت سجلّاتها الحسّاسة منظَّمة ومُتحقَّقًا منها وأسهل في "
            "التعامل، مع توليد المستندات والتصدير باتّساق.\n"
            "خدمات ذات صلة: تطوير Django/Python، وأتمتة الأعمال، وتصميم تدفّقات البيانات/الـ API."),
        'order': 8,
        'meta_description': L(
            'How Bidatia built a Django platform for a humanitarian organization to manage sensitive records, dynamic documents, validations and structured exports.',
            'Cómo Bidatia construyó una plataforma en Django para que una organización humanitaria gestionara registros sensibles, documentos dinámicos, validaciones y exportaciones estructuradas.',
            'كيف بنى Bidatia منصّة Django لمنظمة إنسانية لإدارة السجلّات الحسّاسة والمستندات الديناميكية وعمليات التحقّق والتصدير المنظَّم.'),
    },
    {
        'title': L('Planning the technical foundation for a retail e-commerce platform',
                   'Diseño de la base técnica para una plataforma de comercio electrónico',
                   'تصميم الأساس التقني لمنصّة تجارة إلكترونية'),
        'client_summary': L('Retail & e-commerce · architecture & integration',
                            'Comercio minorista y e-commerce · arquitectura e integración',
                            'التجزئة والتجارة الإلكترونية · معمارية وتكامل'),
        'challenge': L(
            "A retail e-commerce project needed a practical technical foundation for product sales, order flow, "
            "payment integration and delivery/courier integration — with room to scale operationally later.\n"
            "The priority was a solid, realistic architecture rather than a rushed build.",
            "Un proyecto de comercio electrónico necesitaba una base técnica práctica para la venta de productos, "
            "el flujo de pedidos, la integración de pagos y la integración con mensajería/reparto, con margen para "
            "escalar la operativa más adelante.\n"
            "La prioridad era una arquitectura sólida y realista, no una construcción apresurada.",
            "احتاج مشروع تجارة إلكترونية إلى أساس تقني عملي لبيع المنتجات، وتدفّق الطلبات، وتكامل المدفوعات، "
            "والتكامل مع خدمات التوصيل، مع إمكانية التوسّع تشغيليًا لاحقًا.\n"
            "كانت الأولوية لمعمارية متينة وواقعية، لا لبناء متسرّع."),
        'approach': L(
            "We designed the architecture for the e-commerce workflow end to end — product structure, order flow, "
            "payment logic, delivery/courier integration and the back-office processes behind them — so the "
            "technical foundation matched how the business would actually operate.\n"
            "Delivered: an e-commerce architecture and integration plan covering products, payments, delivery and "
            "back-office workflow. Technologies: Django/Odoo and API integrations.",
            "Diseñamos la arquitectura del flujo de comercio electrónico de principio a fin —estructura de "
            "productos, flujo de pedidos, lógica de pagos, integración con mensajería/reparto y los procesos de "
            "back-office detrás— para que la base técnica encajara con cómo operaría realmente el negocio.\n"
            "Entregado: una arquitectura de e-commerce y un plan de integración que cubren productos, pagos, "
            "reparto y flujo de back-office. Tecnologías: Django/Odoo e integraciones de API.",
            "صمّمنا معمارية تدفّق التجارة الإلكترونية من البداية إلى النهاية — بنية المنتجات، وتدفّق الطلبات، ومنطق "
            "المدفوعات، والتكامل مع التوصيل، وعمليات المكتب الخلفي خلفها — لتلائم الأساسُ التقني الطريقةَ التي سيعمل "
            "بها النشاط فعلًا.\n"
            "ما سُلّم: معمارية تجارة إلكترونية وخطة تكامل تغطّي المنتجات والمدفوعات والتوصيل وسير المكتب الخلفي. "
            "التقنيات: Django/Odoo وتكاملات الـ API."),
        'results': L(
            "The project gained a clear, practical technical direction it could build on, with the key integration "
            "points (payments, delivery, back-office) planned deliberately instead of improvised.\n"
            "Related services: Django/Odoo Integration, API integration and e-commerce process automation.",
            "El proyecto obtuvo una dirección técnica clara y práctica sobre la que construir, con los puntos clave "
            "de integración (pagos, reparto, back-office) planificados con criterio en lugar de improvisados.\n"
            "Servicios relacionados: integración Django/Odoo, integración de API y automatización de procesos de "
            "e-commerce.",
            "حصل المشروع على اتجاه تقني واضح وعملي يُبنى عليه، مع تخطيط نقاط التكامل الأساسية (المدفوعات، والتوصيل، "
            "والمكتب الخلفي) بوعي بدل الارتجال.\n"
            "خدمات ذات صلة: تكامل Django/Odoo، وتكامل الـ API، وأتمتة عمليات التجارة الإلكترونية."),
        'order': 9,
        'meta_description': L(
            'How Bidatia planned the technical foundation of a retail e-commerce platform — product structure, payments, delivery integration and back-office workflow.',
            'Cómo Bidatia planificó la base técnica de una plataforma de comercio electrónico: estructura de productos, pagos, integración de reparto y flujo de back-office.',
            'كيف خطّط Bidatia الأساس التقني لمنصّة تجارة إلكترونية: بنية المنتجات، والمدفوعات، وتكامل التوصيل، وسير المكتب الخلفي.'),
    },
    {
        'title': L('Custom invoice tax presentation without breaking Odoo accounting',
                   'Presentación fiscal personalizada en facturas sin romper la contabilidad de Odoo',
                   'عرض ضريبي مخصّص في الفواتير دون كسر محاسبة Odoo'),
        'client_summary': L('Accounting & finance operations · Odoo customization',
                            'Contabilidad y operaciones financieras · personalización de Odoo',
                            'المحاسبة والعمليات المالية · تخصيص Odoo'),
        'challenge': L(
            "The business needed invoice logic that supported a more detailed tax presentation for accounting "
            "review, without disturbing Odoo's standard accounting flow — a common but delicate requirement.\n"
            "The challenge was adding the extra tax-column detail while keeping standard invoice behavior intact.",
            "El negocio necesitaba una lógica de facturas que soportara una presentación fiscal más detallada para "
            "la revisión contable, sin alterar el flujo contable estándar de Odoo, un requisito habitual pero "
            "delicado.\n"
            "El reto era añadir el detalle adicional de columnas de impuestos manteniendo intacto el "
            "comportamiento estándar de las facturas.",
            "احتاج النشاط إلى منطق فواتير يدعم عرضًا ضريبيًا أكثر تفصيلًا لأغراض المراجعة المحاسبية، دون المساس "
            "بتدفّق المحاسبة القياسي في Odoo — وهو مطلب شائع لكنه حسّاس.\n"
            "كان التحدّي إضافة تفصيل أعمدة الضرائب مع الإبقاء على سلوك الفواتير القياسي سليمًا."),
        'approach': L(
            "We built an Odoo customization/prototype that adds the additional tax-column logic the team needed, "
            "while preserving the standard invoice behavior as much as possible so the core accounting flow stayed "
            "reliable.\n"
            "Delivered: a working Odoo customization/prototype for the extended tax-column presentation. "
            "Technologies: Odoo (custom module), Python and the Odoo accounting framework.",
            "Construimos una personalización/prototipo en Odoo que añade la lógica adicional de columnas de "
            "impuestos que el equipo necesitaba, preservando en lo posible el comportamiento estándar de las "
            "facturas para que el flujo contable principal siguiera siendo fiable.\n"
            "Entregado: una personalización/prototipo funcional en Odoo para la presentación ampliada de columnas "
            "de impuestos. Tecnologías: Odoo (módulo a medida), Python y el marco contable de Odoo.",
            "بنينا تخصيصًا/نموذجًا أوليًا في Odoo يضيف منطق أعمدة الضرائب الإضافي الذي يحتاجه الفريق، مع الحفاظ قدر "
            "الإمكان على سلوك الفواتير القياسي ليبقى تدفّق المحاسبة الأساسي موثوقًا.\n"
            "ما سُلّم: تخصيص/نموذج أولي عملي في Odoo للعرض الموسّع لأعمدة الضرائب. التقنيات: Odoo (وحدة مخصّصة)، "
            "وPython، وإطار المحاسبة في Odoo."),
        'results': L(
            "The team got the additional tax detail it needed for review, layered carefully on top of Odoo's "
            "standard accounting rather than working against it.\n"
            "Related services: the Odoo Accounting & Invoicing Process Review and Custom Odoo Module Development. "
            "This is a technical customization, not tax advice.",
            "El equipo obtuvo el detalle fiscal adicional que necesitaba para la revisión, añadido con cuidado "
            "sobre la contabilidad estándar de Odoo en lugar de ir en su contra.\n"
            "Servicios relacionados: revisión de procesos de contabilidad y facturación, y desarrollo de módulos a "
            "medida. Es una personalización técnica, no asesoramiento fiscal.",
            "حصل الفريق على التفصيل الضريبي الإضافي الذي يحتاجه للمراجعة، مُضافًا بعناية فوق محاسبة Odoo القياسية بدل "
            "أن يتعارض معها.\n"
            "خدمات ذات صلة: مراجعة عمليات المحاسبة والفوترة، وتطوير وحدات مخصّصة. هذا تخصيص تقني وليس استشارة ضريبية."),
        'order': 10,
        'meta_description': L(
            'How Bidatia added detailed invoice tax-column presentation in Odoo for accounting review while preserving the standard accounting flow. A technical customization.',
            'Cómo Bidatia añadió en Odoo una presentación detallada de columnas de impuestos para la revisión contable, preservando el flujo contable estándar. Una personalización técnica.',
            'كيف أضاف Bidatia في Odoo عرضًا مفصّلًا لأعمدة الضرائب لأغراض المراجعة المحاسبية، مع الحفاظ على تدفّق المحاسبة القياسي. تخصيص تقني.'),
    },
    {
        'title': L('Building an audit and extraction tool for Odoo migration analysis',
                   'Una herramienta de auditoría y extracción para analizar migraciones de Odoo',
                   'أداة تدقيق واستخراج لتحليل ترقيات Odoo'),
        'client_summary': L('ERP technical audit · internal tooling',
                            'Auditoría técnica de ERP · herramientas internas',
                            'تدقيق تقني لأنظمة ERP · أدوات داخلية'),
        'challenge': L(
            "Large Odoo systems can contain hundreds of custom models, fields, views, server actions, access rules "
            "and Studio changes — which makes migration planning slow and easy to get wrong when done by hand.\n"
            "A reliable way to see the full technical picture was needed before planning any migration.",
            "Los sistemas Odoo grandes pueden contener cientos de modelos, campos, vistas, acciones de servidor, "
            "reglas de acceso y cambios de Studio a medida, lo que hace que planificar una migración sea lento y "
            "propenso a errores si se hace a mano.\n"
            "Hacía falta una forma fiable de ver la imagen técnica completa antes de planificar cualquier "
            "migración.",
            "قد تحتوي أنظمة Odoo الكبيرة على مئات النماذج والحقول والواجهات وإجراءات الخادم وقواعد الوصول وتغييرات "
            "Studio المخصّصة، ما يجعل تخطيط الترقية بطيئًا وعرضة للخطأ عند تنفيذه يدويًا.\n"
            "كانت الحاجة قائمة لطريقة موثوقة لرؤية الصورة التقنية الكاملة قبل تخطيط أي ترقية."),
        'approach': L(
            "We built an audit/extraction tool that connects to Odoo, collects the technical metadata across the "
            "system, and produces structured Markdown and JSON reports that make the customizations reviewable at "
            "a glance.\n"
            "Delivered: an Odoo audit/extraction tool with structured Markdown/JSON reporting for migration "
            "analysis. Technologies: Python, the Odoo API and structured report generation.",
            "Construimos una herramienta de auditoría/extracción que se conecta a Odoo, recopila los metadatos "
            "técnicos de todo el sistema y produce informes estructurados en Markdown y JSON que permiten revisar "
            "las personalizaciones de un vistazo.\n"
            "Entregado: una herramienta de auditoría/extracción de Odoo con informes estructurados en Markdown/JSON "
            "para el análisis de migración. Tecnologías: Python, la API de Odoo y generación de informes "
            "estructurados.",
            "بنينا أداة تدقيق/استخراج تتّصل بـ Odoo، وتجمع البيانات الوصفية التقنية عبر النظام، وتنتج تقارير منظَّمة "
            "بصيغتَي Markdown وJSON تجعل التخصيصات قابلة للمراجعة بلمحة.\n"
            "ما سُلّم: أداة تدقيق/استخراج لـ Odoo مع تقارير منظَّمة بصيغة Markdown/JSON لتحليل الترقية. التقنيات: "
            "Python، وواجهة Odoo البرمجية، وتوليد تقارير منظَّمة."),
        'results': L(
            "What used to be a manual, error-prone inventory became a repeatable, structured report — making "
            "migration planning faster and decisions better grounded in the system's real state.\n"
            "Related services: Odoo Health Check, Odoo Migration Assessment and Odoo Studio Cleanup.",
            "Lo que antes era un inventario manual y propenso a errores se convirtió en un informe estructurado y "
            "repetible, lo que aceleró la planificación de la migración y la basó mejor en el estado real del "
            "sistema.\n"
            "Servicios relacionados: diagnóstico técnico de Odoo, evaluación de migración de Odoo y limpieza de "
            "Odoo Studio.",
            "تحوّل ما كان جردًا يدويًا عرضة للخطأ إلى تقرير منظَّم قابل للتكرار، فأصبح تخطيط الترقية أسرع وأكثر "
            "استنادًا إلى الحالة الفعلية للنظام.\n"
            "خدمات ذات صلة: الفحص الفني لـ Odoo، وتقييم ترقية Odoo، وتنظيف Odoo Studio."),
        'order': 11,
        'meta_description': L(
            'How Bidatia built an Odoo audit and extraction tool that collects technical metadata and produces structured reports to make migration planning faster and safer.',
            'Cómo Bidatia construyó una herramienta de auditoría y extracción de Odoo que recopila metadatos técnicos y genera informes estructurados para acelerar y asegurar la planificación de migraciones.',
            'كيف بنى Bidatia أداة تدقيق واستخراج لـ Odoo تجمع البيانات الوصفية التقنية وتنتج تقارير منظَّمة لتسريع تخطيط الترقية وجعله أكثر أمانًا.'),
    },
    {
        'title': L('A controlled connector for AI-assisted Odoo technical review',
                   'Un conector controlado para revisión técnica de Odoo asistida por IA',
                   'موصّل مُتحكَّم به لمراجعة Odoo التقنية بمساعدة الذكاء الاصطناعي'),
        'client_summary': L('ERP technical operations · AI-assisted engineering',
                            'Operaciones técnicas de ERP · ingeniería asistida por IA',
                            'العمليات التقنية لأنظمة ERP · هندسة بمساعدة الذكاء الاصطناعي'),
        'challenge': L(
            "Technical teams wanted a safer way to let AI-assisted tools inspect allowed Odoo data and help review "
            "records, normalization rules and operational patterns — without giving those tools unrestricted "
            "access to the system.\n"
            "The hard part was enabling useful AI-assisted analysis while keeping access controlled and auditable.",
            "Los equipos técnicos querían una forma más segura de permitir que las herramientas asistidas por IA "
            "inspeccionaran datos permitidos de Odoo y ayudaran a revisar registros, reglas de normalización y "
            "patrones operativos, sin dar a esas herramientas acceso sin restricciones al sistema.\n"
            "La parte difícil era habilitar un análisis asistido por IA útil manteniendo el acceso controlado y "
            "auditable.",
            "أرادت الفرق التقنية طريقة أكثر أمانًا للسماح لأدوات مدعومة بالذكاء الاصطناعي بفحص بيانات Odoo المسموح "
            "بها والمساعدة في مراجعة السجلّات وقواعد التطبيع والأنماط التشغيلية — دون منح تلك الأدوات وصولًا غير "
            "مقيّد للنظام.\n"
            "كان الجزء الصعب هو تمكين تحليل مفيد بمساعدة الذكاء الاصطناعي مع إبقاء الوصول مُتحكَّمًا به وقابلًا "
            "للتدقيق."),
        'approach': L(
            "We built a controlled connector layer with authentication, an explicit list of allowed models, "
            "defined tool endpoints and review workflows — so AI-assisted analysis could only reach what it was "
            "permitted to, under clear rules.\n"
            "Delivered: a controlled Odoo connector with authentication, allowlisted models, tool endpoints and "
            "review workflows for AI-assisted technical analysis. Technologies: Python, Django, the Odoo API and a "
            "controlled tool/endpoint layer.",
            "Construimos una capa de conector controlada con autenticación, una lista explícita de modelos "
            "permitidos, endpoints de herramientas definidos y flujos de revisión, de modo que el análisis "
            "asistido por IA solo pudiera acceder a lo permitido, bajo reglas claras.\n"
            "Entregado: un conector de Odoo controlado con autenticación, modelos en lista blanca, endpoints de "
            "herramientas y flujos de revisión para el análisis técnico asistido por IA. Tecnologías: Python, "
            "Django, la API de Odoo y una capa controlada de herramientas/endpoints.",
            "بنينا طبقة موصّل مُتحكَّم بها مع مصادقة، وقائمة صريحة بالنماذج المسموح بها، ونقاط نهاية أدوات محدّدة، "
            "وتدفّقات مراجعة — بحيث لا يصل التحليل المدعوم بالذكاء الاصطناعي إلا إلى المسموح به، وفق قواعد واضحة.\n"
            "ما سُلّم: موصّل Odoo مُتحكَّم به مع مصادقة، ونماذج في القائمة البيضاء، ونقاط نهاية أدوات، وتدفّقات "
            "مراجعة للتحليل التقني المدعوم بالذكاء الاصطناعي. التقنيات: Python، وDjango، وواجهة Odoo البرمجية، وطبقة "
            "أدوات/نقاط نهاية مُتحكَّم بها."),
        'results': L(
            "The team gained a safer, scoped way to apply AI-assisted review to Odoo — useful analysis within clear "
            "boundaries, rather than broad, unrestricted access.\n"
            "Related services: AI-assisted engineering, Odoo technical support and Django/Odoo Integration.",
            "El equipo obtuvo una forma más segura y acotada de aplicar la revisión asistida por IA a Odoo: "
            "análisis útil dentro de límites claros, en lugar de un acceso amplio y sin restricciones.\n"
            "Servicios relacionados: ingeniería asistida por IA, soporte técnico de Odoo e integración Django/Odoo.",
            "حصل الفريق على طريقة أكثر أمانًا ومحدّدة النطاق لتطبيق المراجعة المدعومة بالذكاء الاصطناعي على Odoo: "
            "تحليل مفيد ضمن حدود واضحة، بدل وصول واسع وغير مقيّد.\n"
            "خدمات ذات صلة: الهندسة بمساعدة الذكاء الاصطناعي، ودعم Odoo التقني، وتكامل Django/Odoo."),
        'order': 12,
        'meta_description': L(
            'How Bidatia built a controlled connector enabling AI-assisted Odoo technical review with authentication, allowlisted models and defined, auditable access.',
            'Cómo Bidatia construyó un conector controlado que habilita la revisión técnica de Odoo asistida por IA con autenticación, modelos en lista blanca y acceso definido y auditable.',
            'كيف بنى Bidatia موصّلًا مُتحكَّمًا به يُتيح مراجعة Odoo التقنية بمساعدة الذكاء الاصطناعي مع مصادقة ونماذج في القائمة البيضاء ووصول محدّد وقابل للتدقيق.'),
    },
]


BLOG_POSTS = [
    {
        'title': L(
            'Why ERP projects need a data strategy from day one',
            'Por qué los proyectos de ERP necesitan una estrategia de datos desde el primer día',
            'لماذا تحتاج مشاريع ERP إلى استراتيجية بيانات منذ اليوم الأول'),
        'excerpt': L(
            'An ERP is the largest data project most companies ever run — yet data strategy is usually the last thing on the plan. Here is why that order should be reversed.',
            'Un ERP es el mayor proyecto de datos que muchas empresas emprenderán nunca, y sin embargo la estrategia de datos suele ser lo último en el plan. Aquí explicamos por qué ese orden debería invertirse.',
            'يُعدّ نظام ERP أكبر مشروع بيانات تنفّذه معظم الشركات، ومع ذلك تأتي استراتيجية البيانات عادةً في آخر الخطّة. إليك لماذا يجب عكس هذا الترتيب.'),
        'content': L(
            "When teams plan an ERP project, they talk about modules, workflows and go-live dates. What they "
            "rarely talk about — until it hurts — is the data: where it lives today, how clean it is, who owns "
            "it, and what 'one customer' or 'one product' actually means across the business.\n"
            "Every ERP runs on data, and an ERP go-live is really a giant data migration. If you move messy, "
            "duplicated, inconsistent records into a shiny new system, you get a shiny new system full of messy "
            "data — plus a team that quietly stops trusting it. A data strategy decides, up front, which sources "
            "are authoritative, what quality rules apply, and how the ERP will feed reporting and AI later.\n"
            "At Bidatia, ERP and data are not two separate projects. We design the data model, the governance "
            "rules and the integration points alongside the ERP itself — so the system you launch is one you, "
            "and your dashboards, can trust from day one.",

            "Cuando los equipos planifican un proyecto de ERP, hablan de módulos, flujos de trabajo y fechas de "
            "puesta en marcha. De lo que rara vez hablan —hasta que duele— es de los datos: dónde están hoy, qué "
            "calidad tienen, quién es su propietario y qué significa realmente «un cliente» o «un producto» en "
            "toda la empresa.\n"
            "Todo ERP funciona con datos, y una puesta en marcha es, en realidad, una migración de datos enorme. "
            "Si trasladas registros desordenados, duplicados e inconsistentes a un sistema nuevo y reluciente, "
            "obtienes un sistema nuevo y reluciente lleno de datos desordenados, y un equipo que deja de confiar "
            "en él en silencio. Una estrategia de datos decide, de antemano, qué fuentes son autoritativas, qué "
            "reglas de calidad se aplican y cómo el ERP alimentará después los informes y la IA.\n"
            "En Bidatia, el ERP y los datos no son dos proyectos separados. Diseñamos el modelo de datos, las "
            "reglas de gobierno y los puntos de integración junto al propio ERP, para que el sistema que pones en "
            "marcha sea uno en el que tú —y tus cuadros de mando— podáis confiar desde el primer día.",

            "عندما تخطّط الفرق لمشروع ERP، تتحدّث عن الوحدات وسير العمل ومواعيد الإطلاق. وما نادرًا ما تتحدّث عنه — "
            "حتى يؤلم — هو البيانات: أين توجد اليوم، ومدى نظافتها، ومن يملكها، وما الذي يعنيه فعلًا «عميل واحد» أو "
            "«منتج واحد» عبر الشركة.\n"
            "كل نظام ERP يعمل بالبيانات، والإطلاق في حقيقته ترحيل بيانات ضخم. فإذا نقلت سجلّات فوضوية ومكرّرة وغير "
            "متّسقة إلى نظام جديد لامع، حصلت على نظام جديد لامع مليء ببيانات فوضوية — وفريق يتوقّف بهدوء عن الوثوق "
            "به. تحدّد استراتيجية البيانات مسبقًا أي المصادر مرجعية، وأي قواعد جودة تنطبق، وكيف سيغذّي النظام "
            "التقارير والذكاء الاصطناعي لاحقًا.\n"
            "في Bidatia، ليست ERP والبيانات مشروعين منفصلين. نصمّم نموذج البيانات وقواعد الحوكمة ونقاط التكامل إلى "
            "جانب النظام نفسه، ليكون النظام الذي تُطلقه نظامًا تثق به أنت ولوحاتك منذ اليوم الأول."),
        'meta_description': L(
            'An ERP go-live is really a giant data migration. Why a data strategy — sources, quality rules, ownership and integration — belongs at the start of every ERP project.',
            'Una puesta en marcha de ERP es, en realidad, una migración de datos enorme. Por qué una estrategia de datos —fuentes, reglas de calidad, propiedad e integración— debe estar al inicio de todo proyecto de ERP.',
            'الإطلاق في حقيقته ترحيل بيانات ضخم. لماذا تنتمي استراتيجية البيانات — المصادر وقواعد الجودة والملكية والتكامل — إلى بداية كل مشروع ERP.'),
    },
    {
        'title': L(
            'Data governance for ERP and CRM: turning records into a trusted asset',
            'Gobierno del dato para ERP y CRM: convertir los registros en un activo fiable',
            'حوكمة البيانات لـ ERP و CRM: تحويل السجلّات إلى أصل موثوق'),
        'excerpt': L(
            'Duplicate customers, three definitions of "active", empty mandatory fields. Governance is what keeps your operational data from quietly rotting.',
            'Clientes duplicados, tres definiciones de «activo», campos obligatorios vacíos. El gobierno del dato es lo que evita que tus datos operativos se degraden en silencio.',
            'عملاء مكرّرون، وثلاثة تعريفات لكلمة «نشِط»، وحقول إلزامية فارغة. الحوكمة هي ما يمنع بياناتك التشغيلية من التعفّن بهدوء.'),
        'content': L(
            "Ask three people in a company how many active customers it has, and you'll often get three answers. "
            "That's not a reporting problem — it's a governance problem. Without agreed definitions, ownership "
            "and quality rules, operational data drifts: duplicates creep in, codes diverge, mandatory fields get "
            "skipped, and every dashboard built on top inherits the mess.\n"
            "Data governance for ERP and CRM is the unglamorous discipline that prevents this. It answers simple "
            "but critical questions: who owns customer data? What makes a record valid? How do we detect and merge "
            "duplicates? What does each KPI actually measure? Done well, it's invisible — things just stay clean.\n"
            "Bidatia's roots are in data governance, and we bring that discipline to operational systems. We define "
            "ownership and quality rules, set up validation and de-duplication, and give you dashboards that surface "
            "problems early — so your ERP and CRM stay a single source of truth you can build reporting and AI on.",

            "Pregunta a tres personas de una empresa cuántos clientes activos tiene y a menudo obtendrás tres "
            "respuestas. Eso no es un problema de informes, es un problema de gobierno del dato. Sin definiciones "
            "acordadas, propiedad y reglas de calidad, los datos operativos se degradan: aparecen duplicados, los "
            "códigos divergen, se omiten campos obligatorios y cada cuadro de mando construido encima hereda el caos.\n"
            "El gobierno del dato para ERP y CRM es la disciplina poco vistosa que lo evita. Responde a preguntas "
            "sencillas pero críticas: ¿quién es propietario de los datos de cliente? ¿Qué hace válido a un registro? "
            "¿Cómo detectamos y fusionamos duplicados? ¿Qué mide realmente cada KPI? Bien hecho, es invisible: las "
            "cosas simplemente se mantienen limpias.\n"
            "Las raíces de Bidatia están en el gobierno del dato, y llevamos esa disciplina a los sistemas "
            "operativos. Definimos propiedad y reglas de calidad, implantamos validación y deduplicación, y te damos "
            "cuadros de mando que detectan los problemas a tiempo, para que tu ERP y tu CRM sigan siendo una fuente "
            "única de verdad sobre la que construir informes e IA.",

            "اسأل ثلاثة أشخاص في شركة عن عدد عملائها النشطين، وغالبًا ستحصل على ثلاث إجابات. هذه ليست مشكلة تقارير "
            "— بل مشكلة حوكمة. فبلا تعريفات متّفق عليها وملكية وقواعد جودة، تنحرف البيانات التشغيلية: تتسلّل "
            "التكرارات، وتتباعد الرموز، وتُهمَل الحقول الإلزامية، وترث كل لوحة مبنية فوقها الفوضى.\n"
            "حوكمة البيانات لـ ERP و CRM هي الانضباط غير البرّاق الذي يمنع ذلك. تجيب عن أسئلة بسيطة لكنها حاسمة: من "
            "يملك بيانات العملاء؟ وما الذي يجعل السجلّ صالحًا؟ وكيف نكتشف التكرارات وندمجها؟ وماذا يقيس كل مؤشّر "
            "فعلًا؟ وحين تُنفَّذ جيدًا تكون غير مرئية — تبقى الأمور نظيفة وحسب.\n"
            "جذور Bidatia في حوكمة البيانات، وننقل هذا الانضباط إلى الأنظمة التشغيلية. نحدّد الملكية وقواعد الجودة، "
            "ونُعِدّ التحقّق وإزالة التكرار، ونمنحك لوحات تكشف المشكلات مبكّرًا، ليبقى ERP و CRM لديك مصدر حقيقة "
            "واحدًا تبني عليه التقارير والذكاء الاصطناعي."),
        'meta_description': L(
            'Why ERP and CRM data quietly degrades without governance, and how ownership, quality rules, validation and de-duplication keep it a trusted single source of truth.',
            'Por qué los datos de ERP y CRM se degradan en silencio sin gobierno del dato, y cómo la propiedad, las reglas de calidad, la validación y la deduplicación los mantienen como una fuente única de verdad fiable.',
            'لماذا تتدهور بيانات ERP و CRM بهدوء بلا حوكمة، وكيف تحافظ الملكية وقواعد الجودة والتحقّق وإزالة التكرار عليها كمصدر حقيقة واحد موثوق.'),
    },
    {
        'title': L(
            'AI agents inside ERP workflows: where they help, and where they don\'t',
            'Agentes de IA en los flujos del ERP: dónde ayudan y dónde no',
            'وكلاء الذكاء الاصطناعي داخل تدفّقات ERP: أين يساعدون وأين لا'),
        'excerpt': L(
            'AI agents can quietly remove hours of repetitive ERP work — or quietly make confident mistakes. The difference is scope, grounding and a human in the loop.',
            'Los agentes de IA pueden eliminar discretamente horas de trabajo repetitivo en el ERP, o cometer errores con total seguridad. La diferencia está en el alcance, el anclaje en datos y una persona supervisando.',
            'يمكن لوكلاء الذكاء الاصطناعي أن يزيلوا بهدوء ساعات من العمل المتكرّر في ERP — أو أن يرتكبوا أخطاءً بثقة. الفارق هو النطاق والاستناد إلى البيانات ووجود إنسان في المسار.'),
        'content': L(
            "There's a lot of noise about AI in business software, and not all of it is useful. Inside an ERP, the "
            "honest answer is: AI agents are excellent at some tasks and dangerous at others, and knowing the "
            "difference is the whole game.\n"
            "Where they help: triaging and classifying incoming documents, drafting replies for a human to approve, "
            "summarizing long case histories, extracting structured fields from messy text, and flagging anomalies "
            "for review. These are high-volume, low-stakes-per-item tasks where a human still signs off on anything "
            "that matters. Where they hurt: anywhere an unsupervised model posts to your ledger, changes prices, or "
            "makes an irreversible decision on its own.\n"
            "Bidatia builds AI agents grounded in your own governed data (using RAG), scoped to one clear task, with "
            "a human approval step where decisions count — and every action logged and auditable. That's the "
            "difference between AI that saves your team hours and AI that creates a cleanup project. Good data "
            "governance, it turns out, is also the foundation for trustworthy AI.",

            "Hay mucho ruido sobre la IA en el software de empresa, y no todo es útil. Dentro de un ERP, la respuesta "
            "honesta es: los agentes de IA son excelentes en algunas tareas y peligrosos en otras, y saber "
            "distinguirlas lo es todo.\n"
            "Dónde ayudan: clasificar documentos entrantes, redactar respuestas para que una persona las apruebe, "
            "resumir historiales largos, extraer campos estructurados de texto desordenado y señalar anomalías para "
            "su revisión. Son tareas de gran volumen y bajo riesgo por elemento, en las que una persona sigue "
            "validando lo que importa. Dónde perjudican: allí donde un modelo sin supervisión escribe en tu "
            "contabilidad, cambia precios o toma por su cuenta una decisión irreversible.\n"
            "Bidatia construye agentes de IA anclados en tus propios datos gobernados (mediante RAG), acotados a una "
            "tarea clara, con un paso de aprobación humana donde las decisiones cuentan, y cada acción registrada y "
            "auditable. Esa es la diferencia entre una IA que ahorra horas a tu equipo y una IA que crea un proyecto "
            "de limpieza. Resulta que un buen gobierno del dato es también la base de una IA fiable.",

            "هناك ضجيج كثير حول الذكاء الاصطناعي في برمجيات الأعمال، وليس كله مفيدًا. وداخل نظام ERP، الإجابة الصادقة "
            "هي: وكلاء الذكاء الاصطناعي ممتازون في بعض المهام وخطيرون في أخرى، ومعرفة الفرق هي اللعبة كلّها.\n"
            "أين يساعدون: فرز المستندات الواردة وتصنيفها، وصياغة ردود ليوافق عليها إنسان، وتلخيص تواريخ الحالات "
            "الطويلة، واستخراج حقول منظَّمة من نصّ فوضوي، ورصد الشذوذ للمراجعة. هذه مهامّ عالية الحجم ومنخفضة المخاطر "
            "لكل عنصر، يبقى فيها الإنسان مصادقًا على ما يهمّ. وأين يضرّون: حيثما يكتب نموذج غير مُراقَب في دفترك، أو "
            "يغيّر الأسعار، أو يتّخذ بمفرده قرارًا لا رجعة فيه.\n"
            "تبني Bidatia وكلاء ذكاء اصطناعي مستندين إلى بياناتك المَحوكمة (عبر RAG)، محصورين في مهمّة واضحة، مع خطوة "
            "موافقة بشرية حيث تهمّ القرارات، وكل إجراء مسجَّل وقابل للتدقيق. هذا هو الفرق بين ذكاء اصطناعي يوفّر على "
            "فريقك ساعات وآخر يصنع مشروع تنظيف. وتبيَّن أن حوكمة البيانات الجيدة هي أيضًا أساس الذكاء الاصطناعي الموثوق."),
        'meta_description': L(
            'A practical look at AI agents in ERP workflows: the tasks they do well, the ones they should never own alone, and why grounding, scope and human approval matter.',
            'Una mirada práctica a los agentes de IA en los flujos del ERP: las tareas que hacen bien, las que nunca deberían asumir solos y por qué importan el anclaje en datos, el alcance y la aprobación humana.',
            'نظرة عملية على وكلاء الذكاء الاصطناعي في تدفّقات ERP: المهام التي يُتقنونها، وتلك التي يجب ألّا يتولّوها بمفردهم، ولماذا يهمّ الاستناد إلى البيانات والنطاق والموافقة البشرية.'),
    },
    {
        'title': L(
            '5 warning signs your Odoo system needs a technical health check',
            '5 señales de que tu sistema Odoo necesita un diagnóstico técnico',
            '5 علامات تدلّ على أن نظام Odoo لديك يحتاج إلى فحص فني'),
        'excerpt': L(
            'Slow screens and "weird" behaviour are rarely random. Here are the signals that usually mean it is time for a structured review.',
            'Las pantallas lentas y los comportamientos «raros» rara vez son casualidad. Estas son las señales que suelen indicar que toca una revisión estructurada.',
            'نادرًا ما تكون الشاشات البطيئة والسلوكيات «الغريبة» محض صدفة. إليك العلامات التي تعني عادةً أن وقت المراجعة المنظَّمة قد حان.'),
        'content': L(
            "Most Odoo systems don't break overnight — they slowly accumulate friction until one day "
            "someone asks, 'why does this take so long?' and nobody has a good answer.\n"
            "Here are five signals that usually mean a structured technical review is overdue: screens "
            "that have gradually gotten slower without an obvious cause; automated actions or scheduled "
            "jobs that occasionally fail silently; reports that show different numbers depending on who "
            "runs them; a growing list of 'don't touch that, we're not sure what it does' customizations; "
            "and a team that has started building workarounds outside Odoo because something inside it "
            "doesn't work the way they need.\n"
            "Individually, each of these might seem manageable. Together, they're usually a sign that "
            "the system has drifted from its original design — and that a focused audit will save far more "
            "time than it costs.",

            "La mayoría de los sistemas Odoo no se rompen de un día para otro: van acumulando fricción poco a poco "
            "hasta que un día alguien pregunta «¿por qué tarda tanto esto?» y nadie tiene una buena respuesta.\n"
            "Estas son cinco señales que suelen indicar que una revisión técnica estructurada lleva tiempo "
            "pendiente: pantallas que se han ido volviendo más lentas sin causa aparente; acciones automatizadas o "
            "tareas programadas que de vez en cuando fallan en silencio; informes que muestran cifras distintas "
            "según quién los ejecute; una lista creciente de personalizaciones del tipo «no toques eso, no sabemos "
            "bien qué hace»; y un equipo que ha empezado a improvisar soluciones fuera de Odoo porque algo dentro "
            "no funciona como necesita.\n"
            "Por separado, cada una puede parecer asumible. Juntas, suelen indicar que el sistema se ha alejado de "
            "su diseño original, y que una auditoría enfocada ahorrará mucho más tiempo del que cuesta.",

            "معظم أنظمة Odoo لا تتعطّل بين ليلة وضحاها — بل تتراكم فيها العوائق ببطء حتى يسأل أحدهم يومًا: «لماذا "
            "يستغرق هذا كل هذا الوقت؟» ولا يجد أحد إجابة جيدة.\n"
            "إليك خمس علامات تعني عادةً أن مراجعة فنية منظَّمة قد تأخّرت: شاشات أصبحت أبطأ تدريجيًا دون سبب واضح؛ "
            "وإجراءات آلية أو مهام مجدوَلة تفشل بصمت أحيانًا؛ وتقارير تُظهر أرقامًا مختلفة بحسب من يشغّلها؛ وقائمة "
            "متنامية من التخصيصات من نوع «لا تلمس ذلك، لسنا متأكّدين مما يفعله»؛ وفريق بدأ يبتكر حلولًا بديلة خارج "
            "Odoo لأن شيئًا داخله لا يعمل كما يحتاجون.\n"
            "بمفردها قد تبدو كل علامة محتمَلة. لكنها مجتمعةً تشير عادةً إلى أن النظام قد ابتعد عن تصميمه الأصلي — وأن "
            "تدقيقًا مركّزًا سيوفّر من الوقت أكثر بكثير مما يكلّف."),
        'meta_description': L(
            'Five common warning signs that your Odoo system has drifted from its original design and would benefit from a structured technical health check.',
            'Cinco señales habituales de que tu sistema Odoo se ha alejado de su diseño original y se beneficiaría de un diagnóstico técnico estructurado.',
            'خمس علامات شائعة على أن نظام Odoo لديك قد ابتعد عن تصميمه الأصلي وسيستفيد من فحص فني منظَّم.'),
    },
    {
        'title': L(
            'Odoo Studio vs. custom modules: when each one makes sense',
            'Odoo Studio frente a módulos a medida: cuándo conviene cada uno',
            'Odoo Studio مقابل الوحدات المخصّصة: متى يناسب كلٌّ منهما'),
        'excerpt': L(
            'Studio is a great prototyping tool — but knowing when to graduate to a real module can save you serious pain later.',
            'Studio es una gran herramienta de prototipado, pero saber cuándo dar el salto a un módulo de verdad puede ahorrarte muchos problemas después.',
            'يُعدّ Studio أداة ممتازة لبناء النماذج الأولية، لكن معرفة متى تنتقل إلى وحدة حقيقية قد يجنّبك متاعب جدّية لاحقًا.'),
        'content': L(
            "Odoo Studio is genuinely useful: it lets non-developers add fields, tweak views, and build "
            "simple automations without writing code. The trouble starts when Studio becomes the permanent "
            "home for business-critical logic rather than a prototyping tool.\n"
            "A simple rule of thumb: if a customization is small, low-risk, and easy to recreate, Studio is "
            "often fine. If it's central to how your business runs, touches multiple workflows, or would be "
            "painful to lose, it probably belongs in a properly engineered custom module — version-controlled, "
            "testable, and safe to carry through future upgrades.\n"
            "The good news is that this isn't an all-or-nothing decision. Many companies run a hybrid setup: "
            "Studio for quick, low-stakes adjustments, and custom modules for the logic that really matters. "
            "The key is being intentional about which is which — rather than discovering the difference during "
            "your next upgrade.",

            "Odoo Studio es realmente útil: permite a quienes no programan añadir campos, ajustar vistas y crear "
            "automatizaciones sencillas sin escribir código. El problema empieza cuando Studio pasa de ser una "
            "herramienta de prototipado a convertirse en el hogar permanente de la lógica crítica del negocio.\n"
            "Una regla práctica sencilla: si una personalización es pequeña, de bajo riesgo y fácil de rehacer, "
            "Studio suele bastar. Si es central para el funcionamiento de tu negocio, afecta a varios flujos de "
            "trabajo o sería doloroso perderla, probablemente debería vivir en un módulo a medida bien diseñado: "
            "versionado, testeable y seguro de cara a futuras actualizaciones.\n"
            "La buena noticia es que no es una decisión de todo o nada. Muchas empresas funcionan con un enfoque "
            "híbrido: Studio para ajustes rápidos y de poca importancia, y módulos a medida para la lógica que de "
            "verdad importa. La clave es decidir con criterio qué va en cada sitio, en lugar de descubrir la "
            "diferencia durante la próxima actualización.",

            "Odoo Studio مفيد حقًّا: فهو يتيح لغير المطوّرين إضافة الحقول، وتعديل الواجهات، وبناء أتمتة بسيطة دون "
            "كتابة شيفرة. لكن المشكلة تبدأ حين يتحوّل Studio من أداة لبناء النماذج الأولية إلى موطن دائم لمنطق العمل "
            "الجوهري.\n"
            "قاعدة عملية بسيطة: إذا كان التخصيص صغيرًا، ومنخفض المخاطر، وسهل إعادة إنشائه، فغالبًا يكفي Studio. أمّا "
            "إذا كان محوريًا لطريقة عمل نشاطك، أو يمسّ عدّة تدفّقات عمل، أو سيكون فقدانه مؤلمًا، فالأرجح أن مكانه وحدة "
            "مخصّصة مصمَّمة بعناية — خاضعة لإدارة الإصدارات، وقابلة للاختبار، وآمنة عبر الترقيات المقبلة.\n"
            "والخبر الجيّد أن هذا ليس قرارًا حاسمًا بين كل شيء أو لا شيء. تعتمد كثير من الشركات إعدادًا هجينًا: Studio "
            "للتعديلات السريعة المنخفضة الأهمية، والوحدات المخصّصة للمنطق المهمّ فعلًا. والمفتاح هو اتخاذ القرار بوعي "
            "حول ما يذهب إلى كلٍّ منهما — بدل اكتشاف الفرق أثناء الترقية التالية."),
        'meta_description': L(
            'A practical guide to deciding when Odoo Studio customizations are appropriate, and when business-critical logic should be rebuilt as a proper custom module.',
            'Una guía práctica para decidir cuándo son apropiadas las personalizaciones de Odoo Studio y cuándo la lógica crítica debe reconstruirse como un módulo a medida en condiciones.',
            'دليل عملي لتقرير متى تكون تخصيصات Odoo Studio مناسبة، ومتى ينبغي إعادة بناء المنطق الجوهري كوحدة مخصّصة سليمة.'),
    },
    {
        'title': L(
            'Three questions to ask before starting an Odoo migration',
            'Tres preguntas que hacerte antes de empezar una migración de Odoo',
            'ثلاثة أسئلة اطرحها قبل بدء ترقية Odoo'),
        'excerpt': L(
            'Migrations succeed or struggle long before the first line of code changes. These three questions help you start on the right foot.',
            'El éxito o las dificultades de una migración se deciden mucho antes de cambiar la primera línea de código. Estas tres preguntas te ayudan a empezar con buen pie.',
            'يتحدّد نجاح الترقية أو تعثّرها قبل تغيير أول سطر برمجي بوقت طويل. تساعدك هذه الأسئلة الثلاثة على البدء بشكل صحيح.'),
        'content': L(
            "Odoo migrations have a reputation for being risky — and sometimes they are, but usually because "
            "key questions weren't answered clearly before the project started.\n"
            "First: what exactly are we relying on today that must keep working tomorrow? It's surprisingly "
            "common for teams to discover, mid-migration, that a 'minor' customization is actually load-bearing. "
            "Second: how clean is our current setup, really? A migration is the worst time to discover years of "
            "undocumented Studio changes and forgotten automations. Third: what does success actually look like, "
            "and how will we know we've achieved it? Without a clear definition, it's hard to know when the "
            "project is truly done.\n"
            "Answering these honestly — ideally through a structured assessment — turns a migration from a "
            "leap of faith into a manageable, well-scoped project.",

            "Las migraciones de Odoo tienen fama de arriesgadas, y a veces lo son, pero normalmente porque no se "
            "respondieron con claridad las preguntas clave antes de empezar el proyecto.\n"
            "Primera: ¿de qué dependemos hoy exactamente que tenga que seguir funcionando mañana? Es "
            "sorprendentemente habitual que los equipos descubran, a mitad de la migración, que una personalización "
            "«menor» en realidad es esencial. Segunda: ¿cómo de limpia está realmente nuestra configuración actual? "
            "Una migración es el peor momento para descubrir años de cambios de Studio sin documentar y "
            "automatizaciones olvidadas. Tercera: ¿qué significa realmente el éxito y cómo sabremos que lo hemos "
            "logrado? Sin una definición clara, es difícil saber cuándo está de verdad terminado el proyecto.\n"
            "Responder a estas preguntas con honestidad —idealmente mediante una evaluación estructurada— convierte "
            "una migración de un salto al vacío en un proyecto manejable y bien definido.",

            "تُعرف ترقيات Odoo بأنها محفوفة بالمخاطر — وهي كذلك أحيانًا، لكن غالبًا لأن أسئلة جوهرية لم تُجَب بوضوح "
            "قبل انطلاق المشروع.\n"
            "أولًا: ما الذي نعتمد عليه اليوم بالضبط ويجب أن يستمرّ في العمل غدًا؟ من الشائع بشكل مفاجئ أن تكتشف الفرق "
            "في منتصف الترقية أن تخصيصًا «ثانويًا» هو في الحقيقة أساسي. ثانيًا: ما مدى نظافة إعدادنا الحالي فعلًا؟ "
            "الترقية أسوأ وقت لاكتشاف سنوات من تغييرات Studio غير الموثّقة والأتمتة المنسيّة. ثالثًا: كيف يبدو النجاح "
            "فعليًا، وكيف سنعرف أننا حقّقناه؟ بدون تعريف واضح، يصعب معرفة متى يكون المشروع قد اكتمل حقًّا.\n"
            "والإجابة عن هذه الأسئلة بصدق — ويُفضَّل عبر تقييم منظَّم — تحوّل الترقية من قفزة في المجهول إلى مشروع "
            "محدّد المعالم وقابل للإدارة."),
        'meta_description': L(
            'Three essential questions every business should answer before starting an Odoo version migration, to reduce risk and avoid costly surprises mid-project.',
            'Tres preguntas esenciales que toda empresa debería responder antes de iniciar una migración de versión de Odoo, para reducir el riesgo y evitar sorpresas costosas a mitad del proyecto.',
            'ثلاثة أسئلة جوهرية ينبغي لكل شركة الإجابة عنها قبل بدء ترقية إصدار Odoo، للحدّ من المخاطر وتجنّب المفاجآت المكلفة في منتصف المشروع.'),
    },
    {
        'title': L(
            'Planning a move to Odoo 19? What to check before you upgrade',
            '¿Pensando en pasar a Odoo 19? Qué revisar antes de actualizar',
            'تفكّر في الانتقال إلى Odoo 19؟ ما الذي يجب فحصه قبل الترقية'),
        'excerpt': L(
            'A newer Odoo version is tempting — but the upgrade succeeds or stalls based on what you check first. Here is a practical pre-migration checklist.',
            'Una versión más nueva de Odoo es tentadora, pero el éxito de la actualización depende de lo que revises primero. Aquí tienes una lista práctica previa a la migración.',
            'إصدار أحدث من Odoo مغرٍ — لكن نجاح الترقية يتوقّف على ما تفحصه أولًا. إليك قائمة عملية لما قبل الترقية.'),
        'content': L(
            "Moving to a newer Odoo version like Odoo 19 can bring real benefits — but most painful upgrades "
            "aren't caused by the new version itself. They're caused by what gets carried into it: custom code "
            "that wasn't written to survive upgrades, Studio changes nobody documented, third-party apps that may "
            "not have a compatible release yet, and data that quietly drifted out of shape over the years.\n"
            "Before committing to the move, check four things. First, your customizations and Studio changes: "
            "which are business-critical, and will they work on the new version? Second, your third-party and "
            "community apps: is each one available and stable for your target version? Third, your integrations: "
            "will the APIs and connectors still behave the same way? Fourth, your data: is it clean enough to "
            "migrate, or will it carry old problems forward?\n"
            "The cheapest way to answer these is a structured migration assessment on a copy of your system, "
            "before any production change. It turns 'we think it'll be fine' into a clear, evidence-based plan — "
            "and that is almost always cheaper than fixing a migration that went sideways.",

            "Pasar a una versión más nueva de Odoo, como Odoo 19, puede aportar beneficios reales, pero la mayoría "
            "de las actualizaciones dolorosas no las causa la nueva versión en sí, sino lo que se arrastra hasta "
            "ella: código a medida que no se escribió para sobrevivir a las actualizaciones, cambios de Studio que "
            "nadie documentó, aplicaciones de terceros que quizá aún no tengan una versión compatible y datos que "
            "se han ido deformando con los años.\n"
            "Antes de dar el paso, revisa cuatro cosas. Primero, tus personalizaciones y cambios de Studio: "
            "¿cuáles son críticos y funcionarán en la nueva versión? Segundo, tus aplicaciones de terceros o de la "
            "comunidad: ¿están disponibles y estables para tu versión de destino? Tercero, tus integraciones: "
            "¿seguirán comportándose igual las API y los conectores? Cuarto, tus datos: ¿están lo bastante limpios "
            "para migrar o arrastrarán problemas antiguos?\n"
            "La forma más barata de responder a esto es una evaluación de migración estructurada sobre una copia de "
            "tu sistema, antes de tocar producción. Convierte el «creemos que irá bien» en un plan claro basado en "
            "evidencias, y eso casi siempre sale más barato que arreglar una migración que se torció.",

            "قد يجلب الانتقال إلى إصدار أحدث من Odoo مثل Odoo 19 فوائد حقيقية — لكن معظم الترقيات المؤلمة لا يسبّبها "
            "الإصدار الجديد نفسه، بل ما يُحمَل إليه: شيفرة مخصّصة لم تُكتب لتصمد أمام الترقيات، وتغييرات Studio لم "
            "يوثّقها أحد، وتطبيقات طرف ثالث قد لا يتوفّر لها إصدار متوافق بعد، وبيانات انحرفت بهدوء عن شكلها عبر "
            "السنين.\n"
            "قبل الإقدام على الخطوة، افحص أربعة أمور. أولًا، تخصيصاتك وتغييرات Studio: أيّها جوهري، وهل ستعمل على "
            "الإصدار الجديد؟ ثانيًا، تطبيقات الطرف الثالث أو المجتمع: هل كلٌّ منها متوفّر ومستقر لإصدارك المستهدف؟ "
            "ثالثًا، تكاملاتك: هل ستظلّ واجهات الـ API والموصّلات تتصرّف بالطريقة نفسها؟ رابعًا، بياناتك: هل هي نظيفة "
            "بما يكفي للترحيل أم ستحمل المشكلات القديمة معها؟\n"
            "أرخص طريقة للإجابة عن ذلك هي تقييم ترقية منظَّم على نسخة من نظامك، قبل أي تغيير في الإنتاج. فهو يحوّل "
            "«نظنّ أن الأمور ستكون بخير» إلى خطة واضحة مبنية على أدلة — وهذا غالبًا أرخص من إصلاح ترقية انحرفت عن "
            "مسارها."),
        'meta_description': L(
            'Planning an upgrade to Odoo 19? A practical pre-migration checklist covering customizations, third-party apps, integrations and data — so your Odoo upgrade goes smoothly.',
            '¿Planeas actualizar a Odoo 19? Una lista práctica previa a la migración sobre personalizaciones, apps de terceros, integraciones y datos, para que tu actualización de Odoo salga bien.',
            'تخطّط للترقية إلى Odoo 19؟ قائمة عملية لما قبل الترقية تغطّي التخصيصات وتطبيقات الطرف الثالث والتكاملات والبيانات — لتمرّ ترقية Odoo بسلاسة.'),
    },
    {
        'title': L(
            'How Django and Odoo work together to close process gaps',
            'Cómo Django y Odoo trabajan juntos para cerrar brechas en los procesos de negocio',
            'كيف يعمل Django و Odoo معًا لسدّ الفجوات في عمليات الأعمال'),
        'excerpt': L(
            'Odoo runs your business — but some processes need more than configuration. Here is where a Django layer turns a limitation into a clean solution.',
            'Odoo gestiona tu negocio, pero algunos procesos necesitan más que configuración. Aquí es donde una capa Django convierte una limitación en una solución limpia.',
            'يدير Odoo نشاطك — لكن بعض العمليات تحتاج إلى أكثر من مجرّد إعداد. هنا يحوّل وجود طبقة Django القيدَ إلى حلٍّ نظيف.'),
        'content': L(
            "Odoo is excellent at covering the standard shape of a business — sales, inventory, accounting, "
            "projects. But most companies eventually hit a process that doesn't fit neatly inside it: a "
            "customer-facing portal with its own logic, a high-volume data flow that has to be fast and reliable, "
            "a complex calculation, or a tight integration with an external platform.\n"
            "You can sometimes force these into Odoo with heavy customization — but it is often cleaner to build "
            "the specialized part as a Django service that talks to Odoo through a well-defined API. Odoo stays the "
            "system of record for your core operations, while Django handles the part it is better suited for: "
            "custom interfaces, heavier logic, or performance-sensitive flows. Each system does what it does best, "
            "and a clean integration keeps them in sync.\n"
            "This pattern works precisely because the two share the same foundation — Python — so the same engineer "
            "can reason about both sides. The result is fewer fragile workarounds inside Odoo and a solution that "
            "is genuinely maintainable, rather than a pile of patches waiting to break at the next upgrade.",

            "Odoo es excelente para cubrir la forma estándar de un negocio: ventas, inventario, contabilidad, "
            "proyectos. Pero casi todas las empresas acaban topándose con un proceso que no encaja del todo: un "
            "portal para clientes con su propia lógica, un flujo de datos de gran volumen que debe ser rápido y "
            "fiable, un cálculo complejo o una integración estrecha con una plataforma externa.\n"
            "A veces puedes forzar todo esto dentro de Odoo con mucha personalización, pero suele ser más limpio "
            "construir la parte especializada como un servicio Django que se comunica con Odoo mediante una API "
            "bien definida. Odoo sigue siendo el sistema de referencia de tu operativa principal, mientras Django "
            "se encarga de aquello para lo que está mejor preparado: interfaces a medida, lógica más pesada o "
            "flujos sensibles al rendimiento. Cada sistema hace lo que mejor sabe hacer y una integración limpia "
            "los mantiene sincronizados.\n"
            "Este enfoque funciona precisamente porque ambos comparten la misma base —Python—, de modo que el mismo "
            "ingeniero puede razonar sobre los dos lados. El resultado son menos soluciones frágiles dentro de Odoo "
            "y una solución de verdad mantenible, en lugar de un montón de parches a la espera de romperse en la "
            "próxima actualización.",

            "يُبدع Odoo في تغطية الشكل القياسي لأي نشاط: المبيعات، والمخزون، والمحاسبة، والمشاريع. لكن معظم الشركات "
            "تصطدم في النهاية بعملية لا تتلاءم تمامًا معه: بوّابة للعملاء بمنطقها الخاص، أو تدفّق بيانات كبير الحجم "
            "يجب أن يكون سريعًا وموثوقًا، أو عملية حسابية معقّدة، أو تكامل وثيق مع منصّة خارجية.\n"
            "يمكنك أحيانًا حشر هذه الأمور داخل Odoo بتخصيص ثقيل — لكن غالبًا يكون الأنظف بناء الجزء المتخصّص كخدمة "
            "Django تتواصل مع Odoo عبر واجهة API محدّدة جيدًا. يبقى Odoo نظام التسجيل الأساسي لعملياتك الجوهرية، بينما "
            "يتولّى Django ما هو أنسب له: الواجهات المخصّصة، أو المنطق الأثقل، أو التدفّقات الحسّاسة للأداء. كل نظام "
            "يفعل ما يُتقنه، ويُبقيهما تكاملٌ نظيف متزامنين.\n"
            "ينجح هذا النمط تحديدًا لأن النظامين يشتركان في الأساس نفسه — Python — فيستطيع المهندس نفسه استيعاب "
            "الجانبين. والنتيجة حلول بديلة هشّة أقل داخل Odoo، وحلّ قابل للصيانة فعلًا، بدل كومة من الترقيعات تنتظر أن "
            "تنكسر عند الترقية التالية."),
        'meta_description': L(
            "When Odoo configuration isn't enough, a Django integration can close the gap. Learn when to extend Odoo with a Django service and a clean API — and why it is more maintainable.",
            'Cuando la configuración de Odoo no basta, una integración con Django puede cerrar la brecha. Descubre cuándo ampliar Odoo con un servicio Django y una API limpia, y por qué es más mantenible.',
            'عندما لا يكفي إعداد Odoo، يمكن لتكامل Django سدّ الفجوة. تعرّف متى تُوسّع Odoo بخدمة Django وواجهة API نظيفة — ولماذا يكون ذلك أكثر قابلية للصيانة.'),
    },
    {
        'title': L(
            'Outgrowing spreadsheets: signs your business needs a real ERP',
            'Cuando las hojas de cálculo se quedan cortas: señales de que tu negocio necesita un ERP de verdad',
            'حين تعجز جداول البيانات عن مواكبة نموّك: علامات تدلّ على أن نشاطك يحتاج إلى نظام ERP حقيقي'),
        'excerpt': L(
            "Spreadsheets are where most businesses start — and where many quietly get stuck. Here are the signs it is time for a structured ERP like Odoo.",
            "Las hojas de cálculo son donde empiezan casi todos los negocios, y donde muchos se quedan atascados sin darse cuenta. Estas son las señales de que toca dar el paso a un ERP estructurado como Odoo.",
            "جداول البيانات هي نقطة انطلاق معظم الأنشطة — وعندها يتوقّف كثيرون دون أن ينتبهوا. إليك العلامات التي تدلّ على أن وقت الانتقال إلى نظام ERP منظَّم مثل Odoo قد حان."),
        'content': L(
            "Spreadsheets are flexible, familiar, and free — which is exactly why so many businesses run "
            "critical operations on them far longer than they should. For a while it works. Then the cracks "
            "appear: two people edit the same file, a formula silently breaks, last quarter's numbers can't be "
            "reproduced, and onboarding a new hire means explaining a maze of tabs that only one person fully "
            "understands.\n"
            "The warning signs are remarkably consistent across companies. The 'real' version of a number lives "
            "in someone's head or inbox rather than in a system. Different teams keep their own copies of the "
            "same data, and the copies no longer agree. Simple questions — what's in stock, what's unpaid, "
            "what's actually profitable — take hours to answer instead of seconds. Manually re-keying data "
            "between files eats time and quietly introduces errors. And the moment a key person is on holiday, "
            "parts of the business slow to a crawl.\n"
            "An ERP like Odoo replaces that fragile patchwork with a single source of truth: one place where "
            "sales, inventory, invoicing, and reporting share the same data and stay in sync. The goal isn't "
            "more software for its own sake — it's removing the daily friction and risk of running a growing "
            "business on disconnected files. Done well, the system also scales with you, so the setup that fits "
            "ten people still fits fifty.\n"
            "You don't have to move everything at once. The transitions that go best start small: map how the "
            "business actually works today, pick the one or two processes causing the most pain, and structure "
            "those first. If you're not sure whether you've genuinely outgrown spreadsheets or just need to "
            "organise them better, a short conversation is usually enough to tell — and to sketch a realistic, "
            "low-risk path forward.",

            "Las hojas de cálculo son flexibles, conocidas y gratuitas, y precisamente por eso muchas empresas "
            "gestionan en ellas operaciones críticas durante mucho más tiempo del que deberían. Durante un "
            "tiempo funciona. Después aparecen las grietas: dos personas editan el mismo archivo, una fórmula se "
            "rompe sin que nadie lo note, los números del trimestre pasado no se pueden reproducir, e incorporar "
            "a alguien nuevo implica explicarle un laberinto de pestañas que solo una persona entiende del "
            "todo.\n"
            "Las señales de alerta se repiten en casi todas las empresas. La versión «buena» de un dato vive en "
            "la cabeza o en el correo de alguien, en lugar de en un sistema. Cada equipo guarda su propia copia "
            "de los mismos datos, y las copias ya no coinciden. Preguntas sencillas —qué hay en stock, qué está "
            "sin cobrar, qué es realmente rentable— tardan horas en responderse en vez de segundos. Reescribir "
            "datos a mano de un archivo a otro consume tiempo e introduce errores en silencio. Y en cuanto una "
            "persona clave se va de vacaciones, partes del negocio se ralentizan.\n"
            "Un ERP como Odoo sustituye ese frágil rompecabezas por una única fuente de verdad: un solo lugar "
            "donde ventas, inventario, facturación e informes comparten los mismos datos y se mantienen "
            "sincronizados. El objetivo no es tener más software porque sí, sino eliminar la fricción y el "
            "riesgo diarios de gestionar un negocio en crecimiento con archivos desconectados. Bien hecho, "
            "además crece contigo: el sistema que sirve para diez personas sigue sirviendo para cincuenta.\n"
            "No hace falta migrarlo todo de golpe. Las transiciones que mejor salen empiezan poco a poco: "
            "entender cómo funciona de verdad el negocio hoy, elegir los uno o dos procesos que más duelen y "
            "estructurar esos primero. Si no tienes claro si te has quedado sin hojas de cálculo o solo "
            "necesitas ordenarlas mejor, una conversación breve suele bastar para saberlo y para trazar un "
            "camino realista y de bajo riesgo.",

            "جداول البيانات مرنة ومألوفة ومجّانية — ولهذا السبب تحديدًا تدير كثير من الشركات عمليات حسّاسة عليها "
            "مدّةً أطول بكثير مما ينبغي. تنجح الأمور لبعض الوقت، ثم تبدأ الشروخ بالظهور: شخصان يعدّلان الملف نفسه، "
            "ومعادلة تتعطّل بصمت، وأرقام الربع الماضي يتعذّر إعادة إنتاجها، وتدريب موظّف جديد يعني شرح متاهة من "
            "علامات التبويب لا يفهمها بالكامل سوى شخص واحد.\n"
            "وعلامات الإنذار متشابهة إلى حدٍّ لافت بين الشركات. تبقى النسخة «الصحيحة» من الرقم في ذهن أحدهم أو في "
            "بريده بدل أن تكون في نظام. ويحتفظ كل فريق بنسخته الخاصة من البيانات نفسها، ثم لم تعد النسخ متطابقة. "
            "وأسئلة بسيطة — ما المتوفّر في المخزون؟ وما الذي لم يُحصَّل بعد؟ وما المُربح فعلًا؟ — تستغرق ساعات "
            "للإجابة بدل ثوانٍ. وإعادة إدخال البيانات يدويًا بين الملفّات تلتهم الوقت وتُدخل الأخطاء بهدوء. وما إن "
            "يغيب شخص أساسي في إجازة حتى تتباطأ أجزاء من العمل.\n"
            "يستبدل نظام ERP مثل Odoo هذا المزيج الهشّ بمصدر واحد للحقيقة: مكان واحد تتشارك فيه المبيعات والمخزون "
            "والفوترة والتقارير البيانات نفسها وتبقى متزامنة. والهدف ليس مزيدًا من البرمجيات لذاتها، بل إزالة "
            "الاحتكاك والمخاطرة اليوميّين الناتجين عن إدارة نشاط متنامٍ بملفّات غير مترابطة. وحين يُنفَّذ بإتقان، "
            "فإنه ينمو معك أيضًا: النظام الذي يناسب عشرة أشخاص يظلّ مناسبًا لخمسين.\n"
            "ولست مضطرًّا إلى نقل كل شيء دفعةً واحدة. أنجح عمليات الانتقال تبدأ صغيرة: ارسم كيف يعمل النشاط فعليًا "
            "اليوم، واختر العملية أو العمليتين الأكثر إيلامًا، وابدأ بهيكلتها أولًا. وإن لم تكن متأكّدًا هل تجاوزت "
            "جداول البيانات فعلًا أم تحتاج فقط إلى تنظيمها بشكل أفضل، فغالبًا تكفي محادثة قصيرة لمعرفة ذلك ولرسم "
            "مسار واقعي ومنخفض المخاطر للمضيّ قدمًا."),
        'meta_description': L(
            'Spreadsheets holding your business back? The clear signs you have outgrown them — and how a structured ERP like Odoo gives you one source of truth that scales.',
            '¿Las hojas de cálculo frenan tu negocio? Las señales claras de que se te han quedado cortas y cómo un ERP como Odoo te da una única fuente de datos que escala.',
            'هل تعيق جداول البيانات نموّ نشاطك؟ علامات واضحة على أنك تجاوزتها، وكيف يمنحك نظام ERP مثل Odoo مصدرًا واحدًا للبيانات قابلًا للتوسّع.'),
    },
]


# Slugs created by earlier versions of this seeder whose article title — and so
# its slug — later changed. Re-seeding can't update a row whose slug no longer
# matches, so the stale row lingers. Removing these specific, seeder-owned slugs
# lets the command converge to exactly the BLOG_POSTS set, in development and in
# production, without ever touching admin-authored articles.
RETIRED_POST_SLUGS = [
    'how-django-and-odoo-work-together-to-close-business-process-gaps',
]


def expand(data, translatable):
    """Turn L() dicts into _en/_es/_ar model field keys; pass others through."""
    out = {}
    for key, value in data.items():
        if key in translatable and isinstance(value, dict):
            for lang in ('en', 'es', 'ar'):
                out[f'{key}_{lang}'] = value[lang]
        else:
            out[key] = value
    return out


class Command(BaseCommand):
    help = 'Seed the database with English/Spanish/Arabic demo content for Bidatia.'

    def handle(self, *args, **options):
        self.seed_services()
        self.seed_case_studies()
        self.seed_blog_posts()
        self.stdout.write(self.style.SUCCESS('Demo data seeded successfully (EN/ES/AR).'))

    def seed_services(self):
        for data in SERVICES:
            data = dict(data)
            features = data.pop('features')
            faqs = data.pop('faqs')
            # Allow an explicit slug override (keeps stable URLs even when the
            # display title changes); otherwise derive it from the English title.
            slug = data.pop('slug', None) or slugify(data['title']['en'])
            defaults = expand(data, SERVICE_TR)
            defaults['is_published'] = True
            service, created = Service.objects.update_or_create(slug=slug, defaults=defaults)

            service.features.all().delete()
            for i, feature in enumerate(features):
                ServiceFeature.objects.create(
                    service=service, order=i,
                    text_en=feature['en'], text_es=feature['es'], text_ar=feature['ar'],
                )
            service.faqs.all().delete()
            for i, (question, answer) in enumerate(faqs):
                ServiceFAQ.objects.create(
                    service=service, order=i,
                    question_en=question['en'], question_es=question['es'], question_ar=question['ar'],
                    answer_en=answer['en'], answer_es=answer['es'], answer_ar=answer['ar'],
                )
            self.stdout.write(f'  service: {slug} ({"created" if created else "updated"})')

    def seed_case_studies(self):
        for data in CASE_STUDIES:
            slug = slugify(data['title']['en'])
            defaults = expand(data, CASE_TR)
            defaults['is_published'] = True
            case_study, created = CaseStudy.objects.update_or_create(slug=slug, defaults=defaults)
            self.stdout.write(f'  case study: {slug} ({"created" if created else "updated"})')

    def seed_blog_posts(self):
        for data in BLOG_POSTS:
            slug = slugify(data['title']['en'])
            defaults = expand(data, POST_TR)
            defaults['is_published'] = True
            # published_at: set by the model default on creation; preserved on
            # update so re-seeding never resets article dates / lastmod.
            post, created = BlogPost.objects.update_or_create(slug=slug, defaults=defaults)
            self.stdout.write(f'  blog post: {slug} ({"created" if created else "updated"})')
        # Drop rows left behind by earlier seed iterations whose slug changed.
        retired = BlogPost.objects.filter(slug__in=RETIRED_POST_SLUGS)
        for post in retired:
            self.stdout.write(f'  blog post: {post.slug} (retired -> removed)')
        retired.delete()
