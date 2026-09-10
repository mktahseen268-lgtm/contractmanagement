"use client";

/**
 * Help centre — the in-product knowledge base (Phase 9, item 2).
 *
 *   GET /knowledge?category=&q=
 *   GET /knowledge/{slug}
 *
 * Articles are markdown in the database, seeded with real guides on first start and editable in
 * place. Video is served from this deployment's own storage — embedding YouTube would be less
 * work and would tell a third party who read which internal playbook, and when.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  BookOpen,
  FileQuestion,
  Rocket,
  ScrollText,
  Search,
  Sparkles,
} from "lucide-react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { PageHeader } from "@/components/shell";
import { Badge, Button, Card, CardBody, Input, Skeleton } from "@/components/ui";

type Article = {
  id: string;
  slug: string;
  locale: string;
  title: string;
  summary: string;
  category: string;
  tags: string[];
  video_file_id: string | null;
  video_duration_s: number;
  view_count: number;
  updated_at: string;
};

type ArticleDetail = Article & { body: string };

type Index = { categories: { category: string; count: number }[]; articles: Article[] };

const CATEGORY_META: Record<string, { label: string; icon: typeof BookOpen; blurb: string }> = {
  quickstart: {
    label: "Quick starts",
    icon: Rocket,
    blurb: "Step-by-step, from nothing to done",
  },
  playbook: {
    label: "Playbooks",
    icon: ScrollText,
    blurb: "How the bank handles a situation",
  },
  faq: { label: "Questions", icon: FileQuestion, blurb: "Short answers to common ones" },
  release_note: { label: "What's new", icon: Sparkles, blurb: "Changes, most recent first" },
};

/**
 * A deliberately small markdown renderer: headings, bold, lists, paragraphs.
 *
 * Not a library, and not `dangerouslySetInnerHTML`. Article bodies are written by people with
 * `content.manage`, which is not the same as trusting the string — an editor account is exactly
 * what an attacker would want for stored XSS. Rendering to React elements means the text can
 * never become markup.
 */
function Markdown({ source }: { source: string }) {
  const blocks = useMemo(() => source.split(/\n{2,}/), [source]);

  const inline = (text: string, keyPrefix: string) =>
    text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
      part.startsWith("**") && part.endsWith("**") ? (
        <strong key={`${keyPrefix}-${i}`} className="font-semibold text-ink">
          {part.slice(2, -2)}
        </strong>
      ) : (
        <span key={`${keyPrefix}-${i}`}>{part}</span>
      ),
    );

  return (
    <div className="space-y-3 text-sm leading-relaxed text-ink-2">
      {blocks.map((block, bi) => {
        const trimmed = block.trim();
        if (!trimmed) return null;

        if (trimmed.startsWith("## ")) {
          return (
            <h2 key={bi} className="pt-2 text-base font-semibold text-ink">
              {trimmed.slice(3)}
            </h2>
          );
        }
        if (trimmed.startsWith("# ")) {
          return (
            <h2 key={bi} className="pt-2 text-lg font-semibold text-ink">
              {trimmed.slice(2)}
            </h2>
          );
        }
        if (/^[-*] /m.test(trimmed) && trimmed.split("\n").every((l) => /^[-*] /.test(l.trim()))) {
          return (
            <ul key={bi} className="list-disc space-y-1 ps-5">
              {trimmed.split("\n").map((line, li) => (
                <li key={li}>{inline(line.trim().replace(/^[-*] /, ""), `${bi}-${li}`)}</li>
              ))}
            </ul>
          );
        }
        return <p key={bi}>{inline(trimmed, String(bi))}</p>;
      })}
    </div>
  );
}

