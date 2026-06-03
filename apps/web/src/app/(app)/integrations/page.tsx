"use client";

// Integrations Marketplace — PROTOTYPE connectors gallery (CRM, Microsoft 365, storage, iPaaS).
// Connect/disconnect toggles, categories, search. Webhooks + API keys are the real building
// blocks already shipped; these are the packaged first-class connectors on top. Mockup: in-memory.

import { useMemo, useState } from "react";
import { Check, Plug, Search, Webhook } from "lucide-react";
import { PageHeader } from "@/components/shell";
import { Badge, Button, Card, CardBody, Input } from "@/components/ui";

type Cat = "CRM" | "Microsoft 365" | "Storage" | "Messaging" | "Automation" | "Developer";
type Connector = { id: string; name: string; cat: Cat; desc: string; mark: string; color: string; connected?: boolean };

const CONNECTORS: Connector[] = [
  { id: "sf", name: "Salesforce", cat: "CRM", desc: "Generate & sync contracts from Opportunities; write status back.", mark: "SF", color: "#00A1E0", connected: true },
  { id: "hs", name: "HubSpot", cat: "CRM", desc: "Create agreements from Deals and log signed contracts.", mark: "HS", color: "#FF7A59" },
  { id: "teams", name: "Microsoft Teams", cat: "Messaging", desc: "Approval cards + signature alerts in channels.", mark: "T", color: "#6264A7", connected: true },
  { id: "slack", name: "Slack", cat: "Messaging", desc: "Notify channels on send / sign / decline events.", mark: "S", color: "#4A154B" },
  { id: "outlook", name: "Outlook Add-in", cat: "Microsoft 365", desc: "Send for signature straight from an email.", mark: "O", color: "#0078D4" },
  { id: "sp", name: "SharePoint", cat: "Microsoft 365", desc: "Sync executed PDFs to a document library.", mark: "SP", color: "#038387" },
  { id: "gdrive", name: "Google Drive", cat: "Storage", desc: "Import documents and archive signed copies.", mark: "GD", color: "#1FA463" },
  { id: "dropbox", name: "Dropbox", cat: "Storage", desc: "Two-way sync of contract files.", mark: "DB", color: "#0061FF" },
  { id: "zapier", name: "Zapier", cat: "Automation", desc: "5,000+ app automations on contract events.", mark: "Z", color: "#FF4F00" },
  { id: "power", name: "Power Automate", cat: "Automation", desc: "Microsoft flows on signature & lifecycle events.", mark: "PA", color: "#0066FF" },
  { id: "api", name: "REST API", cat: "Developer", desc: "Full API with bearer keys — already live.", mark: "{}", color: "#475467", connected: true },
  { id: "wh", name: "Webhooks", cat: "Developer", desc: "HMAC-signed event delivery — already live.", mark: "‹›", color: "#475467", connected: true },
];

const CATS: (Cat | "All")[] = ["All", "CRM", "Microsoft 365", "Storage", "Messaging", "Automation", "Developer"];

export default function IntegrationsPage() {
  const [cat, setCat] = useState<Cat | "All">("All");
  const [q, setQ] = useState("");
  const [state, setState] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(CONNECTORS.map((c) => [c.id, !!c.connected]))
  );

  const shown = useMemo(() => {
    const n = q.trim().toLowerCase();
    return CONNECTORS.filter((c) => (cat === "All" || c.cat === cat) && (!n || c.name.toLowerCase().includes(n) || c.desc.toLowerCase().includes(n)));
  }, [cat, q]);

  const connectedCount = Object.values(state).filter(Boolean).length;

  return (
    <div>
      <PageHeader
        title={<span className="flex items-center gap-2">Integrations <Badge tone="accent">Preview</Badge></span>}
        subtitle={`Connect your CRM, Microsoft 365, storage, and automation tools — ${connectedCount} connected.`}
      />

      <div className="space-y-4 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-[220px] flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search integrations…" className="pl-9" />
          </div>
          <div className="flex flex-wrap gap-1.5">
            {CATS.map((c) => (
              <button
                key={c}
                onClick={() => setCat(c)}
                className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${cat === c ? "border-accent bg-accent text-white" : "border-line text-ink-2 hover:bg-surface-2"}`}
              >
                {c}
              </button>
            ))}
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {shown.map((c) => {
            const on = state[c.id];
            return (
              <Card key={c.id} className="transition hover:border-ink-3/30">
                <CardBody className="flex h-full flex-col">
                  <div className="mb-2 flex items-center gap-2.5">
                    <span className="grid h-10 w-10 place-items-center rounded-xl text-sm font-bold text-white" style={{ background: c.color }}>{c.mark}</span>
                    <div className="min-w-0">
                      <div className="truncate font-semibold text-ink">{c.name}</div>
                      <div className="text-[11px] text-ink-3">{c.cat}</div>
                    </div>
                    {on && <span className="ml-auto inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-700"><Check className="h-3 w-3" /> Connected</span>}
                  </div>
                  <p className="flex-1 text-sm text-ink-2">{c.desc}</p>
                  <div className="mt-3">
                    <Button
                      size="sm"
                      variant={on ? "secondary" : "primary"}
                      className="w-full"
                      onClick={() => setState((s) => ({ ...s, [c.id]: !s[c.id] }))}
                    >
                      {on ? "Disconnect" : <><Plug className="h-3.5 w-3.5" /> Connect</>}
                    </Button>
                  </div>
                </CardBody>
              </Card>
            );
          })}
        </div>

        <div className="flex items-center gap-2 rounded-xl border border-line bg-surface-2 px-4 py-3 text-sm text-ink-2">
          <Webhook className="h-4 w-4 text-ink-3" />
          Don&rsquo;t see your tool? Build on the <span className="font-medium text-ink">REST API + webhooks</span> that power every connector here.
        </div>
      </div>
    </div>
  );
}
