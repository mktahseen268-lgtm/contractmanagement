"use client";

/**
 * Comment on a clause, or raise an obligation from it, without leaving the document.
 *
 * Three ways in, because a reviewer should not have to be told the feature exists:
 *
 *   1. A **marker in the margin** beside every section heading. Always visible, so the
 *      affordance announces itself. This is the one people actually find.
 *   2. **Selecting a passage** — for a specific sentence rather than a whole clause.
 *   3. **Right-click** on a selection, because that is where a reader's hand already goes.
 *
 * Whichever way in, the system records *where in the document* the note came from: the section
 * heading it sits under, the exact passage as it read at the time, and the character range.
 * Six months later "chase the indemnity" is useless and "§ 7. Indemnity — 'the Supplier shall
 * indemnify...' " is actionable, and that difference is the whole point of raising it here
 * rather than on a form at the foot of the page.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { MessageSquarePlus, ListTodo, X, MessageSquare } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui";

type Mode = "comment" | "obligation";

interface Picked {
  /** The passage itself, or the whole section when raised from a margin marker. */
  text: string;
  /** The heading this sits under — "4. Confidentiality". Empty above the first heading. */
  section: string;
  start: number;
  end: number;
  x: number;
  y: number;
}

interface Marker {
  top: number;
  title: string;
  el: HTMLElement;
}

/** Character offsets of a range within `root`'s text, so the note can be re-anchored. */
function offsetsWithin(root: HTMLElement, range: Range): { start: number; end: number } {
  const before = range.cloneRange();
  before.selectNodeContents(root);
  before.setEnd(range.startContainer, range.startOffset);
  const start = before.toString().length;
  return { start, end: start + range.toString().length };
}

/** The heading a node sits under: walk backwards through the rendered document. */
function sectionOf(root: HTMLElement, node: Node | null): string {
  if (!node) return "";
  let el: HTMLElement | null =
    node.nodeType === Node.ELEMENT_NODE ? (node as HTMLElement) : node.parentElement;
  // Climb to the block this node belongs to, then walk back through its siblings.
  while (el && el.parentElement && el.parentElement !== root) el = el.parentElement;
  while (el) {
    if (/^H[1-6]$/.test(el.tagName)) return (el.textContent || "").trim();
    el = el.previousElementSibling as HTMLElement | null;
  }
  return "";
}

/** Everything under a heading, up to the next one — what a margin marker refers to. */
function sectionText(heading: HTMLElement): string {
  const parts: string[] = [];
  let el = heading.nextElementSibling as HTMLElement | null;
  while (el && !/^H[1-6]$/.test(el.tagName)) {
    const t = (el.textContent || "").trim();
    if (t) parts.push(t);
    el = el.nextElementSibling as HTMLElement | null;
  }
  return parts.join(" ").slice(0, 600);
}

