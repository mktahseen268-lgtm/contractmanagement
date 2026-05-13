"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ChevronRight, Sparkles } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { PageHeader } from "@/components/shell";
import { ContractForm } from "@/components/contract-form";
import { Button, Card, CardBody, CardHeader, CardTitle, ErrorBanner, Field, Input, Skeleton } from "@/components/ui";
import { contractTypeLabel, titleCase } from "@/lib/utils";
import { api, ApiError } from "@/lib/api";
import type { ContractDetail, ContractTemplate } from "@/lib/types";

export default function NewContractPage() {
  const { me } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const templateId = params?.get("template") ?? "";
  const [template, setTemplate] = useState<ContractTemplate | null>(null);
  const [loadingTemplate, setLoadingTemplate] = useState(!!templateId);
  const [title, setTitle] = useState("");
  const [counterparty, setCounterparty] = useState("");
  const [effective, setEffective] = useState("");
  const [end, setEnd] = useState("");
  const [value, setValue] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!templateId) return;
    setLoadingTemplate(true);
    api.get<ContractTemplate>(`/templates/${templateId}`)
      .then((t) => {
        setTemplate(t);
        // default the title to "<template name> – <today>"
        setTitle(`${t.name}`);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Couldn't load that template."))
      .finally(() => setLoadingTemplate(false));
  }, [templateId]);

  async function spawn(e: React.FormEvent) {
    e.preventDefault();
    if (!template) return;
    setBusy(true); setError("");
    try {
      const c = await api.post<ContractDetail>(`/templates/${template.id}/use`, {
        title: title.trim(), counterparty: counterparty.trim(),
        value: Number(value) || 0,
        effective_date: effective || null, end_date: end || null,
      });
      router.push(`/contracts/${c.id}`);
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "Couldn't create the contract.");
    } finally {
      setBusy(false);
    }
  }

  if (templateId) {
    return (
      <div>
        <PageHeader title="New contract — from template" subtitle={template ? `Using "${template.name}"` : "Loading template…"} />
        <div className="p-6">
          {error && <ErrorBanner message={error} className="mb-3" />}
          {loadingTemplate && <Skeleton className="h-40" />}
          {!loadingTemplate && template && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-1.5"><Sparkles className="h-4 w-4 text-accent" /> {template.name}</CardTitle>
                <div className="text-xs text-ink-3">
                  {contractTypeLabel(template.contract_type)} · {template.default_term_months}mo · {titleCase(template.default_renewal_type)} · {titleCase(template.default_risk_level)} risk · {template.default_currency}
                </div>
              </CardHeader>
              <CardBody>
                <form onSubmit={spawn} className="grid gap-3 sm:grid-cols-12">
                  <div className="sm:col-span-6"><Field label="Title"><Input value={title} onChange={(e) => setTitle(e.target.value)} required /></Field></div>
                  <div className="sm:col-span-6"><Field label="Counterparty"><Input value={counterparty} onChange={(e) => setCounterparty(e.target.value)} placeholder="e.g. Globex LLC" /></Field></div>
                  <div className="sm:col-span-4"><Field label="Value"><Input type="number" min={0} step={0.01} value={value} onChange={(e) => setValue(Number(e.target.value))} /></Field></div>
                  <div className="sm:col-span-4"><Field label="Effective" hint="Defaults to today"><Input type="date" value={effective} onChange={(e) => setEffective(e.target.value)} /></Field></div>
                  <div className="sm:col-span-4"><Field label="End" hint="Defaults to effective + template term"><Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></Field></div>
                  <div className="flex items-center justify-between sm:col-span-12">
                    <Button type="button" variant="ghost" size="sm" onClick={() => router.push("/contracts/new")}>Skip template &amp; start blank</Button>
                    <Button type="submit" loading={busy} disabled={!title.trim()}>
                      Create draft from template <ChevronRight className="h-4 w-4" />
                    </Button>
                  </div>
                </form>
              </CardBody>
            </Card>
          )}
        </div>
      </div>
    );
  }

  return (
    <div>
      <PageHeader title="New contract" subtitle="Fill in the basics — you can refine the document afterwards." />
      <ContractForm mode="create" currency={me?.tenant.currency} />
    </div>
  );
}
