"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, qs } from "@/lib/api";
import { Card, Input, Skeleton } from "@/components/ui";
import { PageHeader } from "@/components/shell";
import { Avatar } from "@/components/ui";
import { actorColor, activityVerb, formatDateTime } from "@/lib/utils";
import type { AuditItem, Paginated } from "@/lib/types";

export default function AuditPage() {
  const [data, setData] = useState<Paginated<AuditItem> | null>(null);
  const [q, setQ] = useState("");
  const [submittedQ, setSubmittedQ] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const pageSize = 50;

  useEffect(() => {
    setLoading(true);
    api
      .get<Paginated<AuditItem>>("/audit" + qs({ q: submittedQ, page, page_size: pageSize }))
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [submittedQ, page]);

  const pages = data ? Math.max(1, Math.ceil(data.total / pageSize)) : 1;

  return (
    <div>
      <PageHeader title="Audit log" subtitle={data ? `${data.total} entries · append-only record of everything that happened` : "…"} />
      <div className="space-y-4 p-6">
        <Card className="p-3">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setPage(1);
              setSubmittedQ(q.trim());
            }}
          >
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by actor, action, or object…" className="h-9 max-w-md" />
          </form>
        </Card>

        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line bg-surface-2 text-left text-[11px] font-semibold uppercase tracking-wide text-ink-3">
                  <th className="px-4 py-2.5">When</th>
                  <th className="px-4 py-2.5">Actor</th>
                  <th className="px-4 py-2.5">Action</th>
                  <th className="px-4 py-2.5">Object</th>
                  <th className="px-4 py-2.5">Details</th>
                  <th className="px-4 py-2.5">IP</th>
                </tr>
              </thead>
              <tbody>
                {loading &&
                  Array.from({ length: 10 }).map((_, i) => (
                    <tr key={i} className="border-b border-line">
                      <td colSpan={6} className="px-4 py-3">
                        <Skeleton className="h-4" />
                      </td>
                    </tr>
                  ))}
                {!loading &&
                  data?.items.map((e) => (
                    <tr key={e.id} className="border-b border-line last:border-0 align-top hover:bg-surface-2">
                      <td className="whitespace-nowrap px-4 py-2.5 text-ink-3 tnum">{formatDateTime(e.at)}</td>
                      <td className="px-4 py-2.5">
                        <span className="inline-flex items-center gap-1.5 text-ink-2">
                          <Avatar name={e.actor_name} color={actorColor(e.actor_name)} size={20} />
                          {e.actor_name}
                        </span>
                      </td>
                      <td className="px-4 py-2.5">
                        <code className="rounded bg-surface-3 px-1.5 py-0.5 text-[12px] text-ink-2">{e.action}</code>
                        <div className="text-xs text-ink-3">{activityVerb(e.action)}</div>
                      </td>
                      <td className="px-4 py-2.5 text-ink-2">
                        {e.object_id && e.object_type === "contract" ? (
                          <Link href={`/contracts/${e.object_id}`} className="text-accent hover:underline">
                            {e.object_label || e.object_type}
                          </Link>
                        ) : (
                          e.object_label || e.object_type || "—"
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-xs text-ink-3">
                        {e.meta && Object.keys(e.meta).length > 0 ? <code className="break-all">{JSON.stringify(e.meta)}</code> : "—"}
                      </td>
                      <td className="px-4 py-2.5 text-xs text-ink-3 tnum">{e.ip || "—"}</td>
                    </tr>
                  ))}
                {!loading && data && data.items.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-10 text-center text-sm text-ink-3">
                      No matching audit entries.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>

        {pages > 1 && (
          <div className="flex items-center justify-between text-sm text-ink-2">
            <span>
              Page {page} of {pages}
            </span>
            <div className="flex gap-2">
              <button className="rounded-md border border-line bg-white px-3 py-1.5 disabled:opacity-50" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                Previous
              </button>
              <button className="rounded-md border border-line bg-white px-3 py-1.5 disabled:opacity-50" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
