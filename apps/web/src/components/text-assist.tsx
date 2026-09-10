"use client";

/**
 * Writing assistance attached to any text field in the product.
 *
 * Two rules shape this component:
 *
 * 1. **It disappears when no model is configured.** The deployment may have no assistant, and a
 *    button that only ever reports "not configured" is worse than no button. The config call is
 *    made once per session and cached, so dropping this next to twenty fields costs one request.
 * 2. **It never edits anything on its own.** The suggestion is shown next to the original and
 *    applied only when the author presses Use. Silently rewriting a clause because a model
 *    thought it read better is the one behaviour a contract tool cannot have.
 */

import { useEffect, useRef, useState } from "react";
import { Check, Sparkles, X } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui";

interface AssistConfig {
  enabled: boolean;
  provider: string;
  modes: string[];
  max_chars: number;
}

interface AssistResult {
  text: string;
  changed: boolean;
  provider: string;
  error: string;
}

const LABELS: Record<string, string> = {
  correct: "Fix spelling & grammar",
  formal: "Make it formal",
  shorten: "Make it concise",
  plain: "Plain language",
};

/** One shared lookup for the whole session, so the control is cheap to attach anywhere. */
let configPromise: Promise<AssistConfig> | null = null;

function loadConfig(): Promise<AssistConfig> {
  configPromise ??= api
    .get<AssistConfig>("/ai/assist/config")
    .catch(() => ({ enabled: false, provider: "none", modes: [], max_chars: 0 }));
  return configPromise;
}

export function TextAssist({
  value,
  onAccept,
  className = "",
}: {
  value: string;
  onAccept: (next: string) => void;
  className?: string;
}) {
  const [config, setConfig] = useState<AssistConfig | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<AssistResult | null>(null);
  const [note, setNote] = useState("");
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    loadConfig().then((c) => {
      if (alive.current) setConfig(c);
    });
    return () => {
      alive.current = false;
    };
  }, []);

  // Nothing configured, or nothing typed yet: render nothing at all rather than a disabled row.
  if (!config?.enabled || !value.trim()) return null;

  const tooLong = value.trim().length > config.max_chars;

  async function run(mode: string) {
    setBusy(mode);
    setNote("");
    setResult(null);
    try {
      const r = await api.post<AssistResult>("/ai/assist", { text: value, mode });
      if (!alive.current) return;
      if (r.error) setNote(r.error);
      else if (!r.changed) setNote("No changes suggested — it already reads correctly.");
      else setResult(r);
    } catch {
      if (alive.current) setNote("The writing assistant is unavailable.");
    } finally {
      if (alive.current) setBusy(null);
    }
  }

  return (
    <div className={`mt-2 ${className}`}>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="flex items-center gap-1 text-xs text-ink-3">
          <Sparkles className="h-3.5 w-3.5" /> Assist
        </span>
        {config.modes.map((mode) => (
          <Button
            key={mode}
            size="sm"
            variant="ghost"
            onClick={() => run(mode)}
            loading={busy === mode}
            disabled={!!busy || tooLong}
            title={LABELS[mode] ?? mode}
          >
            {LABELS[mode] ?? mode}
          </Button>
        ))}
        {tooLong && (
          <span className="text-xs text-ink-3">
            Too long for one pass — select up to {config.max_chars.toLocaleString()} characters.
          </span>
        )}
        {note && <span className="text-xs text-ink-3">{note}</span>}
      </div>

      {result && (
        <div className="mt-2 rounded-md border border-line bg-surface-2 p-3">
          <div className="mb-1.5 text-xs font-medium text-ink-2">Suggested</div>
          {/* The suggestion is shown in full, not as a diff. A reviewer accepting wording into a
              legal document should read the wording, not a summary of what moved. */}
          <p className="whitespace-pre-wrap text-sm text-ink">{result.text}</p>
          <div className="mt-2 flex items-center gap-2">
            <Button
              size="sm"
              onClick={() => {
                onAccept(result.text);
                setResult(null);
                setNote("Applied.");
              }}
            >
              <Check className="h-3.5 w-3.5" /> Use this
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setResult(null)}>
              <X className="h-3.5 w-3.5" /> Discard
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
