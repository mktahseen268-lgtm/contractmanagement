"use client";

/**
 * Localization (Phase 9, item 6) — English and Urdu.
 *
 * Three things this owns, and one it deliberately does not.
 *
 * **Owns:** the interface strings, the reading direction, and locale-aware formatting of dates,
 * numbers and money. Urdu is right-to-left, so choosing it flips `dir` on the document — a
 * translated interface that still reads left-to-right is harder to use than an English one,
 * because every eye movement is backwards.
 *
 * **Does not own:** the wording of legal guidance. Help topics, knowledge-base articles and
 * course content are per-locale rows in the database, edited in the product. That is not a gap —
 * the RFP asks for terminology aligned to MMBL's internal policy language, which only MMBL's
 * legal team can supply. Machine-translating legal guidance and shipping it as authoritative
 * would be worse than showing the English and saying so, which is what the untranslated badge
 * in the help panel does.
 *
 * Missing key behaviour: falls back to English, then to the key itself. Never blank. A missing
 * translation should look unfinished, not like an empty button.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export const LOCALES = ["en", "ur"] as const;
export type Locale = (typeof LOCALES)[number];

export const LOCALE_NAMES: Record<Locale, string> = {
  en: "English",
  ur: "اردو",
};

/** Urdu is right-to-left. */
export const RTL_LOCALES: Locale[] = ["ur"];

const STORAGE_KEY = "cm.locale";

/**
 * Interface strings. Keys are dotted paths that describe *where* the string is, not what it
 * says — renaming a key because the copy changed is how translations get orphaned.
 */
