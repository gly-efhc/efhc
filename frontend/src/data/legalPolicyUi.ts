import type { Lang } from "../lib/i18n";
import type { LegalPolicyMeta } from "./legalPolicies";

type Copy = Omit<LegalPolicyMeta, "version" | "effectiveDate">;

function text(...parts: string[]): string {
  return parts.join(" ");
}

const COPY: Partial<Record<Lang, Copy>> = {
  ru: {
    versionLabel: "Версия",
    effectiveLabel: "Действует с",
    changesLabel: "Что изменилось",
    sectionIndexLabel: "Разделы",
    warningLabel: "Защита кошелька",
    supportLabel: "Поддержка",
    changes: [
      text(
        "Добавлены понятные сведения о безопасности",
        "и данных.",
      ),
      text(
        "Уточнены правила платежей, вывода и защиты",
        "от злоупотреблений.",
      ),
    ],
  },
  en: {
    versionLabel: "Version",
    effectiveLabel: "Effective",
    changesLabel: "What changed",
    sectionIndexLabel: "Sections",
    warningLabel: "Wallet safety",
    supportLabel: "Support",
    changes: [
      "Clearer data and wallet-safety information was added.",
      "Payment, withdrawal, and abuse rules were clarified.",
    ],
  },
  uk: {
    versionLabel: "Версія",
    effectiveLabel: "Чинна з",
    changesLabel: "Що змінилося",
    sectionIndexLabel: "Розділи",
    warningLabel: "Безпека гаманця",
    supportLabel: "Підтримка",
    changes: [
      "Додано зрозумілі відомості про безпеку та дані.",
      text(
        "Уточнено правила платежів, виведення і захисту",
        "від зловживань.",
      ),
    ],
  },
  de: {
    versionLabel: "Version",
    effectiveLabel: "Gültig ab",
    changesLabel: "Änderungen",
    sectionIndexLabel: "Abschnitte",
    warningLabel: "Wallet-Sicherheit",
    supportLabel: "Support",
    changes: [
      text(
        "Hinweise zu Daten und Wallet-Sicherheit wurden",
        "ergänzt.",
      ),
      text(
        "Zahlungs-, Auszahlungs- und Missbrauchsregeln",
        "wurden präzisiert.",
      ),
    ],
  },
  fr: {
    versionLabel: "Version",
    effectiveLabel: "En vigueur",
    changesLabel: "Modifications",
    sectionIndexLabel: "Sections",
    warningLabel: "Sécurité du portefeuille",
    supportLabel: "Assistance",
    changes: [
      text(
        "Les informations sur les données et la sécurité",
        "ont été clarifiées.",
      ),
      text(
        "Les règles de paiement, retrait et abus ont été",
        "précisées.",
      ),
    ],
  },
  es: {
    versionLabel: "Versión",
    effectiveLabel: "Vigente desde",
    changesLabel: "Cambios",
    sectionIndexLabel: "Secciones",
    warningLabel: "Seguridad de la cartera",
    supportLabel: "Soporte",
    changes: [
      text(
        "Se aclaró la información sobre datos y seguridad",
        "de la cartera.",
      ),
      "Se precisaron las reglas de pagos, retiros y abuso.",
    ],
  },
  it: {
    versionLabel: "Versione",
    effectiveLabel: "In vigore",
    changesLabel: "Modifiche",
    sectionIndexLabel: "Sezioni",
    warningLabel: "Sicurezza wallet",
    supportLabel: "Assistenza",
    changes: [
      "Chiarite le informazioni su dati e sicurezza.",
      "Precisate le regole per pagamenti, prelievi e abusi.",
    ],
  },
  tr: {
    versionLabel: "Sürüm",
    effectiveLabel: "Yürürlük",
    changesLabel: "Değişiklikler",
    sectionIndexLabel: "Bölümler",
    warningLabel: "Cüzdan güvenliği",
    supportLabel: "Destek",
    changes: [
      "Veri ve cüzdan güvenliği bilgileri netleştirildi.",
      "Ödeme, çekim ve kötüye kullanım kuralları açıklandı.",
    ],
  },
  pl: {
    versionLabel: "Wersja",
    effectiveLabel: "Obowiązuje od",
    changesLabel: "Zmiany",
    sectionIndexLabel: "Sekcje",
    warningLabel: "Bezpieczeństwo portfela",
    supportLabel: "Pomoc",
    changes: [
      text(
        "Doprecyzowano informacje o danych i bezpieczeństwie",
        "portfela.",
      ),
      "Wyjaśniono zasady płatności, wypłat i nadużyć.",
    ],
  },
  da: {
    versionLabel: "Version",
    effectiveLabel: "Gælder fra",
    changesLabel: "Ændringer",
    sectionIndexLabel: "Afsnit",
    warningLabel: "Wallet-sikkerhed",
    supportLabel: "Support",
    changes: [
      text(
        "Oplysninger om data og wallet-sikkerhed er",
        "tydeliggjort.",
      ),
      text(
        "Regler for betaling, udbetaling og misbrug er",
        "præciseret.",
      ),
    ],
  },
  hi: {
    versionLabel: "संस्करण",
    effectiveLabel: "लागू तिथि",
    changesLabel: "क्या बदला",
    sectionIndexLabel: "अनुभाग",
    warningLabel: "वॉलेट सुरक्षा",
    supportLabel: "सहायता",
    changes: [
      "डेटा और वॉलेट सुरक्षा की जानकारी स्पष्ट की गई।",
      "भुगतान, निकासी और दुरुपयोग के नियम स्पष्ट किए गए।",
    ],
  },
  id: {
    versionLabel: "Versi",
    effectiveLabel: "Berlaku",
    changesLabel: "Perubahan",
    sectionIndexLabel: "Bagian",
    warningLabel: "Keamanan dompet",
    supportLabel: "Dukungan",
    changes: [
      "Informasi data dan keamanan dompet diperjelas.",
      text(
        "Aturan pembayaran, penarikan, dan penyalahgunaan",
        "diperinci.",
      ),
    ],
  },
  sw: {
    versionLabel: "Toleo",
    effectiveLabel: "Linaanza",
    changesLabel: "Kilichobadilika",
    sectionIndexLabel: "Sehemu",
    warningLabel: "Usalama wa pochi",
    supportLabel: "Msaada",
    changes: [
      "Taarifa za data na usalama wa pochi zimefafanuliwa.",
      "Kanuni za malipo, utoaji na matumizi mabaya zimeelezwa.",
    ],
  },
  pt: {
    versionLabel: "Versão",
    effectiveLabel: "Em vigor desde",
    changesLabel: "O que mudou",
    sectionIndexLabel: "Secções",
    warningLabel: "Segurança da carteira",
    supportLabel: "Suporte",
    changes: [
      "Foram clarificadas as informações sobre dados e segurança da carteira.",
      "Foram clarificadas as regras de pagamentos, levantamentos e prevenção de abusos.",
    ],
  },
  ko: {
    versionLabel: "버전",
    effectiveLabel: "시행일",
    changesLabel: "변경 사항",
    sectionIndexLabel: "섹션",
    warningLabel: "지갑 보안",
    supportLabel: "지원",
    changes: [
      "데이터 및 지갑 보안에 관한 설명을 명확히 했습니다.",
      "결제, 출금 및 악용 방지 규칙을 명확히 했습니다.",
    ],
  },
  ja: {
    versionLabel: "バージョン",
    effectiveLabel: "発効日",
    changesLabel: "変更内容",
    sectionIndexLabel: "セクション",
    warningLabel: "ウォレットのセキュリティ",
    supportLabel: "サポート",
    changes: [
      "データとウォレットのセキュリティに関する説明を明確化しました。",
      "支払い、出金、不正利用防止のルールを明確化しました。",
    ],
  },

};

export function getLegalPolicyMeta(lang: Lang): LegalPolicyMeta {
  return {
    ...(COPY[lang] || COPY.en!),
    version: "1.0",
    effectiveDate: "2026-07-21",
  };
}
