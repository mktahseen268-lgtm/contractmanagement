"use client";

import { useEffect, useReducer, useRef, useState } from "react";
import { EditorContent, useEditor, type Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { Markdown } from "tiptap-markdown";
import {
  Bold,
  Braces,
  ChevronDown,
  Code,
  Code2,
  Heading1,
  Heading2,
  Heading3,
  Italic,
  List,
  ListOrdered,
  Minus,
  Pilcrow,
  Quote,
  Redo2,
  Undo2,
} from "lucide-react";
import { cn, CONTRACT_VARIABLES } from "@/lib/utils";

interface Cmd {
  icon: typeof Bold;
  title: string;
  run: () => void;
  active?: () => boolean;
  disabled?: () => boolean;
}

/**
 * Block-style rich editor (Tiptap) that round-trips Markdown — a first cut of the
 * Notion×Docs×PandaDoc editor in docs/11. v1: blocks via a toolbar (paragraph / H1–H3 /
 * bold / italic / code / lists / quote / code block / divider / undo–redo); content is stored
 * as Markdown so the PDF renderer and the rest of the system keep working. v2 adds the slash
 * menu, variables, clause inserts, comments, suggestions, version history and collaboration.
 */
export function BlockEditor({
  value,
  onChange,
  editable = true,
  className,
}: {
  value: string;
  onChange?: (markdown: string) => void;
  editable?: boolean;
  className?: string;
}) {
  const editor = useEditor({
    immediatelyRender: false,
    editable,
    extensions: [
      StarterKit.configure({ heading: { levels: [1, 2, 3, 4] } }),
      Markdown.configure({
        html: false,
        tightLists: true,
        bulletListMarker: "-",
        linkify: false,
        breaks: false,
        transformPastedText: true,
        transformCopiedText: true,
      }),
    ],
    content: value || "",
    editorProps: { attributes: { class: cn("cm-doc min-h-[42vh]", className) } },
    onUpdate: ({ editor }) => onChange?.(editor.storage.markdown.getMarkdown()),
  });

  const [, force] = useReducer((x) => x + 1, 0);
  const [varOpen, setVarOpen] = useState(false);
  const varRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!editor) return;
    const f = () => force();
    editor.on("transaction", f);
    return () => {
      editor.off("transaction", f);
    };
  }, [editor]);
  useEffect(() => {
    editor?.setEditable(editable);
  }, [editor, editable]);
  useEffect(() => {
    if (!varOpen) return;
    const onDocClick = (e: MouseEvent) => {
      if (varRef.current && !varRef.current.contains(e.target as Node)) setVarOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [varOpen]);

  if (!editor) {
    return <div className="cm-doc min-h-[42vh] px-1 py-2 text-sm text-ink-3">Loading editor…</div>;
  }

  const e: Editor = editor;
  const groups: Cmd[][] = [
    [{ icon: Pilcrow, title: "Text", run: () => e.chain().focus().setParagraph().run(), active: () => e.isActive("paragraph") }],
    [
      { icon: Heading1, title: "Heading 1", run: () => e.chain().focus().toggleHeading({ level: 1 }).run(), active: () => e.isActive("heading", { level: 1 }) },
      { icon: Heading2, title: "Heading 2", run: () => e.chain().focus().toggleHeading({ level: 2 }).run(), active: () => e.isActive("heading", { level: 2 }) },
      { icon: Heading3, title: "Heading 3", run: () => e.chain().focus().toggleHeading({ level: 3 }).run(), active: () => e.isActive("heading", { level: 3 }) },
    ],
    [
      { icon: Bold, title: "Bold  ⌘B", run: () => e.chain().focus().toggleBold().run(), active: () => e.isActive("bold") },
      { icon: Italic, title: "Italic  ⌘I", run: () => e.chain().focus().toggleItalic().run(), active: () => e.isActive("italic") },
      { icon: Code, title: "Inline code", run: () => e.chain().focus().toggleCode().run(), active: () => e.isActive("code") },
    ],
    [
      { icon: List, title: "Bullet list", run: () => e.chain().focus().toggleBulletList().run(), active: () => e.isActive("bulletList") },
      { icon: ListOrdered, title: "Numbered list", run: () => e.chain().focus().toggleOrderedList().run(), active: () => e.isActive("orderedList") },
      { icon: Quote, title: "Quote", run: () => e.chain().focus().toggleBlockquote().run(), active: () => e.isActive("blockquote") },
      { icon: Code2, title: "Code block", run: () => e.chain().focus().toggleCodeBlock().run(), active: () => e.isActive("codeBlock") },
      { icon: Minus, title: "Divider", run: () => e.chain().focus().setHorizontalRule().run() },
    ],
    [
      { icon: Undo2, title: "Undo  ⌘Z", run: () => e.chain().focus().undo().run(), disabled: () => !e.can().undo() },
      { icon: Redo2, title: "Redo  ⌘⇧Z", run: () => e.chain().focus().redo().run(), disabled: () => !e.can().redo() },
    ],
  ];

  return (
    <div>
      {editable && (
        <div className="flex flex-wrap items-center gap-0.5 rounded-t-lg border border-line bg-surface-2 px-2 py-1.5">
          {groups.map((g, gi) => (
            <div key={gi} className="flex items-center gap-0.5">
              {gi > 0 && <span className="mx-1 h-5 w-px bg-line" />}
              {g.map((cmd) => {
                const Icon = cmd.icon;
                const active = cmd.active?.() ?? false;
                const disabled = cmd.disabled?.() ?? false;
                return (
                  <button
                    key={cmd.title}
                    type="button"
                    title={cmd.title}
                    onClick={cmd.run}
                    disabled={disabled}
                    className={cn(
                      "grid h-7 w-7 place-items-center rounded-md text-ink-2 transition-colors hover:bg-surface-3 disabled:opacity-40",
                      active && "bg-accent-subtle text-accent",
                    )}
                  >
                    <Icon className="h-3.5 w-3.5" />
                  </button>
                );
              })}
            </div>
          ))}
          <span className="mx-1 h-5 w-px bg-line" />
          <div ref={varRef} className="relative">
            <button
              type="button"
              title="Insert a merge variable"
              onClick={() => setVarOpen((o) => !o)}
              className={cn("flex h-7 items-center gap-1 rounded-md px-2 text-[12px] font-medium text-ink-2 transition-colors hover:bg-surface-3", varOpen && "bg-surface-3")}
            >
              <Braces className="h-3.5 w-3.5" /> Variable <ChevronDown className="h-3 w-3" />
            </button>
            {varOpen && (
              <div className="absolute left-0 top-9 z-50 w-52 overflow-hidden rounded-lg border border-line bg-white py-1 shadow-pop">
                <div className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wide text-ink-3">Merge fields</div>
                {CONTRACT_VARIABLES.map((v) => (
                  <button
                    key={v.key}
                    type="button"
                    onClick={() => {
                      e.chain().focus().insertContent(`{{${v.key}}}`).run();
                      setVarOpen(false);
                    }}
                    className="flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-sm text-ink-2 hover:bg-surface-3"
                  >
                    <span>{v.label}</span>
                    <code className="text-[10px] text-ink-3">{`{{${v.key}}}`}</code>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
      <div className={cn("bg-white px-4 py-3", editable ? "rounded-b-lg border border-t-0 border-line" : "")}>
        <EditorContent editor={editor} />
      </div>
    </div>
  );
}