const STRINGS: Record<Locale, Record<string, string>> = {
  en: {
    "nav.home": "Home",
    "nav.contracts": "Contracts",
    "nav.inbox": "Inbox",
    "nav.knowledge": "Help centre",
    "nav.training": "Training",
    "nav.settings": "Settings",

    "action.save": "Save",
    "action.cancel": "Cancel",
    "action.close": "Close",
    "action.back": "Back",
    "action.next": "Next",
    "action.continue": "Continue",
    "action.retry": "Try again",
    "action.print": "Print",
    "action.download": "Download",
    "action.search": "Search",

    "state.loading": "Loading…",
    "state.empty": "Nothing here yet",
    "state.error": "Something went wrong",

    "sign.title": "Sign this agreement",
    "sign.review": "Read the agreement",
    "sign.identity": "Confirm who you are",
    "sign.sign": "Sign",
    "sign.done": "Done",
    "sign.step": "Step {n} of {total}",
    "sign.agree": "I have read this agreement and I agree to it",
    "sign.your_name": "Your full name",
    "sign.otp_sent": "We sent a code to your phone",
    "sign.otp_enter": "Enter the code",
    "sign.assisted": "Larger text and one step at a time",
    "sign.help": "Ask the branch staff member to explain anything you are unsure about. Do not sign until you are.",
    "sign.copy_sent": "A copy has been sent to you.",
    "sign.no_email": "If you have no email, ask for a printed copy before you leave.",

    "training.hub": "Training",
    "training.required": "Required",
    "training.certificate": "Certificate",
    "training.valid_until": "Valid until",
    "training.expired": "Expired — retake to renew",
    "training.start": "Start",
    "training.resume": "Continue",
    "training.retake": "Retake",
    "training.pass_mark": "Pass mark",
    "training.score": "Score",

    "help.title": "About this field",
    "help.untranslated": "Shown in English — not yet translated",
  },
  ur: {
    "nav.home": "ہوم",
    "nav.contracts": "معاہدے",
    "nav.inbox": "ان باکس",
    "nav.knowledge": "مدد کا مرکز",
    "nav.training": "تربیت",
    "nav.settings": "ترتیبات",

    "action.save": "محفوظ کریں",
    "action.cancel": "منسوخ کریں",
    "action.close": "بند کریں",
    "action.back": "واپس",
    "action.next": "آگے",
    "action.continue": "جاری رکھیں",
    "action.retry": "دوبارہ کوشش کریں",
    "action.print": "پرنٹ کریں",
    "action.download": "ڈاؤن لوڈ کریں",
    "action.search": "تلاش کریں",

    "state.loading": "لوڈ ہو رہا ہے…",
    "state.empty": "ابھی کچھ نہیں",
    "state.error": "کچھ غلط ہو گیا",

    "sign.title": "اس معاہدے پر دستخط کریں",
    "sign.review": "معاہدہ پڑھیں",
    "sign.identity": "اپنی شناخت کی تصدیق کریں",
    "sign.sign": "دستخط کریں",
    "sign.done": "مکمل",
    "sign.step": "مرحلہ {n} از {total}",
    "sign.agree": "میں نے یہ معاہدہ پڑھ لیا ہے اور مجھے منظور ہے",
    "sign.your_name": "آپ کا پورا نام",
    "sign.otp_sent": "ہم نے آپ کے فون پر کوڈ بھیجا ہے",
    "sign.otp_enter": "کوڈ درج کریں",
    "sign.assisted": "بڑا متن اور ایک وقت میں ایک مرحلہ",
    "sign.help": "جو بات سمجھ نہ آئے، برانچ کے عملے سے پوچھیں۔ جب تک اطمینان نہ ہو، دستخط نہ کریں۔",
    "sign.copy_sent": "آپ کو ایک نقل بھیج دی گئی ہے۔",
    "sign.no_email": "اگر آپ کے پاس ای میل نہیں ہے تو جانے سے پہلے پرنٹ شدہ نقل طلب کریں۔",

    "training.hub": "تربیت",
    "training.required": "لازمی",
    "training.certificate": "سرٹیفکیٹ",
    "training.valid_until": "اس تاریخ تک کارآمد",
    "training.expired": "میعاد ختم — تجدید کے لیے دوبارہ کریں",
    "training.start": "شروع کریں",
    "training.resume": "جاری رکھیں",
    "training.retake": "دوبارہ کریں",
    "training.pass_mark": "کامیابی کا معیار",
    "training.score": "نمبر",

    "help.title": "اس خانے کے بارے میں",
    "help.untranslated": "انگریزی میں دکھایا جا رہا ہے — ابھی ترجمہ نہیں ہوا",
  },
};

/** BCP-47 tags for `Intl`. Urdu as spoken in Pakistan, which is the deployment. */
const INTL_LOCALE: Record<Locale, string> = { en: "en-GB", ur: "ur-PK" };

export function isRtl(locale: Locale): boolean {
  return RTL_LOCALES.includes(locale);
}

function normalise(value: string | null | undefined): Locale {
  const base = (value || "").toLowerCase().split("-")[0];
  return (LOCALES as readonly string[]).includes(base) ? (base as Locale) : "en";
}

type I18nValue = {
  locale: Locale;
  dir: "ltr" | "rtl";
  setLocale: (l: Locale) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
  formatDate: (value: string | Date | null | undefined) => string;
  formatDateTime: (value: string | Date | null | undefined) => string;
  formatNumber: (value: number) => string;
  formatMoney: (value: number, currency?: string) => string;
};

const I18nContext = createContext<I18nValue | null>(null);

