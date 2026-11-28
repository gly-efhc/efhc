import type { Lang } from "../lib/i18n";
import { getLegalPolicyMeta } from "./legalPolicyUi";

export type LegalPolicyKind = "terms" | "privacy";

type LegalSection = {
  title: string;
  paragraphs: string[];
};

export type LegalPolicyBase = {
  title: string;
  eyebrow: string;
  updated: string;
  summary: string;
  sections: LegalSection[];
  important: string;
  faq: string;
  back: string;
};

export type LegalPolicyMeta = {
  version: string;
  effectiveDate: string;
  versionLabel: string;
  effectiveLabel: string;
  changesLabel: string;
  sectionIndexLabel: string;
  warningLabel: string;
  supportLabel: string;
  changes: string[];
};

export type LegalPolicy = LegalPolicyBase & LegalPolicyMeta;

type LegalCopy = Record<LegalPolicyKind, LegalPolicyBase>;

function copyText(...parts: string[]): string {
  return parts.join(" ");
}

const COPY: Partial<Record<Lang, LegalCopy>> = {
  ru: {
    privacy: {
      title: "Политика конфиденциальности",
      eyebrow: "Данные и безопасность",
      updated: "Актуальная редакция",
      summary: copyText(
        "Здесь описано, какие данные нужны EFHC Bot,",
        "зачем они используются и как запросить доступ,",
        "исправление или удаление.",
      ),
      sections: [
        {
          title: "Какие данные используются",
          paragraphs: [
            copyText(
              "Идентификатор и общедоступные данные Telegram,",
              "настройки приложения, привязанные публичные",
              "адреса кошельков, история операций, балансы и",
              "записи безопасности.",
            ),
            copyText(
              "EFHC Bot не запрашивает и не хранит seed-фразы,",
              "приватные ключи или пароль от кошелька.",
            ),
          ],
        },
        {
          title: "Зачем нужны данные",
          paragraphs: [
            copyText(
              "Данные используются для работы аккаунта,",
              "отображения балансов, выполнения операций,",
              "предотвращения повторных начислений, защиты от",
              "злоупотреблений и поддержки пользователя.",
            ),
          ],
        },
        {
          title: "Хранение и передача",
          paragraphs: [
            copyText(
              "Данные хранятся столько, сколько необходимо для",
              "работы сервиса, финансовой целостности,",
              "безопасности и выполнения применимых требований.",
            ),
            copyText(
              "Telegram, TON-кошельки, блокчейн и",
              "инфраструктурные поставщики обрабатывают данные",
              "по собственным правилам. Публичные",
              "блокчейн-записи невозможно удалить или изменить.",
            ),
          ],
        },
        {
          title: "Ваши права",
          paragraphs: [
            copyText(
              "Через официальный канал поддержки, указанный в",
              "FAQ, можно запросить копию данных, исправление",
              "или удаление аккаунта.",
            ),
            copyText(
              "Удаление может не распространяться на записи,",
              "которые необходимы для балансовой целостности,",
              "предотвращения мошенничества, разрешения споров",
              "или обязательного хранения.",
            ),
          ],
        },
      ],
      important: copyText(
        "Не передавайте никому seed-фразу, приватный",
        "ключ, код подтверждения или пароль кошелька.",
      ),
      faq: "Открыть FAQ и поддержку",
      back: "Вернуться в профиль",
    },
    terms: {
      title: "Условия использования",
      eyebrow: "Правила сервиса",
      updated: "Актуальная редакция",
      summary: copyText(
        "Используя EFHC Bot, пользователь соглашается",
        "соблюдать правила аккаунта, платежей, защиты от",
        "злоупотреблений и честного использования",
        "функций.",
      ),
      sections: [
        {
          title: "Назначение сервиса",
          paragraphs: [
            copyText(
              "EFHC Bot объединяет энергетический учёт, игровые",
              "механики, социальные функции и операции с EFHC.",
              "Внутренний канон проекта: 1 EFHC соответствует 1",
              "kWh.",
            ),
            copyText(
              "Сервис не обещает гарантированную прибыль, рост",
              "стоимости или инвестиционный результат.",
            ),
          ],
        },
        {
          title: "Балансы и пополнение",
          paragraphs: [
            copyText(
              "Основной и бонусный балансы учитываются",
              "отдельно. Прямое пополнение EFHC jetton",
              "зачисляет EFHC_MAIN в соотношении 1:1 после",
              "подтверждения перевода.",
            ),
            copyText(
              "Покупка через Browser Shop за TON/GRAM или USDT",
              "является отдельным контуром и не смешивается с",
              "прямым пополнением EFHC jetton.",
            ),
          ],
        },
        {
          title: "Платежи и вывод",
          paragraphs: [
            copyText(
              "Блокчейн-транзакцию подписывает пользователь в",
              "своём кошельке. Подтверждённая транзакция может",
              "быть необратимой.",
            ),
            copyText(
              "Для вывода требуется привязанный кошелёк,",
              "достаточный баланс и прохождение предусмотренных",
              "проверок. Статус заявки отображается в истории.",
            ),
          ],
        },
        {
          title: "Честное использование",
          paragraphs: [
            copyText(
              "Запрещены автоматизированные накрутки, повторное",
              "получение наград, обход ограничений, подмена",
              "данных, вмешательство в чужой аккаунт и иные",
              "злоупотребления.",
            ),
            copyText(
              "Подозрительные операции могут быть",
              "приостановлены для проверки без изменения",
              "канонических балансовых правил.",
            ),
          ],
        },
        {
          title: "VIP NFT и изменения",
          paragraphs: [
            copyText(
              "EFHC VIP NFT является отдельным цифровым",
              "объектом и статусной функцией. Он не является",
              "обещанием доходности.",
            ),
            copyText(
              "Правила могут обновляться для безопасности,",
              "законодательства и развития сервиса.",
              "Существенные изменения публикуются в приложении",
              "или официальных каналах.",
            ),
          ],
        },
      ],
      important: copyText(
        "Проверяйте адрес, актив и сумму в кошельке до",
        "подтверждения любой транзакции.",
      ),
      faq: "Открыть FAQ и поддержку",
      back: "Вернуться в профиль",
    },
  },
  en: {
    privacy: {
      title: "Privacy Policy",
      eyebrow: "Data and security",
      updated: "Current version",
      summary: copyText(
        "This policy explains which data EFHC Bot needs,",
        "why it is used, and how to request access,",
        "correction, or deletion.",
      ),
      sections: [
        {
          title: "Data we use",
          paragraphs: [
            copyText(
              "Telegram identifiers and public profile data,",
              "app settings, linked public wallet addresses,",
              "operation history, balances, and security",
              "records.",
            ),
            copyText(
              "EFHC Bot does not request or store seed phrases,",
              "private keys, or wallet passwords.",
            ),
          ],
        },
        {
          title: "Why data is used",
          paragraphs: [
            copyText(
              "Data supports account access, balances,",
              "operations, duplicate-credit prevention, abuse",
              "protection, and user support.",
            ),
          ],
        },
        {
          title: "Storage and sharing",
          paragraphs: [
            copyText(
              "Data is retained only as needed for service",
              "operation, financial integrity, security, and",
              "applicable requirements.",
            ),
            copyText(
              "Telegram, TON wallets, blockchain networks, and",
              "infrastructure providers process data under",
              "their own rules. Public blockchain records",
              "cannot be deleted or changed.",
            ),
          ],
        },
        {
          title: "Your rights",
          paragraphs: [
            copyText(
              "Use the official support channel listed in FAQ",
              "to request a data copy, correction, or account",
              "deletion.",
            ),
            copyText(
              "Deletion may not cover records required for",
              "ledger integrity, fraud prevention, dispute",
              "handling, or mandatory retention.",
            ),
          ],
        },
      ],
      important: copyText(
        "Never share a seed phrase, private key,",
        "confirmation code, or wallet password.",
      ),
      faq: "Open FAQ and support",
      back: "Return to profile",
    },
    terms: {
      title: "Terms of Use",
      eyebrow: "Service rules",
      updated: "Current version",
      summary: copyText(
        "By using EFHC Bot, you agree to the account,",
        "payment, abuse-prevention, and fair-use rules",
        "described here.",
      ),
      sections: [
        {
          title: "Service purpose",
          paragraphs: [
            copyText(
              "EFHC Bot combines energy accounting, game",
              "mechanics, social features, and EFHC operations.",
              "The project canon is 1 EFHC equals 1 kWh.",
            ),
            copyText(
              "The service does not promise guaranteed profit,",
              "price growth, or an investment result.",
            ),
          ],
        },
        {
          title: "Balances and funding",
          paragraphs: [
            copyText(
              "Main and bonus balances are separate. A direct",
              "EFHC jetton deposit credits EFHC_MAIN at 1:1",
              "after transfer confirmation.",
            ),
            copyText(
              "Browser Shop purchases with TON/GRAM or USDT are",
              "a separate flow and are not mixed with direct",
              "EFHC jetton deposits.",
            ),
          ],
        },
        {
          title: "Payments and withdrawals",
          paragraphs: [
            copyText(
              "You sign blockchain transactions in your own",
              "wallet. A confirmed transaction may be",
              "irreversible.",
            ),
            copyText(
              "Withdrawals require a linked wallet, sufficient",
              "balance, and applicable checks. Request status",
              "is shown in history.",
            ),
          ],
        },
        {
          title: "Fair use",
          paragraphs: [
            copyText(
              "Automated farming, duplicate rewards, limit",
              "bypasses, data manipulation, account",
              "interference, and other abuse are prohibited.",
            ),
            copyText(
              "Suspicious operations may be paused for review",
              "without changing canonical balance rules.",
            ),
          ],
        },
        {
          title: "VIP NFT and updates",
          paragraphs: [
            copyText(
              "EFHC VIP NFT is a separate digital object and",
              "status feature. It is not a promise of yield.",
            ),
            copyText(
              "Rules may change for security, legal compliance,",
              "or service development. Material updates are",
              "published in the app or official channels.",
            ),
          ],
        },
      ],
      important: copyText(
        "Check the address, asset, and amount in your",
        "wallet before confirming any transaction.",
      ),
      faq: "Open FAQ and support",
      back: "Return to profile",
    },
  },
  uk: {
    privacy: {
      title: "Політика конфіденційності",
      eyebrow: "Дані та безпека",
      updated: "Чинна редакція",
      summary: copyText(
        "Тут описано, які дані потрібні EFHC Bot, навіщо",
        "вони використовуються та як запросити доступ,",
        "виправлення або видалення.",
      ),
      sections: [
        {
          title: "Які дані використовуються",
          paragraphs: [
            copyText(
              "Ідентифікатор і публічні дані Telegram,",
              "налаштування, прив’язані публічні адреси",
              "гаманців, історія операцій, баланси та записи",
              "безпеки.",
            ),
            copyText(
              "EFHC Bot не запитує і не зберігає seed-фрази,",
              "приватні ключі чи пароль гаманця.",
            ),
          ],
        },
        {
          title: "Мета обробки",
          paragraphs: [
            copyText(
              "Дані потрібні для роботи акаунта, балансів,",
              "операцій, запобігання повторним нарахуванням,",
              "захисту від зловживань і підтримки.",
            ),
          ],
        },
        {
          title: "Зберігання і передача",
          paragraphs: [
            copyText(
              "Дані зберігаються лише стільки, скільки потрібно",
              "для роботи сервісу, фінансової цілісності,",
              "безпеки та застосовних вимог.",
            ),
            copyText(
              "Telegram, TON-гаманці, блокчейн та",
              "інфраструктурні постачальники діють за власними",
              "правилами. Публічні записи блокчейну неможливо",
              "видалити або змінити.",
            ),
          ],
        },
        {
          title: "Ваші права",
          paragraphs: [
            copyText(
              "Через офіційний канал підтримки у FAQ можна",
              "запросити копію даних, виправлення або видалення",
              "акаунта.",
            ),
            copyText(
              "Видалення може не охоплювати записи, потрібні",
              "для цілісності обліку, протидії шахрайству,",
              "спорів або обов’язкового зберігання.",
            ),
          ],
        },
      ],
      important: copyText(
        "Нікому не передавайте seed-фразу, приватний",
        "ключ, код підтвердження чи пароль гаманця.",
      ),
      faq: "Відкрити FAQ і підтримку",
      back: "Повернутися до профілю",
    },
    terms: {
      title: "Умови використання",
      eyebrow: "Правила сервісу",
      updated: "Чинна редакція",
      summary: copyText(
        "Користуючись EFHC Bot, ви погоджуєтеся з",
        "правилами акаунта, платежів, захисту від",
        "зловживань і чесного використання.",
      ),
      sections: [
        {
          title: "Призначення сервісу",
          paragraphs: [
            copyText(
              "EFHC Bot поєднує енергетичний облік, ігрові",
              "механіки, соціальні функції та операції з EFHC.",
              "Канон проєкту: 1 EFHC дорівнює 1 kWh.",
            ),
            copyText(
              "Сервіс не обіцяє гарантований прибуток,",
              "зростання ціни чи інвестиційний результат.",
            ),
          ],
        },
        {
          title: "Баланси і поповнення",
          paragraphs: [
            copyText(
              "Основний і бонусний баланси обліковуються",
              "окремо. Пряме поповнення EFHC jetton зараховує",
              "EFHC_MAIN 1:1 після підтвердження переказу.",
            ),
            copyText(
              "Покупка через Browser Shop за TON/GRAM або USDT",
              "є окремим контуром.",
            ),
          ],
        },
        {
          title: "Платежі і виведення",
          paragraphs: [
            copyText(
              "Блокчейн-транзакцію підписує користувач у",
              "власному гаманці; підтверджена операція може",
              "бути незворотною.",
            ),
            copyText(
              "Для виведення потрібні прив’язаний гаманець,",
              "достатній баланс і передбачені перевірки.",
            ),
          ],
        },
        {
          title: "Чесне використання",
          paragraphs: [
            copyText(
              "Заборонені автоматизовані накрутки, повторні",
              "нагороди, обхід лімітів, підміна даних і",
              "втручання в чужий акаунт.",
            ),
          ],
        },
        {
          title: "VIP NFT і зміни",
          paragraphs: [
            copyText(
              "EFHC VIP NFT є окремим цифровим об’єктом і",
              "статусною функцією, а не обіцянкою дохідності.",
            ),
            copyText(
              "Суттєві зміни правил публікуються в застосунку",
              "або офіційних каналах.",
            ),
          ],
        },
      ],
      important: copyText(
        "Перевіряйте адресу, актив і суму в гаманці до",
        "підтвердження транзакції.",
      ),
      faq: "Відкрити FAQ і підтримку",
      back: "Повернутися до профілю",
    },
  },
  de: {
    privacy: {
      title: "Datenschutzerklärung",
      eyebrow: "Daten und Sicherheit",
      updated: "Aktuelle Fassung",
      summary: copyText(
        "Diese Erklärung beschreibt, welche Daten EFHC",
        "Bot benötigt, warum sie verwendet werden und wie",
        "Auskunft, Berichtigung oder Löschung beantragt",
        "werden kann.",
      ),
      sections: [
        {
          title: "Verwendete Daten",
          paragraphs: [
            copyText(
              "Telegram-Kennung und öffentliche Profildaten,",
              "Einstellungen, verknüpfte öffentliche",
              "Wallet-Adressen, Vorgangsverlauf, Guthaben und",
              "Sicherheitsprotokolle.",
            ),
            copyText(
              "EFHC Bot fordert keine Seed-Phrase, privaten",
              "Schlüssel oder Wallet-Passwörter an und",
              "speichert sie nicht.",
            ),
          ],
        },
        {
          title: "Verwendungszweck",
          paragraphs: [
            copyText(
              "Die Daten ermöglichen Konto, Guthaben, Vorgänge,",
              "Schutz vor Doppelgutschriften, Missbrauchsschutz",
              "und Support.",
            ),
          ],
        },
        {
          title: "Speicherung und Weitergabe",
          paragraphs: [
            copyText(
              "Daten werden nur so lange aufbewahrt, wie",
              "Betrieb, finanzielle Integrität, Sicherheit und",
              "geltende Pflichten es erfordern.",
            ),
            copyText(
              "Telegram, TON-Wallets, Blockchain und",
              "Infrastruktur-Anbieter handeln nach eigenen",
              "Regeln. Öffentliche Blockchain-Daten sind nicht",
              "löschbar.",
            ),
          ],
        },
        {
          title: "Ihre Rechte",
          paragraphs: [
            copyText(
              "Über den offiziellen Support im FAQ können",
              "Datenkopie, Berichtigung oder Kontolöschung",
              "beantragt werden.",
            ),
            copyText(
              "Notwendige Buchungs-, Betrugs-, Streit- oder",
              "Aufbewahrungsdaten können von der Löschung",
              "ausgenommen sein.",
            ),
          ],
        },
      ],
      important: copyText(
        "Geben Sie niemals Seed-Phrase, privaten",
        "Schlüssel, Bestätigungscode oder Wallet-Passwort",
        "weiter.",
      ),
      faq: "FAQ und Support öffnen",
      back: "Zum Profil zurückkehren",
    },
    terms: {
      title: "Nutzungsbedingungen",
      eyebrow: "Serviceregeln",
      updated: "Aktuelle Fassung",
      summary: copyText(
        "Mit der Nutzung von EFHC Bot akzeptieren Sie die",
        "Regeln zu Konto, Zahlungen, Missbrauchsschutz",
        "und fairer Nutzung.",
      ),
      sections: [
        {
          title: "Zweck",
          paragraphs: [
            copyText(
              "EFHC Bot verbindet Energieerfassung,",
              "Spielmechanik, soziale Funktionen und",
              "EFHC-Vorgänge. Projektkanon: 1 EFHC entspricht 1",
              "kWh.",
            ),
            copyText(
              "Es gibt keine Garantie für Gewinn,",
              "Wertsteigerung oder Anlageerfolg.",
            ),
          ],
        },
        {
          title: "Guthaben und Einzahlung",
          paragraphs: [
            copyText(
              "Haupt- und Bonusguthaben sind getrennt. Eine",
              "direkte EFHC-Jetton-Einzahlung schreibt",
              "EFHC_MAIN nach Bestätigung 1:1 gut.",
            ),
            copyText(
              "Browser-Shop-Käufe mit TON/GRAM oder USDT sind",
              "ein eigener Ablauf.",
            ),
          ],
        },
        {
          title: "Zahlungen und Auszahlungen",
          paragraphs: [
            copyText(
              "Blockchain-Transaktionen werden im eigenen",
              "Wallet signiert und können nach Bestätigung",
              "unwiderruflich sein.",
            ),
            copyText(
              "Auszahlungen benötigen ein verknüpftes Wallet,",
              "ausreichendes Guthaben und Prüfungen.",
            ),
          ],
        },
        {
          title: "Faire Nutzung",
          paragraphs: [
            copyText(
              "Automatisierte Manipulation, doppelte Prämien,",
              "Umgehung von Limits, Datenfälschung und",
              "Kontoeingriffe sind verboten.",
            ),
          ],
        },
        {
          title: "VIP NFT und Änderungen",
          paragraphs: [
            copyText(
              "EFHC VIP NFT ist ein separates digitales Objekt",
              "und Statusmerkmal, keine Renditezusage.",
            ),
            copyText(
              "Wesentliche Änderungen werden in der App oder",
              "offiziellen Kanälen veröffentlicht.",
            ),
          ],
        },
      ],
      important: copyText(
        "Prüfen Sie Adresse, Asset und Betrag vor jeder",
        "Bestätigung.",
      ),
      faq: "FAQ und Support öffnen",
      back: "Zum Profil zurückkehren",
    },
  },
  fr: {
    privacy: {
      title: "Politique de confidentialité",
      eyebrow: "Données et sécurité",
      updated: "Version actuelle",
      summary: copyText(
        "Cette politique explique les données nécessaires",
        "à EFHC Bot, leur utilisation et la manière de",
        "demander accès, rectification ou suppression.",
      ),
      sections: [
        {
          title: "Données utilisées",
          paragraphs: [
            copyText(
              "Identifiant et profil public Telegram,",
              "préférences, adresses publiques de portefeuille",
              "liées, historique, soldes et traces de sécurité.",
            ),
            copyText(
              "EFHC Bot ne demande ni ne conserve phrase de",
              "récupération, clé privée ou mot de passe du",
              "portefeuille.",
            ),
          ],
        },
        {
          title: "Finalités",
          paragraphs: [
            copyText(
              "Les données servent au compte, aux soldes, aux",
              "opérations, à la prévention des doubles crédits,",
              "à la lutte contre les abus et au support.",
            ),
          ],
        },
        {
          title: "Conservation et partage",
          paragraphs: [
            copyText(
              "Les données sont conservées selon les besoins du",
              "service, de l’intégrité financière, de la",
              "sécurité et des obligations applicables.",
            ),
            copyText(
              "Telegram, les portefeuilles TON, la blockchain",
              "et les prestataires appliquent leurs propres",
              "règles. Les données publiques de blockchain sont",
              "immuables.",
            ),
          ],
        },
        {
          title: "Vos droits",
          paragraphs: [
            copyText(
              "Le canal officiel indiqué dans la FAQ permet de",
              "demander copie, correction ou suppression du",
              "compte.",
            ),
            copyText(
              "Certaines écritures nécessaires à l’intégrité, à",
              "la lutte contre la fraude, aux litiges ou à la",
              "conservation obligatoire peuvent être",
              "maintenues.",
            ),
          ],
        },
      ],
      important: copyText(
        "Ne partagez jamais phrase de récupération, clé",
        "privée, code de confirmation ou mot de passe.",
      ),
      faq: "Ouvrir la FAQ et le support",
      back: "Retour au profil",
    },
    terms: {
      title: "Conditions d’utilisation",
      eyebrow: "Règles du service",
      updated: "Version actuelle",
      summary: copyText(
        "En utilisant EFHC Bot, vous acceptez les règles",
        "relatives au compte, aux paiements, à la",
        "prévention des abus et à l’usage loyal.",
      ),
      sections: [
        {
          title: "Objet",
          paragraphs: [
            copyText(
              "EFHC Bot réunit comptabilité énergétique,",
              "mécanismes de jeu, fonctions sociales et",
              "opérations EFHC. Canon du projet : 1 EFHC = 1",
              "kWh.",
            ),
            copyText(
              "Aucun bénéfice, hausse de prix ou résultat",
              "d’investissement n’est garanti.",
            ),
          ],
        },
        {
          title: "Soldes et approvisionnement",
          paragraphs: [
            copyText(
              "Les soldes principal et bonus sont séparés. Un",
              "dépôt direct d’EFHC jetton crédite EFHC_MAIN 1:1",
              "après confirmation.",
            ),
            copyText(
              "Les achats Browser Shop en TON/GRAM ou USDT",
              "suivent un circuit distinct.",
            ),
          ],
        },
        {
          title: "Paiements et retraits",
          paragraphs: [
            copyText(
              "Vous signez les transactions blockchain dans",
              "votre portefeuille; une transaction confirmée",
              "peut être irréversible.",
            ),
            copyText(
              "Un retrait exige un portefeuille lié, un solde",
              "suffisant et les contrôles prévus.",
            ),
          ],
        },
        {
          title: "Usage loyal",
          paragraphs: [
            copyText(
              "Automatisation abusive, récompenses dupliquées,",
              "contournement des limites, falsification et",
              "intrusion sont interdits.",
            ),
          ],
        },
        {
          title: "VIP NFT et mises à jour",
          paragraphs: [
            copyText(
              "EFHC VIP NFT est un objet numérique et un statut",
              "distinct, sans promesse de rendement.",
            ),
            copyText(
              "Les changements importants sont publiés dans",
              "l’application ou les canaux officiels.",
            ),
          ],
        },
      ],
      important:
        "Vérifiez adresse, actif et montant avant de confirmer.",
      faq: "Ouvrir la FAQ et le support",
      back: "Retour au profil",
    },
  },
  es: {
    privacy: {
      title: "Política de privacidad",
      eyebrow: "Datos y seguridad",
      updated: "Versión vigente",
      summary: copyText(
        "Explica qué datos necesita EFHC Bot, para qué se",
        "usan y cómo solicitar acceso, corrección o",
        "eliminación.",
      ),
      sections: [
        {
          title: "Datos utilizados",
          paragraphs: [
            copyText(
              "Identificador y perfil público de Telegram,",
              "ajustes, direcciones públicas vinculadas,",
              "historial, saldos y registros de seguridad.",
            ),
            copyText(
              "EFHC Bot no solicita ni almacena frases semilla,",
              "claves privadas o contraseñas de la cartera.",
            ),
          ],
        },
        {
          title: "Finalidad",
          paragraphs: [
            copyText(
              "Los datos permiten operar la cuenta, saldos y",
              "funciones, evitar créditos duplicados, prevenir",
              "abusos y prestar soporte.",
            ),
          ],
        },
        {
          title: "Conservación y terceros",
          paragraphs: [
            copyText(
              "Los datos se conservan según lo necesario para",
              "el servicio, integridad financiera, seguridad y",
              "requisitos aplicables.",
            ),
            copyText(
              "Telegram, carteras TON, blockchain y proveedores",
              "aplican sus propias reglas. Los registros",
              "públicos de blockchain no pueden borrarse.",
            ),
          ],
        },
        {
          title: "Tus derechos",
          paragraphs: [
            copyText(
              "El canal oficial de la FAQ permite pedir copia,",
              "corrección o eliminación de la cuenta.",
            ),
            copyText(
              "Pueden conservarse registros necesarios para",
              "integridad contable, fraude, disputas u",
              "obligaciones de retención.",
            ),
          ],
        },
      ],
      important: copyText(
        "Nunca compartas frase semilla, clave privada,",
        "código de confirmación o contraseña.",
      ),
      faq: "Abrir FAQ y soporte",
      back: "Volver al perfil",
    },
    terms: {
      title: "Condiciones de uso",
      eyebrow: "Reglas del servicio",
      updated: "Versión vigente",
      summary: copyText(
        "Al usar EFHC Bot aceptas las reglas de cuenta,",
        "pagos, prevención de abusos y uso justo.",
      ),
      sections: [
        {
          title: "Finalidad",
          paragraphs: [
            copyText(
              "EFHC Bot combina contabilidad energética,",
              "mecánicas de juego, funciones sociales y",
              "operaciones EFHC. Canon: 1 EFHC equivale a 1",
              "kWh.",
            ),
            copyText(
              "No se garantiza beneficio, aumento de precio ni",
              "resultado de inversión.",
            ),
          ],
        },
        {
          title: "Saldos y recargas",
          paragraphs: [
            copyText(
              "Los saldos principal y bonus están separados. Un",
              "depósito directo de EFHC jetton acredita",
              "EFHC_MAIN 1:1 tras confirmación.",
            ),
            copyText(
              "Las compras en Browser Shop con TON/GRAM o USDT",
              "son un flujo separado.",
            ),
          ],
        },
        {
          title: "Pagos y retiros",
          paragraphs: [
            copyText(
              "Las transacciones se firman en tu cartera y, una",
              "vez confirmadas, pueden ser irreversibles.",
            ),
            copyText(
              "El retiro requiere cartera vinculada, saldo",
              "suficiente y controles aplicables.",
            ),
          ],
        },
        {
          title: "Uso justo",
          paragraphs: [
            copyText(
              "Se prohíben automatización abusiva, recompensas",
              "duplicadas, evasión de límites, falsificación e",
              "intervención en otras cuentas.",
            ),
          ],
        },
        {
          title: "VIP NFT y cambios",
          paragraphs: [
            copyText(
              "EFHC VIP NFT es un objeto digital y estado",
              "separado, sin promesa de rendimiento.",
            ),
            copyText(
              "Los cambios relevantes se publican en la",
              "aplicación o canales oficiales.",
            ),
          ],
        },
      ],
      important:
        "Comprueba dirección, activo e importe antes de confirmar.",
      faq: "Abrir FAQ y soporte",
      back: "Volver al perfil",
    },
  },
  it: {
    privacy: {
      title: "Informativa sulla privacy",
      eyebrow: "Dati e sicurezza",
      updated: "Versione corrente",
      summary: copyText(
        "Descrive i dati necessari a EFHC Bot, il loro",
        "uso e come chiedere accesso, correzione o",
        "cancellazione.",
      ),
      sections: [
        {
          title: "Dati utilizzati",
          paragraphs: [
            copyText(
              "Identificativo e profilo pubblico Telegram,",
              "impostazioni, indirizzi pubblici collegati,",
              "cronologia, saldi e registri di sicurezza.",
            ),
            copyText(
              "EFHC Bot non richiede né conserva seed phrase,",
              "chiavi private o password del wallet.",
            ),
          ],
        },
        {
          title: "Finalità",
          paragraphs: [
            copyText(
              "I dati servono per account, saldi, operazioni,",
              "prevenzione di accrediti doppi, contrasto agli",
              "abusi e assistenza.",
            ),
          ],
        },
        {
          title: "Conservazione e terzi",
          paragraphs: [
            copyText(
              "I dati restano solo quanto necessario per",
              "servizio, integrità finanziaria, sicurezza e",
              "obblighi applicabili.",
            ),
            copyText(
              "Telegram, wallet TON, blockchain e fornitori",
              "seguono regole proprie. I registri pubblici",
              "blockchain non sono cancellabili.",
            ),
          ],
        },
        {
          title: "Diritti",
          paragraphs: [
            copyText(
              "Il canale ufficiale nella FAQ consente di",
              "chiedere copia, correzione o cancellazione",
              "dell’account.",
            ),
            copyText(
              "Possono restare registri necessari per",
              "contabilità, antifrode, controversie o",
              "conservazione obbligatoria.",
            ),
          ],
        },
      ],
      important: copyText(
        "Non condividere seed phrase, chiave privata,",
        "codice di conferma o password.",
      ),
      faq: "Apri FAQ e assistenza",
      back: "Torna al profilo",
    },
    terms: {
      title: "Termini di utilizzo",
      eyebrow: "Regole del servizio",
      updated: "Versione corrente",
      summary: copyText(
        "Usando EFHC Bot accetti le regole su account,",
        "pagamenti, prevenzione degli abusi e uso",
        "corretto.",
      ),
      sections: [
        {
          title: "Scopo",
          paragraphs: [
            copyText(
              "EFHC Bot unisce contabilità energetica,",
              "meccaniche di gioco, funzioni sociali e",
              "operazioni EFHC. Canone: 1 EFHC = 1 kWh.",
            ),
            copyText(
              "Non sono garantiti profitto, crescita di prezzo",
              "o risultato d’investimento.",
            ),
          ],
        },
        {
          title: "Saldi e ricariche",
          paragraphs: [
            copyText(
              "Saldo principale e bonus sono separati. Un",
              "deposito diretto EFHC jetton accredita EFHC_MAIN",
              "1:1 dopo conferma.",
            ),
            copyText(
              "Gli acquisti Browser Shop in TON/GRAM o USDT",
              "sono separati.",
            ),
          ],
        },
        {
          title: "Pagamenti e prelievi",
          paragraphs: [
            copyText(
              "Le transazioni sono firmate nel proprio wallet e",
              "possono essere irreversibili dopo conferma.",
            ),
            copyText(
              "Il prelievo richiede wallet collegato, saldo",
              "sufficiente e controlli previsti.",
            ),
          ],
        },
        {
          title: "Uso corretto",
          paragraphs: [
            copyText(
              "Sono vietati automazione abusiva, premi",
              "duplicati, aggiramento dei limiti,",
              "falsificazione e accesso ad account altrui.",
            ),
          ],
        },
        {
          title: "VIP NFT e modifiche",
          paragraphs: [
            copyText(
              "EFHC VIP NFT è un oggetto digitale e stato",
              "separato, senza promessa di rendimento.",
            ),
            copyText(
              "Le modifiche importanti sono pubblicate nell’app",
              "o nei canali ufficiali.",
            ),
          ],
        },
      ],
      important:
        "Controlla indirizzo, asset e importo prima di confermare.",
      faq: "Apri FAQ e assistenza",
      back: "Torna al profilo",
    },
  },
  tr: {
    privacy: {
      title: "Gizlilik Politikası",
      eyebrow: "Veri ve güvenlik",
      updated: "Güncel sürüm",
      summary: copyText(
        "EFHC Bot’un hangi verilere ihtiyaç duyduğunu,",
        "neden kullandığını ve erişim, düzeltme veya",
        "silme talebini açıklar.",
      ),
      sections: [
        {
          title: "Kullanılan veriler",
          paragraphs: [
            copyText(
              "Telegram kimliği ve açık profil bilgileri,",
              "ayarlar, bağlı açık cüzdan adresleri, işlem",
              "geçmişi, bakiyeler ve güvenlik kayıtları.",
            ),
            copyText(
              "EFHC Bot seed ifade, özel anahtar veya cüzdan",
              "parolası istemez ve saklamaz.",
            ),
          ],
        },
        {
          title: "Kullanım amacı",
          paragraphs: [
            copyText(
              "Veriler hesap, bakiye ve işlemler, çift krediyi",
              "önleme, kötüye kullanım koruması ve destek için",
              "kullanılır.",
            ),
          ],
        },
        {
          title: "Saklama ve üçüncü taraflar",
          paragraphs: [
            copyText(
              "Veriler hizmet, finansal bütünlük, güvenlik ve",
              "geçerli gereklilikler için gerekli süre boyunca",
              "tutulur.",
            ),
            copyText(
              "Telegram, TON cüzdanları, blokzincir ve altyapı",
              "sağlayıcıları kendi kurallarını uygular. Açık",
              "blokzincir kayıtları silinemez.",
            ),
          ],
        },
        {
          title: "Haklarınız",
          paragraphs: [
            copyText(
              "FAQ’daki resmî destek kanalından veri kopyası,",
              "düzeltme veya hesap silme talep edilebilir.",
            ),
            copyText(
              "Muhasebe bütünlüğü, dolandırıcılık, uyuşmazlık",
              "veya zorunlu saklama kayıtları tutulabilir.",
            ),
          ],
        },
      ],
      important: copyText(
        "Seed ifade, özel anahtar, doğrulama kodu veya",
        "cüzdan parolasını paylaşmayın.",
      ),
      faq: "FAQ ve desteği aç",
      back: "Profile dön",
    },
    terms: {
      title: "Kullanım Koşulları",
      eyebrow: "Hizmet kuralları",
      updated: "Güncel sürüm",
      summary: copyText(
        "EFHC Bot’u kullanarak hesap, ödeme, kötüye",
        "kullanım önleme ve adil kullanım kurallarını",
        "kabul edersiniz.",
      ),
      sections: [
        {
          title: "Amaç",
          paragraphs: [
            copyText(
              "EFHC Bot enerji muhasebesi, oyun mekanikleri,",
              "sosyal işlevler ve EFHC işlemlerini birleştirir.",
              "Proje kanonu: 1 EFHC = 1 kWh.",
            ),
            copyText(
              "Garantili kâr, fiyat artışı veya yatırım sonucu",
              "vaat edilmez.",
            ),
          ],
        },
        {
          title: "Bakiyeler ve yükleme",
          paragraphs: [
            copyText(
              "Ana ve bonus bakiye ayrıdır. Doğrudan EFHC",
              "jetton yatırımı onaydan sonra EFHC_MAIN’e 1:1",
              "geçer.",
            ),
            copyText(
              "TON/GRAM veya USDT ile Browser Shop alımı ayrı",
              "bir akıştır.",
            ),
          ],
        },
        {
          title: "Ödeme ve çekim",
          paragraphs: [
            copyText(
              "Blokzincir işlemini kendi cüzdanınızda",
              "imzalarsınız ve onaylanan işlem geri",
              "alınamayabilir.",
            ),
            copyText(
              "Çekim için bağlı cüzdan, yeterli bakiye ve",
              "kontroller gerekir.",
            ),
          ],
        },
        {
          title: "Adil kullanım",
          paragraphs: [
            copyText(
              "Otomatik kötüye kullanım, çift ödül, limit aşma,",
              "veri tahrifi ve başka hesaba müdahale yasaktır.",
            ),
          ],
        },
        {
          title: "VIP NFT ve değişiklikler",
          paragraphs: [
            copyText(
              "EFHC VIP NFT ayrı bir dijital nesne ve statüdür;",
              "getiri vaadi değildir.",
            ),
            copyText(
              "Önemli değişiklikler uygulama veya resmî",
              "kanallarda yayımlanır.",
            ),
          ],
        },
      ],
      important:
        "Onaydan önce adresi, varlığı ve tutarı kontrol edin.",
      faq: "FAQ ve desteği aç",
      back: "Profile dön",
    },
  },
  pl: {
    privacy: {
      title: "Polityka prywatności",
      eyebrow: "Dane i bezpieczeństwo",
      updated: "Aktualna wersja",
      summary: copyText(
        "Wyjaśnia, jakich danych potrzebuje EFHC Bot, po",
        "co są używane i jak poprosić o dostęp,",
        "poprawienie lub usunięcie.",
      ),
      sections: [
        {
          title: "Używane dane",
          paragraphs: [
            copyText(
              "Identyfikator i publiczny profil Telegram,",
              "ustawienia, powiązane publiczne adresy portfeli,",
              "historia, salda i zapisy bezpieczeństwa.",
            ),
            copyText(
              "EFHC Bot nie żąda ani nie przechowuje frazy",
              "seed, klucza prywatnego ani hasła portfela.",
            ),
          ],
        },
        {
          title: "Cel",
          paragraphs: [
            copyText(
              "Dane obsługują konto, salda, operacje, ochronę",
              "przed podwójnym naliczeniem, nadużyciami i",
              "wsparcie.",
            ),
          ],
        },
        {
          title: "Przechowywanie i podmioty trzecie",
          paragraphs: [
            copyText(
              "Dane są przechowywane tak długo, jak wymaga tego",
              "usługa, integralność finansowa, bezpieczeństwo i",
              "obowiązki.",
            ),
            copyText(
              "Telegram, portfele TON, blockchain i dostawcy",
              "stosują własne zasady. Publicznych zapisów",
              "blockchain nie można usunąć.",
            ),
          ],
        },
        {
          title: "Twoje prawa",
          paragraphs: [
            copyText(
              "Przez oficjalny kanał w FAQ można poprosić o",
              "kopię, poprawienie lub usunięcie konta.",
            ),
            copyText(
              "Zapisy potrzebne dla księgi, ochrony przed",
              "oszustwami, sporów lub obowiązkowego",
              "przechowywania mogą pozostać.",
            ),
          ],
        },
      ],
      important: copyText(
        "Nigdy nie udostępniaj frazy seed, klucza",
        "prywatnego, kodu ani hasła.",
      ),
      faq: "Otwórz FAQ i wsparcie",
      back: "Wróć do profilu",
    },
    terms: {
      title: "Warunki korzystania",
      eyebrow: "Zasady usługi",
      updated: "Aktualna wersja",
      summary: copyText(
        "Korzystając z EFHC Bot, akceptujesz zasady",
        "konta, płatności, ochrony przed nadużyciami i",
        "uczciwego użycia.",
      ),
      sections: [
        {
          title: "Cel",
          paragraphs: [
            copyText(
              "EFHC Bot łączy rozliczenie energii, mechaniki",
              "gry, funkcje społeczne i operacje EFHC. Kanon: 1",
              "EFHC = 1 kWh.",
            ),
            copyText(
              "Nie ma gwarancji zysku, wzrostu ceny ani wyniku",
              "inwestycji.",
            ),
          ],
        },
        {
          title: "Salda i zasilenie",
          paragraphs: [
            copyText(
              "Saldo główne i bonusowe są oddzielne.",
              "Bezpośredni depozyt EFHC jetton zasila EFHC_MAIN",
              "1:1 po potwierdzeniu.",
            ),
            copyText(
              "Zakupy Browser Shop w TON/GRAM lub USDT są",
              "oddzielnym procesem.",
            ),
          ],
        },
        {
          title: "Płatności i wypłaty",
          paragraphs: [
            copyText(
              "Transakcję podpisujesz we własnym portfelu; po",
              "potwierdzeniu może być nieodwracalna.",
            ),
            copyText(
              "Wypłata wymaga powiązanego portfela,",
              "wystarczającego salda i kontroli.",
            ),
          ],
        },
        {
          title: "Uczciwe użycie",
          paragraphs: [
            copyText(
              "Zakazane są automatyczne nadużycia, podwójne",
              "nagrody, obchodzenie limitów, fałszowanie danych",
              "i ingerencja w cudze konto.",
            ),
          ],
        },
        {
          title: "VIP NFT i zmiany",
          paragraphs: [
            copyText(
              "EFHC VIP NFT jest oddzielnym obiektem cyfrowym i",
              "statusem, bez obietnicy zysku.",
            ),
            copyText(
              "Istotne zmiany są publikowane w aplikacji lub",
              "oficjalnych kanałach.",
            ),
          ],
        },
      ],
      important:
        "Sprawdź adres, aktywo i kwotę przed zatwierdzeniem.",
      faq: "Otwórz FAQ i wsparcie",
      back: "Wróć do profilu",
    },
  },
  da: {
    privacy: {
      title: "Privatlivspolitik",
      eyebrow: "Data og sikkerhed",
      updated: "Gældende version",
      summary: copyText(
        "Forklarer hvilke data EFHC Bot bruger, hvorfor",
        "de bruges, og hvordan adgang, rettelse eller",
        "sletning anmodes.",
      ),
      sections: [
        {
          title: "Data vi bruger",
          paragraphs: [
            copyText(
              "Telegram-id og offentlig profil, indstillinger,",
              "tilknyttede offentlige wallet-adresser,",
              "historik, saldi og sikkerhedsregistreringer.",
            ),
            copyText(
              "EFHC Bot beder ikke om eller gemmer seed phrase,",
              "privat nøgle eller wallet-adgangskode.",
            ),
          ],
        },
        {
          title: "Formål",
          paragraphs: [
            copyText(
              "Data bruges til konto, saldi, handlinger,",
              "beskyttelse mod dobbelt kreditering, misbrug og",
              "support.",
            ),
          ],
        },
        {
          title: "Opbevaring og tredjeparter",
          paragraphs: [
            copyText(
              "Data opbevares kun, når drift, finansiel",
              "integritet, sikkerhed og gældende krav kræver",
              "det.",
            ),
            copyText(
              "Telegram, TON-wallets, blockchain og",
              "leverandører har egne regler. Offentlige",
              "blockchain-poster kan ikke slettes.",
            ),
          ],
        },
        {
          title: "Dine rettigheder",
          paragraphs: [
            copyText(
              "Via den officielle support i FAQ kan du bede om",
              "kopi, rettelse eller kontosletning.",
            ),
            copyText(
              "Poster til regnskabsintegritet, svindel, tvister",
              "eller lovpligtig opbevaring kan bevares.",
            ),
          ],
        },
      ],
      important: copyText(
        "Del aldrig seed phrase, privat nøgle,",
        "bekræftelseskode eller adgangskode.",
      ),
      faq: "Åbn FAQ og support",
      back: "Tilbage til profil",
    },
    terms: {
      title: "Brugsvilkår",
      eyebrow: "Serviceregler",
      updated: "Gældende version",
      summary: copyText(
        "Ved brug af EFHC Bot accepterer du regler om",
        "konto, betaling, misbrugsbeskyttelse og fair",
        "brug.",
      ),
      sections: [
        {
          title: "Formål",
          paragraphs: [
            copyText(
              "EFHC Bot samler energiregnskab, spilmekanik,",
              "sociale funktioner og EFHC-handlinger. Kanon: 1",
              "EFHC = 1 kWh.",
            ),
            copyText(
              "Der gives ingen garanti for fortjeneste,",
              "prisstigning eller investeringsresultat.",
            ),
          ],
        },
        {
          title: "Saldi og indbetaling",
          paragraphs: [
            copyText(
              "Hoved- og bonussaldo er adskilt. Direkte EFHC",
              "jetton-indbetaling krediterer EFHC_MAIN 1:1",
              "efter bekræftelse.",
            ),
            copyText(
              "Browser Shop-køb med TON/GRAM eller USDT er et",
              "særskilt forløb.",
            ),
          ],
        },
        {
          title: "Betaling og udbetaling",
          paragraphs: [
            copyText(
              "Du signerer blockchain-transaktioner i egen",
              "wallet; en bekræftet transaktion kan være",
              "uigenkaldelig.",
            ),
            copyText(
              "Udbetaling kræver tilknyttet wallet,",
              "tilstrækkelig saldo og kontroller.",
            ),
          ],
        },
        {
          title: "Fair brug",
          paragraphs: [
            copyText(
              "Automatiseret misbrug, dobbelte belønninger,",
              "omgåelse af grænser, falske data og indgreb i",
              "andres konto er forbudt.",
            ),
          ],
        },
        {
          title: "VIP NFT og ændringer",
          paragraphs: [
            copyText(
              "EFHC VIP NFT er et separat digitalt objekt og",
              "status, ikke et løfte om afkast.",
            ),
            copyText(
              "Væsentlige ændringer offentliggøres i appen",
              "eller officielle kanaler.",
            ),
          ],
        },
      ],
      important:
        "Kontrollér adresse, aktiv og beløb før bekræftelse.",
      faq: "Åbn FAQ og support",
      back: "Tilbage til profil",
    },
  },
  hi: {
    privacy: {
      title: "गोपनीयता नीति",
      eyebrow: "डेटा और सुरक्षा",
      updated: "वर्तमान संस्करण",
      summary: copyText(
        "यह बताता है कि EFHC Bot को कौन-सा डेटा चाहिए,",
        "उसका उपयोग क्यों होता है और पहुँच, सुधार या",
        "हटाने का अनुरोध कैसे करें।",
      ),
      sections: [
        {
          title: "उपयोग किया गया डेटा",
          paragraphs: [
            copyText(
              "Telegram पहचान और सार्वजनिक प्रोफ़ाइल, सेटिंग्स,",
              "जुड़े सार्वजनिक वॉलेट पते, इतिहास, बैलेंस और",
              "सुरक्षा रिकॉर्ड।",
            ),
            copyText(
              "EFHC Bot seed phrase, निजी कुंजी या वॉलेट",
              "पासवर्ड नहीं मांगता और न ही संग्रहीत करता है।",
            ),
          ],
        },
        {
          title: "उद्देश्य",
          paragraphs: [
            copyText(
              "डेटा खाता, बैलेंस, संचालन, दोहरे क्रेडिट की",
              "रोकथाम, दुरुपयोग सुरक्षा और सहायता के लिए उपयोग",
              "होता है।",
            ),
          ],
        },
        {
          title: "संग्रह और तीसरे पक्ष",
          paragraphs: [
            copyText(
              "डेटा केवल सेवा, वित्तीय अखंडता, सुरक्षा और लागू",
              "आवश्यकताओं के लिए जरूरी अवधि तक रखा जाता है।",
            ),
            copyText(
              "Telegram, TON वॉलेट, ब्लॉकचेन और प्रदाता अपने",
              "नियम लागू करते हैं। सार्वजनिक ब्लॉकचेन रिकॉर्ड",
              "हटाए नहीं जा सकते।",
            ),
          ],
        },
        {
          title: "आपके अधिकार",
          paragraphs: [
            copyText(
              "FAQ में दिए आधिकारिक सहायता चैनल से डेटा कॉपी,",
              "सुधार या खाता हटाने का अनुरोध किया जा सकता है।",
            ),
            copyText(
              "लेजर अखंडता, धोखाधड़ी, विवाद या अनिवार्य संग्रह",
              "के रिकॉर्ड रखे जा सकते हैं।",
            ),
          ],
        },
      ],
      important: copyText(
        "Seed phrase, निजी कुंजी, पुष्टि कोड या वॉलेट",
        "पासवर्ड कभी साझा न करें।",
      ),
      faq: "FAQ और सहायता खोलें",
      back: "प्रोफ़ाइल पर लौटें",
    },
    terms: {
      title: "उपयोग की शर्तें",
      eyebrow: "सेवा नियम",
      updated: "वर्तमान संस्करण",
      summary: copyText(
        "EFHC Bot का उपयोग करके आप खाता, भुगतान, दुरुपयोग",
        "रोकथाम और उचित उपयोग के नियम स्वीकार करते हैं।",
      ),
      sections: [
        {
          title: "सेवा का उद्देश्य",
          paragraphs: [
            copyText(
              "EFHC Bot ऊर्जा लेखांकन, गेम यांत्रिकी, सामाजिक",
              "सुविधाएँ और EFHC संचालन जोड़ता है। परियोजना",
              "नियम: 1 EFHC = 1 kWh।",
            ),
            "लाभ, मूल्य वृद्धि या निवेश परिणाम की गारंटी नहीं है।",
          ],
        },
        {
          title: "बैलेंस और फंडिंग",
          paragraphs: [
            copyText(
              "मुख्य और बोनस बैलेंस अलग हैं। सीधे EFHC jetton",
              "जमा से पुष्टि के बाद EFHC_MAIN 1:1 क्रेडिट होता",
              "है।",
            ),
            "TON/GRAM या USDT से Browser Shop खरीद अलग प्रक्रिया है।",
          ],
        },
        {
          title: "भुगतान और निकासी",
          paragraphs: [
            copyText(
              "ब्लॉकचेन लेनदेन अपने वॉलेट में हस्ताक्षरित होता",
              "है और पुष्टि के बाद अपरिवर्तनीय हो सकता है।",
            ),
            copyText(
              "निकासी के लिए जुड़ा वॉलेट, पर्याप्त बैलेंस और",
              "आवश्यक जाँच चाहिए।",
            ),
          ],
        },
        {
          title: "उचित उपयोग",
          paragraphs: [
            copyText(
              "स्वचालित दुरुपयोग, दोहरा पुरस्कार, सीमा से बचना,",
              "गलत डेटा और दूसरे खाते में हस्तक्षेप निषिद्ध है।",
            ),
          ],
        },
        {
          title: "VIP NFT और बदलाव",
          paragraphs: [
            copyText(
              "EFHC VIP NFT अलग डिजिटल वस्तु और स्थिति है, आय",
              "का वादा नहीं।",
            ),
            copyText(
              "महत्वपूर्ण बदलाव ऐप या आधिकारिक चैनलों में",
              "प्रकाशित होते हैं।",
            ),
          ],
        },
      ],
      important: "पुष्टि से पहले पता, संपत्ति और राशि जाँचें।",
      faq: "FAQ और सहायता खोलें",
      back: "प्रोफ़ाइल पर लौटें",
    },
  },
  id: {
    privacy: {
      title: "Kebijakan Privasi",
      eyebrow: "Data dan keamanan",
      updated: "Versi berlaku",
      summary: copyText(
        "Menjelaskan data yang dibutuhkan EFHC Bot,",
        "alasan penggunaannya, serta cara meminta akses,",
        "koreksi, atau penghapusan.",
      ),
      sections: [
        {
          title: "Data yang digunakan",
          paragraphs: [
            copyText(
              "ID dan profil publik Telegram, pengaturan,",
              "alamat dompet publik tertaut, riwayat, saldo,",
              "dan catatan keamanan.",
            ),
            copyText(
              "EFHC Bot tidak meminta atau menyimpan seed",
              "phrase, kunci privat, atau kata sandi dompet.",
            ),
          ],
        },
        {
          title: "Tujuan",
          paragraphs: [
            copyText(
              "Data digunakan untuk akun, saldo, operasi,",
              "mencegah kredit ganda, perlindungan",
              "penyalahgunaan, dan dukungan.",
            ),
          ],
        },
        {
          title: "Penyimpanan dan pihak ketiga",
          paragraphs: [
            copyText(
              "Data disimpan selama diperlukan untuk layanan,",
              "integritas keuangan, keamanan, dan kewajiban",
              "yang berlaku.",
            ),
            copyText(
              "Telegram, dompet TON, blockchain, dan penyedia",
              "memiliki aturan sendiri. Catatan blockchain",
              "publik tidak dapat dihapus.",
            ),
          ],
        },
        {
          title: "Hak Anda",
          paragraphs: [
            copyText(
              "Gunakan kanal dukungan resmi di FAQ untuk",
              "meminta salinan, koreksi, atau penghapusan akun.",
            ),
            copyText(
              "Catatan untuk integritas buku besar, penipuan,",
              "sengketa, atau penyimpanan wajib dapat",
              "dipertahankan.",
            ),
          ],
        },
      ],
      important: copyText(
        "Jangan pernah membagikan seed phrase, kunci",
        "privat, kode konfirmasi, atau kata sandi.",
      ),
      faq: "Buka FAQ dan dukungan",
      back: "Kembali ke profil",
    },
    terms: {
      title: "Ketentuan Penggunaan",
      eyebrow: "Aturan layanan",
      updated: "Versi berlaku",
      summary: copyText(
        "Dengan menggunakan EFHC Bot, Anda menyetujui",
        "aturan akun, pembayaran, pencegahan",
        "penyalahgunaan, dan penggunaan wajar.",
      ),
      sections: [
        {
          title: "Tujuan",
          paragraphs: [
            copyText(
              "EFHC Bot menggabungkan pencatatan energi,",
              "mekanik permainan, fitur sosial, dan operasi",
              "EFHC. Kanon: 1 EFHC = 1 kWh.",
            ),
            copyText(
              "Tidak ada jaminan keuntungan, kenaikan harga,",
              "atau hasil investasi.",
            ),
          ],
        },
        {
          title: "Saldo dan pendanaan",
          paragraphs: [
            copyText(
              "Saldo utama dan bonus terpisah. Deposit langsung",
              "EFHC jetton mengkredit EFHC_MAIN 1:1 setelah",
              "konfirmasi.",
            ),
            copyText(
              "Pembelian Browser Shop dengan TON/GRAM atau USDT",
              "adalah alur terpisah.",
            ),
          ],
        },
        {
          title: "Pembayaran dan penarikan",
          paragraphs: [
            copyText(
              "Transaksi blockchain ditandatangani di dompet",
              "Anda dan dapat tidak dapat dibatalkan setelah",
              "dikonfirmasi.",
            ),
            copyText(
              "Penarikan membutuhkan dompet tertaut, saldo",
              "cukup, dan pemeriksaan yang berlaku.",
            ),
          ],
        },
        {
          title: "Penggunaan wajar",
          paragraphs: [
            copyText(
              "Otomatisasi abusif, hadiah ganda, bypass batas,",
              "pemalsuan data, dan gangguan akun lain dilarang.",
            ),
          ],
        },
        {
          title: "VIP NFT dan perubahan",
          paragraphs: [
            copyText(
              "EFHC VIP NFT adalah objek digital dan status",
              "terpisah, bukan janji imbal hasil.",
            ),
            "Perubahan penting diumumkan di aplikasi atau kanal resmi.",
          ],
        },
      ],
      important:
        "Periksa alamat, aset, dan jumlah sebelum konfirmasi.",
      faq: "Buka FAQ dan dukungan",
      back: "Kembali ke profil",
    },
  },
  sw: {
    privacy: {
      title: "Sera ya Faragha",
      eyebrow: "Data na usalama",
      updated: "Toleo la sasa",
      summary: copyText(
        "Inaeleza data inayohitajika na EFHC Bot, sababu",
        "ya matumizi yake na jinsi ya kuomba ufikiaji,",
        "marekebisho au kufutwa.",
      ),
      sections: [
        {
          title: "Data inayotumika",
          paragraphs: [
            copyText(
              "Kitambulisho na wasifu wa umma wa Telegram,",
              "mipangilio, anwani za pochi za umma, historia,",
              "salio na kumbukumbu za usalama.",
            ),
            copyText(
              "EFHC Bot haiombi wala kuhifadhi seed phrase,",
              "ufunguo binafsi au nenosiri la pochi.",
            ),
          ],
        },
        {
          title: "Madhumuni",
          paragraphs: [
            copyText(
              "Data hutumika kwa akaunti, salio, shughuli,",
              "kuzuia mkopo mara mbili, ulinzi dhidi ya",
              "matumizi mabaya na msaada.",
            ),
          ],
        },
        {
          title: "Uhifadhi na wahusika wengine",
          paragraphs: [
            copyText(
              "Data huhifadhiwa kwa muda unaohitajika kwa",
              "huduma, uadilifu wa fedha, usalama na masharti",
              "yanayotumika.",
            ),
            copyText(
              "Telegram, pochi za TON, blockchain na watoa",
              "huduma wana kanuni zao. Rekodi za umma za",
              "blockchain haziwezi kufutwa.",
            ),
          ],
        },
        {
          title: "Haki zako",
          paragraphs: [
            copyText(
              "Tumia njia rasmi ya msaada iliyo kwenye FAQ",
              "kuomba nakala, marekebisho au kufutwa kwa",
              "akaunti.",
            ),
            copyText(
              "Rekodi za uadilifu wa leja, udanganyifu,",
              "migogoro au uhifadhi wa lazima zinaweza kubaki.",
            ),
          ],
        },
      ],
      important: copyText(
        "Usishiriki seed phrase, ufunguo binafsi, msimbo",
        "wa uthibitisho au nenosiri.",
      ),
      faq: "Fungua FAQ na msaada",
      back: "Rudi kwenye wasifu",
    },
    terms: {
      title: "Masharti ya Matumizi",
      eyebrow: "Kanuni za huduma",
      updated: "Toleo la sasa",
      summary: copyText(
        "Kwa kutumia EFHC Bot unakubali kanuni za",
        "akaunti, malipo, kuzuia matumizi mabaya na",
        "matumizi ya haki.",
      ),
      sections: [
        {
          title: "Madhumuni",
          paragraphs: [
            copyText(
              "EFHC Bot inaunganisha uhasibu wa nishati,",
              "michezo, vipengele vya kijamii na shughuli za",
              "EFHC. Kanuni: 1 EFHC = 1 kWh.",
            ),
            copyText(
              "Hakuna ahadi ya faida, kupanda kwa bei au",
              "matokeo ya uwekezaji.",
            ),
          ],
        },
        {
          title: "Salio na kuweka fedha",
          paragraphs: [
            copyText(
              "Salio kuu na bonasi ni tofauti. Amana ya moja",
              "kwa moja ya EFHC jetton huweka EFHC_MAIN 1:1",
              "baada ya uthibitisho.",
            ),
            copyText(
              "Ununuzi wa Browser Shop kwa TON/GRAM au USDT ni",
              "mchakato tofauti.",
            ),
          ],
        },
        {
          title: "Malipo na utoaji",
          paragraphs: [
            copyText(
              "Unasaini shughuli za blockchain kwenye pochi",
              "yako na shughuli iliyothibitishwa inaweza",
              "kutorejesheka.",
            ),
            copyText(
              "Utoaji unahitaji pochi iliyounganishwa, salio la",
              "kutosha na ukaguzi husika.",
            ),
          ],
        },
        {
          title: "Matumizi ya haki",
          paragraphs: [
            copyText(
              "Otomatiki ya udanganyifu, zawadi mbili, kukwepa",
              "mipaka, data bandia na kuingilia akaunti",
              "nyingine ni marufuku.",
            ),
          ],
        },
        {
          title: "VIP NFT na mabadiliko",
          paragraphs: [
            copyText(
              "EFHC VIP NFT ni kitu cha kidijitali na hadhi",
              "tofauti, si ahadi ya mapato.",
            ),
            copyText(
              "Mabadiliko muhimu huchapishwa kwenye programu au",
              "njia rasmi.",
            ),
          ],
        },
      ],
      important:
        "Kagua anwani, mali na kiasi kabla ya kuthibitisha.",
      faq: "Fungua FAQ na msaada",
      back: "Rudi kwenye wasifu",
    },
  },
  pt: {
    privacy: {
      title: "Política de Privacidade",
      eyebrow: "Dados e segurança",
      updated: "Versão atual",
      summary: copyText(
        "Descreve os dados de que o EFHC Bot necessita, por que",
        "são utilizados e como pedir acesso, correção ou eliminação.",
      ),
      sections: [
        {
          title: "Que dados são utilizados",
          paragraphs: [
            copyText(
              "Identificador e dados públicos do Telegram, definições,",
              "endereços públicos de carteiras, histórico, saldos e",
              "registos de segurança.",
            ),
            copyText(
              "O EFHC Bot não pede nem guarda seed phrase, chave privada",
              "ou palavra-passe da carteira.",
            ),
          ],
        },
        {
          title: "Porque são necessários os dados",
          paragraphs: [
            copyText(
              "Os dados são utilizados para contas, saldos, operações,",
              "prevenção de créditos duplicados, proteção contra abusos",
              "e suporte.",
            ),
          ],
        },
        {
          title: "Armazenamento e partilha",
          paragraphs: [
            copyText(
              "Os dados são conservados durante o período necessário",
              "ao serviço, à integridade financeira, à segurança e às",
              "obrigações aplicáveis.",
            ),
            copyText(
              "Telegram, carteiras TON, blockchain e prestadores de",
              "serviços têm as suas próprias regras. Os registos públicos",
              "da blockchain não podem ser eliminados.",
            ),
          ],
        },
        {
          title: "Os seus direitos",
          paragraphs: [
            copyText(
              "Utilize o canal oficial de suporte indicado no FAQ para",
              "pedir uma cópia, correção ou eliminação da conta.",
            ),
            copyText(
              "Os registos necessários para integridade do ledger, fraude,",
              "litígios ou retenção obrigatória podem ser conservados.",
            ),
          ],
        },
      ],
      important: copyText(
        "Não partilhe com ninguém a seed phrase, chave privada, código",
        "de confirmação ou palavra-passe da carteira.",
      ),
      faq: "Abrir FAQ e suporte",
      back: "Voltar ao perfil",
    },
    terms: {
      title: "Termos de Utilização",
      eyebrow: "Regras do serviço",
      updated: "Versão atual",
      summary: copyText(
        "Ao utilizar o EFHC Bot aceita as regras de conta, pagamentos,",
        "prevenção de abusos e utilização justa.",
      ),
      sections: [
        {
          title: "Finalidade do serviço",
          paragraphs: [
            copyText(
              "O EFHC Bot combina contabilização de energia, mecânicas",
              "de jogo, funções sociais e operações EFHC. Regra:",
              "1 EFHC = 1 kWh.",
            ),
            copyText(
              "Não existe promessa de rendimento, valorização do preço",
              "ou resultado de investimento.",
            ),
          ],
        },
        {
          title: "Saldos e depósitos",
          paragraphs: [
            copyText(
              "Os saldos principal e de bónus são separados. Um depósito",
              "direto de EFHC jetton credita EFHC_MAIN 1:1 após confirmação.",
            ),
            copyText(
              "As compras no Browser Shop com TON/GRAM ou USDT são um",
              "processo separado.",
            ),
          ],
        },
        {
          title: "Pagamentos e levantamentos",
          paragraphs: [
            copyText(
              "As transações blockchain são assinadas na sua carteira e",
              "uma transação confirmada pode ser irreversível.",
            ),
            copyText(
              "O levantamento exige uma carteira associada, saldo",
              "suficiente e as verificações aplicáveis.",
            ),
          ],
        },
        {
          title: "Utilização justa",
          paragraphs: [
            copyText(
              "São proibidos automação fraudulenta, prémios duplicados,",
              "evasão de limites, dados falsos e interferência em contas",
              "de terceiros.",
            ),
          ],
        },
        {
          title: "VIP NFT e alterações",
          paragraphs: [
            copyText(
              "O EFHC VIP NFT é um item digital e um estatuto separado,",
              "não uma promessa de rendimento.",
            ),
            copyText(
              "As alterações importantes são publicadas na aplicação ou",
              "nos canais oficiais.",
            ),
          ],
        },
      ],
      important: "Verifique o endereço, o ativo e o montante antes de confirmar.",
      faq: "Abrir FAQ e suporte",
      back: "Voltar ao perfil",
    },
  },
  ko: {
    privacy: {
      title: "개인정보 처리방침",
      eyebrow: "데이터 및 보안",
      updated: "현재 버전",
      summary: copyText(
        "EFHC Bot에 필요한 데이터, 사용 목적,",
        "접근·수정·삭제 요청 방법을 설명합니다.",
      ),
      sections: [
        {
          title: "사용하는 데이터",
          paragraphs: [
            copyText(
              "Telegram 식별자와 공개 데이터, 설정, 공개 지갑 주소,",
              "기록, 잔액 및 보안 로그를 사용합니다.",
            ),
            copyText(
              "EFHC Bot은 seed phrase, 개인 키 또는",
              "지갑 비밀번호를 요청하거나 저장하지 않습니다.",
            ),
          ],
        },
        {
          title: "데이터가 필요한 이유",
          paragraphs: [
            copyText(
              "데이터는 계정, 잔액, 작업, 중복 적립 방지,",
              "악용 방지 및 지원을 위해 사용됩니다.",
            ),
          ],
        },
        {
          title: "보관 및 공유",
          paragraphs: [
            copyText(
              "데이터는 서비스 제공, 금융 무결성, 보안 및 적용되는",
              "의무에 필요한 기간 동안 보관됩니다.",
            ),
            copyText(
              "Telegram, TON 지갑, blockchain 및 서비스 제공자는",
              "각자의 규칙을 적용합니다. 공개 blockchain 기록은 삭제할 수 없습니다.",
            ),
          ],
        },
        {
          title: "사용자의 권리",
          paragraphs: [
            copyText(
              "FAQ에 안내된 공식 지원 채널을 통해 계정 데이터의",
              "사본, 수정 또는 삭제를 요청할 수 있습니다.",
            ),
            copyText(
              "ledger 무결성, 사기 방지, 분쟁 또는 의무 보관에",
              "필요한 기록은 유지될 수 있습니다.",
            ),
          ],
        },
      ],
      important: copyText(
        "seed phrase, 개인 키, 확인 코드 또는 지갑 비밀번호를",
        "다른 사람과 공유하지 마세요.",
      ),
      faq: "FAQ 및 지원 열기",
      back: "프로필로 돌아가기",
    },
    terms: {
      title: "이용약관",
      eyebrow: "서비스 규칙",
      updated: "현재 버전",
      summary: copyText(
        "EFHC Bot을 사용하면 계정, 결제, 악용 방지 및",
        "공정 이용 규칙에 동의하는 것으로 간주됩니다.",
      ),
      sections: [
        {
          title: "서비스 목적",
          paragraphs: [
            copyText(
              "EFHC Bot은 에너지 회계, 게임 메커니즘, 소셜 기능 및",
              "EFHC 작업을 결합합니다. 규칙: 1 EFHC = 1 kWh.",
            ),
            copyText(
              "수익, 가격 상승 또는 투자 결과를 보장하지 않습니다.",
            ),
          ],
        },
        {
          title: "잔액 및 입금",
          paragraphs: [
            copyText(
              "메인 잔액과 보너스 잔액은 분리됩니다. EFHC jetton 직접 입금은",
              "확인 후 EFHC_MAIN에 1:1로 적립됩니다.",
            ),
            copyText(
              "TON/GRAM 또는 USDT를 사용하는 Browser Shop 구매는",
              "별도의 절차입니다.",
            ),
          ],
        },
        {
          title: "결제 및 출금",
          paragraphs: [
            copyText(
              "blockchain 거래는 사용자의 지갑에서 서명하며",
              "확인된 거래는 되돌릴 수 없을 수 있습니다.",
            ),
            copyText(
              "출금에는 연결된 지갑, 충분한 잔액 및",
              "적용되는 검증 절차가 필요합니다.",
            ),
          ],
        },
        {
          title: "공정 이용",
          paragraphs: [
            copyText(
              "사기성 자동화, 중복 보상, 제한 우회, 허위 데이터 및",
              "타인 계정에 대한 간섭은 금지됩니다.",
            ),
          ],
        },
        {
          title: "VIP NFT 및 변경",
          paragraphs: [
            copyText(
              "EFHC VIP NFT는 별도의 디지털 아이템과 상태이며",
              "수익을 보장하는 상품이 아닙니다.",
            ),
            copyText(
              "중요한 변경 사항은 앱 또는 공식 채널에 게시됩니다.",
            ),
          ],
        },
      ],
      important: "확인 전에 주소, 자산 및 금액을 확인하세요.",
      faq: "FAQ 및 지원 열기",
      back: "프로필로 돌아가기",
    },
  },
  ja: {
    privacy: {
      title: "プライバシーポリシー",
      eyebrow: "データとセキュリティ",
      updated: "現在のバージョン",
      summary: copyText(
        "EFHC Botが必要とするデータ、その利用目的、",
        "アクセス・訂正・削除を依頼する方法を説明します。",
      ),
      sections: [
        {
          title: "利用するデータ",
          paragraphs: [
            copyText(
              "Telegramの識別子と公開データ、設定、公開ウォレットアドレス、",
              "履歴、残高、セキュリティログを利用します。",
            ),
            copyText(
              "EFHC Botはseed phrase、秘密鍵、",
              "ウォレットのパスワードを要求または保存しません。",
            ),
          ],
        },
        {
          title: "データが必要な理由",
          paragraphs: [
            copyText(
              "データはアカウント、残高、操作、重複付与の防止、",
              "不正利用の防止、サポートのために使用されます。",
            ),
          ],
        },
        {
          title: "保存と共有",
          paragraphs: [
            copyText(
              "データはサービス提供、金融上の整合性、セキュリティ、",
              "適用される義務に必要な期間保存されます。",
            ),
            copyText(
              "Telegram、TONウォレット、blockchain、サービス提供者には",
              "それぞれの規則があります。公開blockchain記録は削除できません。",
            ),
          ],
        },
        {
          title: "利用者の権利",
          paragraphs: [
            copyText(
              "FAQに記載された公式サポート窓口から、アカウントデータの",
              "写し、訂正、削除を依頼できます。",
            ),
            copyText(
              "ledgerの整合性、不正防止、紛争、法令上の保存に",
              "必要な記録は保持される場合があります。",
            ),
          ],
        },
      ],
      important: copyText(
        "seed phrase、秘密鍵、確認コード、ウォレットのパスワードを",
        "他人と共有しないでください。",
      ),
      faq: "FAQとサポートを開く",
      back: "プロフィールに戻る",
    },
    terms: {
      title: "利用規約",
      eyebrow: "サービスのルール",
      updated: "現在のバージョン",
      summary: copyText(
        "EFHC Botを利用することで、アカウント、支払い、不正利用防止、",
        "公正利用に関するルールに同意したものとみなされます。",
      ),
      sections: [
        {
          title: "サービスの目的",
          paragraphs: [
            copyText(
              "EFHC Botはエネルギー会計、ゲームメカニズム、ソーシャル機能、",
              "EFHC操作を組み合わせます。ルール: 1 EFHC = 1 kWh。",
            ),
            copyText(
              "収益、価格上昇、投資結果を保証するものではありません。",
            ),
          ],
        },
        {
          title: "残高と入金",
          paragraphs: [
            copyText(
              "メイン残高とボーナス残高は分離されています。EFHC jettonの直接入金は、",
              "確認後にEFHC_MAINへ1:1で反映されます。",
            ),
            copyText(
              "TON/GRAMまたはUSDTを使用するBrowser Shopでの購入は、",
              "別の処理です。",
            ),
          ],
        },
        {
          title: "支払いと出金",
          paragraphs: [
            copyText(
              "blockchain取引は利用者のウォレットで署名され、",
              "確認済みの取引は取り消せない場合があります。",
            ),
            copyText(
              "出金には、紐付け済みウォレット、十分な残高、",
              "適用される検証が必要です。",
            ),
          ],
        },
        {
          title: "公正利用",
          paragraphs: [
            copyText(
              "不正な自動化、報酬の重複取得、制限回避、虚偽データ、",
              "第三者アカウントへの干渉は禁止されています。",
            ),
          ],
        },
        {
          title: "VIP NFTと変更",
          paragraphs: [
            copyText(
              "EFHC VIP NFTは独立したデジタルアイテムおよびステータスであり、",
              "収益を保証するものではありません。",
            ),
            copyText(
              "重要な変更はアプリまたは公式チャンネルで公開されます。",
            ),
          ],
        },
      ],
      important: "確認する前に、アドレス、資産、金額を確認してください。",
      faq: "FAQとサポートを開く",
      back: "プロフィールに戻る",
    },
  },

};

export function getLegalPolicy(
  kind: LegalPolicyKind,
  lang: Lang,
): LegalPolicy {
  const localized = COPY[lang] || COPY.en!;
  return {
    ...localized[kind],
    ...getLegalPolicyMeta(lang),
  };
}

export const LEGAL_POLICY_LANGS = Object.freeze(
  Object.keys(COPY).sort(),
);
