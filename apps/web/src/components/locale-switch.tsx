"use client";

/**
 * Language chooser (Phase 9, item 6).
 *
 * A native `<select>`, not a custom dropdown. It is keyboard-operable, announced correctly by
 * every screen reader, and on a phone it opens the platform picker — three things a hand-rolled
 * menu has to re-implement and usually gets partly wrong.
 *
 * Each language is named **in that language**. "Urdu" is only useful to somebody who already
 * reads English; "اردو" is useful to the person looking for it.
 */

import { Languages } from "lucide-react";
import { LOCALE_NAMES, LOCALES, useI18n, type Locale } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export function LocaleSwitch({ className }: { className?: string }) {
  const { locale, setLocale } = useI18n();

  return (
    <label className={cn("inline-flex items-center gap-1.5 text-xs text-ink-2", className)}>
      <Languages className="h-3.5 w-3.5" aria-hidden="true" />
      <span className="sr-only">Language</span>
      <select
        value={locale}
        onChange={(e) => setLocale(e.target.value as Locale)}
        className="rounded-md border border-line bg-surface-1 px-2 py-1 text-xs text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        {LOCALES.map((l) => (
          <option key={l} value={l} lang={l}>
            {LOCALE_NAMES[l]}
          </option>
        ))}
      </select>
    </label>
  );
}