export function I18nProvider({
  children,
  initial,
}: {
  children: ReactNode;
  initial?: Locale;
}) {
  const [locale, setLocaleState] = useState<Locale>(initial || "en");

  // Read the stored choice after mount, not during render: the server has no localStorage, and
  // reading it during render produces markup that does not match what the server sent.
  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored) setLocaleState(normalise(stored));
    } catch {
      // Private mode, or storage disabled. English is a working default, not an error.
    }
  }, []);

  // The whole document flips, not just the components that opted in. A page with an RTL panel
  // inside an LTR shell is harder to read than either done consistently.
  useEffect(() => {
    if (typeof document === "undefined") return;
    document.documentElement.lang = locale;
    document.documentElement.dir = isRtl(locale) ? "rtl" : "ltr";
  }, [locale]);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Not persisting the choice is a smaller failure than refusing to change language.
    }
  }, []);

  const value = useMemo<I18nValue>(() => {
    const tag = INTL_LOCALE[locale];

    const t = (key: string, vars?: Record<string, string | number>) => {
      // English, then the key itself. Never blank — a missing translation should look
      // unfinished rather than like an empty button.
      const raw = STRINGS[locale]?.[key] ?? STRINGS.en[key] ?? key;
      if (!vars) return raw;
      return raw.replace(/\{(\w+)\}/g, (_m, name) =>
        name in vars ? String(vars[name]) : `{${name}}`,
      );
    };

    const toDate = (value: string | Date | null | undefined) => {
      if (!value) return null;
      const d = value instanceof Date ? value : new Date(value);
      return isNaN(d.getTime()) ? null : d;
    };

    return {
      locale,
      dir: isRtl(locale) ? "rtl" : "ltr",
      setLocale,
      t,
      formatDate: (value) => {
        const d = toDate(value);
        return d
          ? d.toLocaleDateString(tag, { year: "numeric", month: "short", day: "numeric" })
          : "—";
      },
      formatDateTime: (value) => {
        const d = toDate(value);
        return d
          ? d.toLocaleString(tag, {
              year: "numeric",
              month: "short",
              day: "numeric",
              hour: "2-digit",
              minute: "2-digit",
            })
          : "—";
      },
      formatNumber: (value) => new Intl.NumberFormat(tag).format(value),
      formatMoney: (value, currency = "PKR") => {
        try {
          return new Intl.NumberFormat(tag, {
            style: "currency",
            currency,
            maximumFractionDigits: 0,
          }).format(value);
        } catch {
          // An unknown currency code must not blank the figure — the number is the part that
          // matters, and a missing amount reads as zero.
          return `${currency} ${new Intl.NumberFormat(tag).format(value)}`;
        }
      },
    };
  }, [locale, setLocale]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

/**
 * Apply the workspace's configured locale as the starting point.
 *
 * Only when the person has not chosen for themselves. A tenant default that overrode an
 * explicit choice would silently switch somebody's language back on every page load, which is
 * worse than not having a default at all.
 */
export function useLocaleDefault(tenantLocale: string | null | undefined) {
  const { setLocale } = useI18n();
  useEffect(() => {
    if (!tenantLocale) return;
    try {
      if (window.localStorage.getItem(STORAGE_KEY)) return;   // their choice wins
    } catch {
      // Storage unavailable: fall through and use the workspace default.
    }
    setLocale(normalise(tenantLocale));
  }, [tenantLocale, setLocale]);
}


export function useI18n(): I18nValue {
  const ctx = useContext(I18nContext);
  if (ctx) return ctx;
  // Usable outside the provider — the public signing portal renders before any app chrome, and
  // a hook that throws there would take the page down over a language preference.
  const tag = INTL_LOCALE.en;
  return {
    locale: "en",
    dir: "ltr",
    setLocale: () => {},
    t: (key, vars) => {
      const raw = STRINGS.en[key] ?? key;
      return vars
        ? raw.replace(/\{(\w+)\}/g, (_m, n) => (n in vars ? String(vars[n]) : `{${n}}`))
        : raw;
    },
    formatDate: (v) => (v ? new Date(v).toLocaleDateString(tag) : "—"),
    formatDateTime: (v) => (v ? new Date(v).toLocaleString(tag) : "—"),
    formatNumber: (v) => new Intl.NumberFormat(tag).format(v),
    formatMoney: (v, currency = "PKR") => `${currency} ${new Intl.NumberFormat(tag).format(v)}`,
  };
}
