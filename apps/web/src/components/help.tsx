"use client";

/**
 * Contextual help (Phase 9, item 1).
 *
 *   GET /help?surface=…   — every topic for a screen, in one request
 *
 * One fetch per screen, cached in a module-level map. A tooltip that arrives after the user has
 * moved on is not help, and a request per field would be dozens per page.
 *
 * Accessibility is the substance here, not a coat of paint. The trigger is a real `<button>`
 * with an accessible name, the panel is linked to it by `aria-describedby`, Escape closes it,
 * and it opens on focus as well as hover — help you can only reach with a mouse is help a
 * keyboard user does not have.
 */

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { HelpCircle } from "lucide-react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export type HelpTopic = {
  key: string;
  title: string;
  body: string;
  surface: string;
  locale: string;
  is_translated: boolean;
};

type Cache = Record<string, Record<string, HelpTopic>>;

/** Keyed by `${locale}:${surface}`. Cleared on reload; help copy does not change mid-session. */
const cache: Cache = {};
const inflight: Record<string, Promise<Record<string, HelpTopic>>> = {};

async function loadSurface(locale: string, surface: string) {
  const cacheKey = `${locale}:${surface}`;
  if (cache[cacheKey]) return cache[cacheKey];
  // De-duped: a form with fifteen help icons mounts fifteen components at once, and without
  // this that is fifteen identical requests.
  if (!inflight[cacheKey]) {
    const query = surface ? `?surface=${encodeURIComponent(surface)}` : "";
    inflight[cacheKey] = api
      .get<Record<string, HelpTopic>>(`/help${query}`)
      .then((data) => {
        cache[cacheKey] = data;
        return data;
      })
      .catch(() => ({}) as Record<string, HelpTopic>)
      .finally(() => {
        delete inflight[cacheKey];
      });
  }
  return inflight[cacheKey];
}

export function useHelp(surface = "") {
  const { locale } = useI18n();
  const [topics, setTopics] = useState<Record<string, HelpTopic>>(
    () => cache[`${locale}:${surface}`] || {},
  );

  useEffect(() => {
    let alive = true;
    void loadSurface(locale, surface).then((data) => {
      if (alive) setTopics(data);
    });
    return () => {
      alive = false;
    };
  }, [locale, surface]);

  return topics;
}

/**
 * The `?` next to a field label.
 *
 * Renders **nothing** when there is no topic for the key. An empty tooltip is worse than no
 * icon: it advertises help and then does not give any.
 */
export function HelpTip({
  topicKey,
  surface = "",
  className,
}: {
  topicKey: string;
  surface?: string;
  className?: string;
}) {
  const topics = useHelp(surface);
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const wrapRef = useRef<HTMLSpanElement>(null);

  const topic = topics[topicKey];

  const close = useCallback(() => setOpen(false), []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        close();
      }
    };
    const onClickAway = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) close();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClickAway);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClickAway);
    };
  }, [open, close]);

  if (!topic) return null;

  return (
    <span ref={wrapRef} className={cn("relative inline-flex", className)}>
      <button
        type="button"
        // Named, not just an icon. A screen reader announcing "button" tells nobody anything.
        aria-label={`${t("help.title")}: ${topic.title || topicKey}`}
        aria-expanded={open}
        aria-describedby={open ? panelId : undefined}
        onClick={() => setOpen((v) => !v)}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        className="rounded-full text-ink-3 transition-colors hover:text-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        <HelpCircle className="h-3.5 w-3.5" aria-hidden="true" />
      </button>

      {open && (
        <span
          id={panelId}
          role="tooltip"
          className="absolute start-0 top-6 z-50 w-72 rounded-lg border border-line bg-surface-1 p-3 text-start shadow-lg"
        >
          {topic.title && (
            <span className="mb-1 block text-xs font-semibold text-ink">{topic.title}</span>
          )}
          <span className="block text-xs leading-relaxed text-ink-2">{topic.body}</span>
          {!topic.is_translated && (
            <span className="mt-1.5 block text-[11px] text-ink-3">{t("help.untranslated")}</span>
          )}
        </span>
      )}
    </span>
  );
}

/**
 * A label with its help icon — the common pairing, so screens do not each re-assemble it.
 */
export function LabelWithHelp({
  children,
  topicKey,
  surface = "",
  htmlFor,
}: {
  children: React.ReactNode;
  topicKey: string;
  surface?: string;
  htmlFor?: string;
}) {
  return (
    <span className="inline-flex items-center gap-1">
      <label htmlFor={htmlFor} className="text-xs font-medium text-ink-2">
        {children}
      </label>
      <HelpTip topicKey={topicKey} surface={surface} />
    </span>
  );
}
