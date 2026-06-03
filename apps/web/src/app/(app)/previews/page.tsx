"use client";

// Previews hub — a single landing page that showcases every prototyped roadmap feature, grouped
// by area. Each card deep-links to the interactive mockup. Great as a "here's what's coming" demo
// surface; keeps the main nav from ballooning.

import Link from "next/link";
import {
  ArrowRight, Building2, Fingerprint, FileText, Folder, Gavel, GitBranch, Globe, KeyRound, LayoutList,
  Library, Link2, ListChecks, Mails, PenLine, PenTool, Plug, Search, ShieldAlert, ShieldCheck, Sparkles, UserCog,
} from "lucide-react";
import { PageHeader } from "@/components/shell";
import { Badge, Card, CardBody } from "@/components/ui";

type Item = { href: string; title: string; desc: string; icon: typeof PenTool };
type Group = { name: string; items: Item[] };

const GROUPS: Group[] = [
  {
    name: "Signing & sending",
    items: [
      { href: "/signature-studio", title: "Signature Studio", desc: "Drag-and-drop signature, initials, date & text fields onto the document.", icon: PenTool },
      { href: "/bulk-send", title: "Bulk Send", desc: "One template to many signers, with scheduled reminders and expiry.", icon: Mails },
      { href: "/identity-check", title: "Identity Verification", desc: "SMS / email OTP, government-ID, or KBA before signing.", icon: Fingerprint },
      { href: "/client-portal", title: "Client Portal", desc: "External counterparty review, negotiation, and signing surface.", icon: Globe },
      { href: "/temporary-access", title: "Temporary Access", desc: "Grant a vendor scoped, time-limited access to one contract.", icon: Link2 },
    ],
  },
  {
    name: "Authoring",
    items: [
      { href: "/clauses", title: "Clause Library", desc: "Reusable approved language with playbook guidance.", icon: Library },
      { href: "/redline", title: "Redlining", desc: "Tracked changes with accept / reject and author attribution.", icon: PenLine },
      { href: "/docx-studio", title: "Word Import / Export", desc: "Convert .docx to an editable contract and export back.", icon: FileText },
    ],
  },
  {
    name: "Repository & organization",
    items: [
      { href: "/folders", title: "Folders", desc: "Nested folder tree for the repository — beyond flat tags.", icon: Folder },
      { href: "/custom-fields", title: "Custom Fields", desc: "Tenant-defined contract metadata fields.", icon: LayoutList },
      { href: "/search", title: "Full-text Search", desc: "Ranked search inside document bodies and clauses.", icon: Search },
      { href: "/obligations", title: "Obligations Dashboard", desc: "Portfolio-wide obligations with due dates and reminders.", icon: ListChecks },
    ],
  },
  {
    name: "Workflow & intelligence",
    items: [
      { href: "/workflow-builder", title: "Workflow Builder", desc: "Parallel approval groups, conditional routing, SLA escalation.", icon: GitBranch },
      { href: "/ai-analysis", title: "AI Risk Analysis", desc: "Risk score, flagged clauses, missing terms, extracted obligations.", icon: ShieldAlert },
    ],
  },
  {
    name: "People & access",
    items: [
      { href: "/roles", title: "Roles & Permissions", desc: "Editable permission matrix + custom roles.", icon: UserCog },
      { href: "/departments", title: "Departments", desc: "Managed department directory with leads & rollups.", icon: Building2 },
    ],
  },
  {
    name: "Security & admin",
    items: [
      { href: "/sso-admin", title: "SAML SSO", desc: "Enterprise IdP config + SCIM provisioning.", icon: ShieldCheck },
      { href: "/passkeys", title: "Passkeys", desc: "Passwordless, phishing-resistant WebAuthn sign-in.", icon: KeyRound },
      { href: "/legal-hold", title: "Legal Hold", desc: "Preserve contracts & audit trails for litigation / audit.", icon: Gavel },
    ],
  },
  {
    name: "Integrations",
    items: [
      { href: "/integrations", title: "Integrations", desc: "Salesforce, Teams, Slack, Outlook, Drive, Zapier connectors.", icon: Plug },
    ],
  },
];

export default function PreviewsHubPage() {
  const total = GROUPS.reduce((n, g) => n + g.items.length, 0);
  return (
    <div>
      <PageHeader
        title={<span className="flex items-center gap-2">Capabilities <Badge tone="accent">{total}</Badge></span>}
        subtitle="The full platform capability suite, organised by area."
      />

      <div className="space-y-6 p-4">
        <div className="flex items-center gap-2 rounded-xl border border-accent/30 bg-accent/5 px-4 py-3 text-sm text-ink-2">
          <Sparkles className="h-4 w-4 text-accent" />
          Explore the platform&rsquo;s capabilities across signing, authoring, repository, workflow, intelligence, access, security, and integrations.
        </div>

        {GROUPS.map((g) => (
          <div key={g.name}>
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-ink-3">{g.name}</div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {g.items.map((it) => {
                const Icon = it.icon;
                return (
                  <Link key={it.href} href={it.href}>
                    <Card className="group h-full transition hover:border-accent hover:shadow-card">
                      <CardBody className="flex h-full flex-col">
                        <div className="mb-2 flex items-center gap-2">
                          <span className="grid h-9 w-9 place-items-center rounded-lg bg-accent/10 text-accent"><Icon className="h-4 w-4" /></span>
                          <span className="font-semibold text-ink">{it.title}</span>
                        </div>
                        <p className="flex-1 text-sm text-ink-2">{it.desc}</p>
                        <div className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-accent opacity-0 transition group-hover:opacity-100">
                          Open <ArrowRight className="h-3.5 w-3.5" />
                        </div>
                      </CardBody>
                    </Card>
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
