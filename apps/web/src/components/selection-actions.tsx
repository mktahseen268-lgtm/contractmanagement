"use client";

/**
 * Select a passage in the document, act on it where you are looking.
 *
 * The comment box and the obligation box already existed at the bottom of the page, and that
 * is the wrong place for both. A reviewer noticing something in clause 2 had to hold the
 * sentence in their head, scroll past the rest of the agreement, and retype enough context for
 * the note to make sense later. Most of the time the note simply did not get written.
 *
 * So: highlight the text and a small menu appears over the selection. Right-click on the
 * selection does the same, because that is where a reader's hand already goes. The passage is
 * carried into the note as a quotation, and the character range is stored with it, so the
 * thread stays attached to the wording rather than floating free three revisions later.
 *
 * Deliberately not a rich annotation layer with margin pins and threading. That is a bigger
 * feature and this is the part that changes whether the note gets written at all.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { MessageSquarePlus, ListTodo, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui";

type Mode = "comment" | "obligation";

interface Picked {
  text: string;
  start: number;
  end: number;
  x: number;
  y: number;
}

/** Character offsets of the selection within `root`'s text, for anchoring the note. */
function offsetsWithin(root: HTMLElement, range: Range): { start: number; end: number } {
  const before = range.cloneRange();
  before.selectNodeContents(root);
  before.setEnd(range.startContainer, range.startOffset);
  const start = before.toString().length;
  return { start, end: start + range.toString().length };
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
  const [mode, setMode] = useState<Mode | null>(null);
  const [text, setText] = useState("");
  const [due, setDue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState("");
  const panel = useRef<HTMLDivElement | null>(null);

  const capture = useCallback(() => {
    const root = containerRef.current;
    if (!root) return;
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed || selection.rangeCount === 0) return;

    const range = selection.getRangeAt(0);
    // Ignore selections that start outside the document body — the page has plenty of other
    // text and a menu appearing over the navigation would be noise.
    if (!root.contains(range.commonAncestorContainer)) return;

    const value = selection.toString().trim();
    if (value.length < 2) return;

    const rect = range.getBoundingClientRect();
    const box = root.getBoundingClientRect();
    const { start, end } = offsetsWithin(root, range);
    setPicked({
      text: value,
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

  // Dismiss on outside click or Escape, but never while a form is open with typing in it —
  // losing a half-written note to a stray click is worse than a menu that lingers.
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

  async function save() {
    if (!picked || !text.trim()) return;
    setBusy(true);
    setError("");
    try {
      if (mode === "comment") {
        await api.post(`/contracts/${contractId}/comments`, {
          body: text.trim(),
          quote: picked.text,
          anchor_start: picked.start,
          anchor_end: picked.end,
        });
      } else {
        await api.post(`/contracts/${contractId}/obligations`, {
          title: text.trim(),
          description: `From the agreement: "${picked.text}"`,
          due_date: due || null,
          owner_id: null,
        });
      }
      setDone(mode === "comment" ? "Comment added." : "Obligation added.");
      setText("");
      setDue("");
      setMode(null);
      onSaved?.();
      window.getSelection()?.removeAllRanges();
      setTimeout(() => setPicked(null), 900);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "That did not save.");
    } finally {
      setBusy(false);
    }
  }

  if (!picked) return null;

  return (
    <div
      ref={panel}
      className="absolute z-30 -translate-x-1/2 -translate-y-full pb-2"
      style={{ left: picked.x, top: picked.y }}
      role="dialog"
      aria-label="Actions for the selected passage"
    >
      <div className="w-[min(24rem,90vw)] rounded-lg border border-line bg-surface shadow-lg">
        <div className="flex items-start gap-2 border-b border-line px-3 py-2">
          <p className="line-clamp-2 flex-1 text-xs italic text-ink-3">“{picked.text}”</p>
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
                  ? "What needs saying about this passage?"
                  : "What has to be done, and by whom?"
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
  );
}