export default function KnowledgePage() {
  const { locale } = useI18n();
  const [index, setIndex] = useState<Index | null>(null);
  const [category, setCategory] = useState("");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<ArticleDetail | null>(null);
  const [loadingArticle, setLoadingArticle] = useState(false);

  const load = useCallback(() => {
    const params = new URLSearchParams();
    if (category) params.set("category", category);
    if (query.trim()) params.set("q", query.trim());
    params.set("locale", locale);
    api
      .get<Index>(`/knowledge?${params}`)
      .then(setIndex)
      .catch(() => setIndex({ categories: [], articles: [] }));
  }, [category, query, locale]);

  useEffect(() => {
    const timer = window.setTimeout(load, query ? 250 : 0);
    return () => window.clearTimeout(timer);
  }, [load, query]);

  async function openArticle(slug: string) {
    setLoadingArticle(true);
    try {
      setOpen(await api.get<ArticleDetail>(`/knowledge/${slug}?locale=${locale}`));
      window.scrollTo({ top: 0 });
    } catch {
      setOpen(null);
    } finally {
      setLoadingArticle(false);
    }
  }

  if (open) {
    return (
      <div>
        <PageHeader
          title={open.title}
          subtitle={open.summary}
          actions={
            <Button size="sm" variant="ghost" onClick={() => setOpen(null)}>
              <ArrowLeft className="h-3.5 w-3.5 rtl:rotate-180" aria-hidden="true" /> Back to the
              help centre
            </Button>
          }
        />
        <div className="p-6">
          <Card>
            <CardBody className="max-w-3xl">
              {open.video_file_id && (
                <video
                  controls
                  preload="metadata"
                  className="mb-4 w-full rounded-lg border border-line"
                  src={`/api/files/${open.video_file_id}/content`}
                >
                  {/* Stated rather than assumed: a video with no captions is inaccessible to a
                      deaf viewer, and the honest thing is to say so and give them the text. */}
                  Your browser cannot play this video. The written guide below covers the same
                  ground.
                </video>
              )}
              <Markdown source={open.body} />
            </CardBody>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="Help centre"
        subtitle="Quick starts, playbooks and answers — written for this bank, not for software in general"
      />

      <div className="space-y-4 p-6">
        <Card>
          <CardBody>
            <label htmlFor="kb-search" className="mb-1 block text-xs font-medium text-ink-2">
              Search the help centre
            </label>
            <div className="relative">
              <Search
                className="pointer-events-none absolute start-2.5 top-2.5 h-4 w-4 text-ink-3"
                aria-hidden="true"
              />
              <Input
                id="kb-search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="notice period, sanctions, signing…"
                className="ps-8"
              />
            </div>
          </CardBody>
        </Card>

        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant={category === "" ? "primary" : "ghost"}
            onClick={() => setCategory("")}
            aria-pressed={category === ""}
          >
            Everything
          </Button>
          {(index?.categories ?? []).map((c) => {
            const meta = CATEGORY_META[c.category];
            if (!meta) return null;
            const Icon = meta.icon;
            return (
              <Button
                key={c.category}
                size="sm"
                variant={category === c.category ? "primary" : "ghost"}
                onClick={() => setCategory(c.category)}
                aria-pressed={category === c.category}
              >
                <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                {meta.label}
                <span className="text-[11px] opacity-70">{c.count}</span>
              </Button>
            );
          })}
        </div>

        {index === null || loadingArticle ? (
          <Skeleton className="h-40" />
        ) : index.articles.length === 0 ? (
          <Card>
            <CardBody className="py-10 text-center text-sm text-ink-2">
              <BookOpen className="mx-auto mb-3 h-9 w-9 text-ink-3" aria-hidden="true" />
              <div className="text-base font-semibold text-ink">Nothing matches</div>
              <p className="mt-1">
                {query
                  ? "Try a different word, or clear the search."
                  : "No articles in this section yet."}
              </p>
            </CardBody>
          </Card>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2">
            {index.articles.map((a) => {
              const meta = CATEGORY_META[a.category];
              const Icon = meta?.icon ?? BookOpen;
              return (
                <li key={a.id}>
                  <button
                    type="button"
                    onClick={() => openArticle(a.slug)}
                    className="h-full w-full rounded-xl border border-line bg-surface-1 p-4 text-start transition-colors hover:border-accent/50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                  >
                    <div className="mb-1.5 flex items-center gap-2">
                      <Icon className="h-4 w-4 text-accent" aria-hidden="true" />
                      <Badge tone="neutral">{meta?.label ?? a.category}</Badge>
                      {a.locale !== locale && (
                        <span className="text-[11px] text-ink-3">in English</span>
                      )}
                    </div>
                    <div className="text-sm font-semibold text-ink">{a.title}</div>
                    {a.summary && <p className="mt-1 text-xs text-ink-2">{a.summary}</p>}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
