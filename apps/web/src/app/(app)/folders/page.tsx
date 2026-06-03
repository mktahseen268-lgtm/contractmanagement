"use client";

// Folders & Organization — PROTOTYPE of hierarchical foldering for the contract repository (vs the
// current flat tags). A nested folder tree on the left, contracts in the selected folder on the
// right, with move/organize. Mockup: in-memory tree. Wires later to a folders table + contract
// folder_id.

import { useMemo, useState } from "react";
import { ChevronDown, ChevronRight, FileText, Folder, FolderOpen, FolderPlus, Move } from "lucide-react";
import Link from "next/link";
import { PageHeader } from "@/components/shell";
import { Badge, Button, Card, CardBody } from "@/components/ui";
import { statusMeta } from "@/lib/utils";

type Node = { id: string; name: string; count: number; children?: Node[] };
type Doc = { id: string; ref: string; title: string; status: string; folderId: string };

const TREE: Node[] = [
  {
    id: "all", name: "All contracts", count: 31, children: [
      { id: "sales", name: "Sales", count: 12, children: [
        { id: "sales-emea", name: "EMEA", count: 7 },
        { id: "sales-apac", name: "APAC", count: 5 },
      ] },
      { id: "procurement", name: "Procurement", count: 9, children: [
        { id: "proc-vendors", name: "Vendors", count: 6 },
        { id: "proc-saas", name: "SaaS subscriptions", count: 3 },
      ] },
      { id: "hr", name: "HR & People", count: 6 },
      { id: "legal", name: "Legal & Compliance", count: 4 },
    ],
  },
];

const DOCS: Doc[] = [
  { id: "a", ref: "C-2026-0012", title: "Northwind Master Services Agreement", status: "active", folderId: "sales-emea" },
  { id: "b", ref: "C-2026-0033", title: "Lumen Labs Reseller Agreement", status: "out_for_signature", folderId: "sales-apac" },
  { id: "c", ref: "C-2025-0119", title: "Platform Inc Data Processing Addendum", status: "signed", folderId: "proc-saas" },
  { id: "d", ref: "C-2026-0007", title: "Acme ↔ ThiqaTech NDA", status: "active", folderId: "legal" },
  { id: "e", ref: "C-2026-0041", title: "Trial Co Subscription Order", status: "draft", folderId: "proc-saas" },
  { id: "f", ref: "C-2026-0050", title: "Field Engineer Offer Letter", status: "signed", folderId: "hr" },
  { id: "g", ref: "C-2026-0021", title: "GoldStar Vendor Agreement", status: "active", folderId: "proc-vendors" },
  { id: "h", ref: "C-2026-0009", title: "EMEA Distribution Agreement", status: "approved", folderId: "sales-emea" },
];

function descendantIds(node: Node): string[] {
  const ids = [node.id];
  node.children?.forEach((c) => ids.push(...descendantIds(c)));
  return ids;
}

export default function FoldersPage() {
  const [selected, setSelected] = useState("all");
  const [open, setOpen] = useState<Record<string, boolean>>({ all: true, sales: true, procurement: true });

  const selectedNode = useMemo(() => {
    const find = (n: Node): Node | null => (n.id === selected ? n : (n.children?.map(find).find(Boolean) ?? null));
    return TREE.map(find).find(Boolean) ?? TREE[0];
  }, [selected]);

  const inScope = useMemo(() => {
    if (!selectedNode) return [];
    const ids = new Set(descendantIds(selectedNode));
    return DOCS.filter((d) => ids.has(d.folderId) || selected === "all");
  }, [selectedNode, selected]);

  return (
    <div>
      <PageHeader
        title={<span className="flex items-center gap-2">Folders</span>}
        subtitle="Organise the repository into nested folders — beyond flat tags."
        actions={<Button size="sm" variant="secondary"><FolderPlus className="h-3.5 w-3.5" /> New folder</Button>}
      />

      <div className="grid gap-4 p-4 lg:grid-cols-[240px_1fr]">
        {/* tree */}
        <Card className="h-max">
          <CardBody className="space-y-0.5">
            {TREE.map((n) => (
              <TreeNode key={n.id} node={n} depth={0} selected={selected} setSelected={setSelected} open={open} setOpen={setOpen} />
            ))}
          </CardBody>
        </Card>

        {/* docs in folder */}
        <Card>
          <CardBody className="p-0">
            <div className="flex items-center justify-between border-b border-line px-4 py-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-ink">
                <FolderOpen className="h-4 w-4 text-accent" /> {selectedNode?.name}
                <span className="text-xs font-normal text-ink-3">· {inScope.length} contract{inScope.length === 1 ? "" : "s"}</span>
              </div>
              <Button size="sm" variant="ghost"><Move className="h-3.5 w-3.5" /> Move selected</Button>
            </div>
            <div className="divide-y divide-line">
              {inScope.map((d) => (
                <Link key={d.id} href={`/contracts/${d.id}`} className="flex items-center gap-3 px-4 py-2.5 hover:bg-surface-2">
                  <FileText className="h-4 w-4 shrink-0 text-ink-3" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium text-ink">{d.title}</div>
                    <div className="text-[11px] text-ink-3">{d.ref}</div>
                  </div>
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ${statusMeta(d.status).pill}`}>{statusMeta(d.status).label}</span>
                </Link>
              ))}
              {inScope.length === 0 && <div className="px-4 py-8 text-center text-sm text-ink-3">This folder is empty.</div>}
            </div>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

function TreeNode({
  node, depth, selected, setSelected, open, setOpen,
}: {
  node: Node; depth: number; selected: string; setSelected: (id: string) => void;
  open: Record<string, boolean>; setOpen: (fn: (o: Record<string, boolean>) => Record<string, boolean>) => void;
}) {
  const hasKids = !!node.children?.length;
  const isOpen = open[node.id];
  const on = selected === node.id;
  return (
    <div>
      <div
        className={`flex cursor-pointer items-center gap-1 rounded-md py-1.5 pr-2 text-sm ${on ? "bg-accent/10 font-medium text-accent" : "text-ink-2 hover:bg-surface-2"}`}
        style={{ paddingLeft: `${depth * 14 + 6}px` }}
        onClick={() => setSelected(node.id)}
      >
        {hasKids ? (
          <button onClick={(e) => { e.stopPropagation(); setOpen((o) => ({ ...o, [node.id]: !o[node.id] })); }} className="shrink-0 text-ink-3">
            {isOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
          </button>
        ) : (
          <span className="w-3.5 shrink-0" />
        )}
        {on ? <FolderOpen className="h-4 w-4 shrink-0" /> : <Folder className="h-4 w-4 shrink-0" />}
        <span className="flex-1 truncate">{node.name}</span>
        <span className="shrink-0 text-[11px] text-ink-3">{node.count}</span>
      </div>
      {hasKids && isOpen && node.children!.map((c) => (
        <TreeNode key={c.id} node={c} depth={depth + 1} selected={selected} setSelected={setSelected} open={open} setOpen={setOpen} />
      ))}
    </div>
  );
}