export function SelectionActions({
  contractId,
  containerRef,
  onSaved,
}: {
  contractId: string;
  containerRef: React.RefObject<HTMLElement | null>;
  onSaved?: () => void;
}) {
  const [picked, setPicked] = useState<Picked | null>(null);
  const [markers, setMarkers] = useState<Marker[]>([]);
  const [mode, setMode] = useState<Mode | null>(null);
  const [text, setText] = useState("");
  const [due, setDue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState("");
  const panel = useRef<HTMLDivElement | null>(null);

  // --- the margin markers ------------------------------------------------------------------
  // Positions are measured from the rendered headings rather than injected into the editor's
  // DOM: Tiptap owns that tree and rewrites it, and anything added inside would be lost on the
  // next render.
  const measure = useCallback(() => {
    const root = containerRef.current;
    if (!root) return;
    const box = root.getBoundingClientRect();
    const found: Marker[] = [];
    root.querySelectorAll<HTMLElement>("h1, h2, h3").forEach((h) => {
      const title = (h.textContent || "").trim();
      if (!title) return;
      found.push({ top: h.getBoundingClientRect().top - box.top, title, el: h });
    });
    setMarkers(found);
  }, [containerRef]);

  useEffect(() => {
    const root = containerRef.current;
    if (!root) return;
    // The editor renders asynchronously, and the document reflows as fonts settle and the
    // window resizes, so the positions are re-measured rather than taken once.
    const t = setTimeout(measure, 250);
    const observer = new ResizeObserver(measure);
    observer.observe(root);
    window.addEventListener("resize", measure);
    return () => {
      clearTimeout(t);
      observer.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [containerRef, measure]);

  function openForSection(marker: Marker) {
    const root = containerRef.current;
    if (!root) return;
    const box = root.getBoundingClientRect();
    const rect = marker.el.getBoundingClientRect();
    const body = sectionText(marker.el);
    setPicked({
      text: body || marker.title,
      section: marker.title,
      // A whole-section note is anchored to the heading; the section text is what carries the
      // meaning, and a range over an entire clause moves with every edit anyway.
      start: 0,
      end: 0,
      x: rect.left - box.left + rect.width / 2,
      y: rect.top - box.top,
    });
    setMode(null);
    setError("");
    setDone("");
  }

  // --- selecting a passage -------------------------------------------------------------------
  const capture = useCallback(() => {
    const root = containerRef.current;
    if (!root) return;
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed || selection.rangeCount === 0) return;

    const range = selection.getRangeAt(0);
    // Ignore selections starting outside the document body — the page has plenty of other text
    // and a menu over the navigation would be noise.
    if (!root.contains(range.commonAncestorContainer)) return;

    const value = selection.toString().trim();
    if (value.length < 2) return;

    const rect = range.getBoundingClientRect();
    const box = root.getBoundingClientRect();
    const { start, end } = offsetsWithin(root, range);
    setPicked({
      text: value,
      section: sectionOf(root, range.startContainer),
      start,
      end,
      x: rect.left - box.left + rect.width / 2,
      y: rect.top - box.top,
    });
    setMode(null);
    setError("");
    setDone("");
  }, [containerRef]);

  useEffect(() => {
    const root = containerRef.current;
    if (!root) return;

    function onContextMenu(e: MouseEvent) {
      const selection = window.getSelection();
      if (!selection || selection.isCollapsed) return;
      // Only take over the browser menu when there is a selection to act on. Right-clicking
      // plain text still gets the native menu, which people use for copy and translate.
      e.preventDefault();
      capture();
    }

    root.addEventListener("mouseup", capture);
    root.addEventListener("contextmenu", onContextMenu);
    return () => {
      root.removeEventListener("mouseup", capture);
      root.removeEventListener("contextmenu", onContextMenu);
    };
  }, [containerRef, capture]);

  // Dismiss on outside click or Escape — but never while a form holds unsaved typing. Losing a
  // half-written note to a stray click is worse than a panel that lingers.
  useEffect(() => {
    function onDown(e: MouseEvent) {
      if (panel.current?.contains(e.target as Node)) return;
      if (mode && text.trim()) return;
      setPicked(null);
      setMode(null);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setPicked(null);
        setMode(null);
      }
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [mode, text]);

  function close() {
    setPicked(null);
    setMode(null);
    setText("");
    setDue("");
  }

  /** Where in the document this came from, in the form a reader will recognise. */
  function reference(p: Picked): string {
    return p.section ? `§ ${p.section}` : "the document";
  }

  async function save() {
    if (!picked || !text.trim()) return;
    setBusy(true);
    setError("");
    try {
      if (mode === "comment") {
        await api.post(`/contracts/${contractId}/comments`, {
          body: `On ${reference(picked)} — ${text.trim()}`,
          quote: picked.text.slice(0, 1000),
          anchor_start: picked.start || null,
          anchor_end: picked.end || null,
        });
      } else {
        await api.post(`/contracts/${contractId}/obligations`, {
          title: text.trim(),
          // The reference travels with the obligation. Months later this is the difference
          // between a task nobody can act on and one somebody can check against the wording.
          description:
            `Raised from ${reference(picked)} of this agreement.\n\n` +
            `"${picked.text.slice(0, 500)}"`,
          due_date: due || null,
          owner_id: null,
        });
      }
      setDone(mode === "comment" ? "Comment recorded." : "Obligation recorded.");
      setText("");
      setDue("");
      setMode(null);
      onSaved?.();
      window.getSelection()?.removeAllRanges();
      setTimeout(() => setPicked(null), 1100);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "That did not save.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {/* Margin markers. Faint until hovered, so they are discoverable without competing with
          the text they sit beside. */}
      {markers.map((m, i) => (
        <button
          key={`${i}-${m.title}`}
          onClick={() => openForSection(m)}
          style={{ top: m.top }}
          title={`Comment on or raise an obligation from “${m.title}”`}
          aria-label={`Add a note on ${m.title}`}
          className="group absolute -left-1 z-20 flex h-7 w-7 items-center justify-center rounded-md border border-transparent text-ink-3 opacity-40 transition hover:border-line hover:bg-surface hover:text-accent hover:opacity-100 focus:opacity-100"
        >
          <MessageSquare className="h-4 w-4" />
        </button>
      ))}

      {picked && (
        <div
          ref={panel}
          className="absolute z-30 -translate-x-1/2 -translate-y-full pb-2"
          style={{ left: picked.x, top: picked.y }}
          role="dialog"
          aria-label="Add a note on this passage"
        >
          <div className="w-[min(26rem,90vw)] rounded-lg border border-line bg-surface shadow-lg">
            <div className="flex items-start gap-2 border-b border-line px-3 py-2">
              <div className="flex-1">
                {picked.section && (
                  <div className="text-[11px] font-semibold uppercase tracking-wide text-accent">
                    § {picked.section}
                  </div>
                )}
                <p className="line-clamp-2 text-xs italic text-ink-3">“{picked.text}”</p>
              </div>
              <button
                onClick={close}
                className="rounded p-0.5 text-ink-3 hover:text-ink"
                aria-label="Close"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>

            {done && <p className="px-3 py-2 text-xs text-ok">{done}</p>}

            {!mode && !done && (
              <div className="flex gap-1 p-2">
                <Button size="sm" variant="ghost" onClick={() => setMode("comment")}>
                  <MessageSquarePlus className="h-3.5 w-3.5" /> Comment
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setMode("obligation")}>
                  <ListTodo className="h-3.5 w-3.5" /> Obligation
                </Button>
              </div>
            )}

            {mode && (
              <div className="space-y-2 p-3">
                {error && <p className="text-xs text-danger">{error}</p>}
                <textarea
                  autoFocus
                  rows={mode === "comment" ? 3 : 2}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder={
                    mode === "comment"
                      ? "What needs saying about this clause?"
                      : "What has to be done? e.g. Serve renewal notice 60 days before expiry"
                  }
                  className="w-full rounded-md border border-line bg-surface px-2.5 py-2 text-sm text-ink outline-none focus:border-accent"
                />
                {mode === "obligation" && (
                  <input
                    type="date"
                    value={due}
                    onChange={(e) => setDue(e.target.value)}
                    aria-label="Due date"
                    className="h-8 rounded-md border border-line bg-surface px-2 text-sm text-ink outline-none focus:border-accent"
                  />
                )}
                <p className="text-[11px] text-ink-3">
                  Recorded against {reference(picked)}, with the wording quoted.
                </p>
                <div className="flex items-center gap-2">
                  <Button size="sm" onClick={save} loading={busy} disabled={!text.trim()}>
                    Save
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setMode(null)} disabled={busy}>
                    Back
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
