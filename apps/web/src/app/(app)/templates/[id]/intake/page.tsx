"use client";

/**
 * Guided drafting wizard — the RFI's core journey (§2.3), as a step-through.
 *
 *   1. Template   — what you are raising (chosen on the previous screen; shown for context)
 *   2. Clauses    — pick a fallback position where policy allows one, add optional clauses
 *   3. Details    — the structured form: drop-downs, LOVs, typed fields
 *   4. Preview    — exactly what the draft will say, before committing to it
 *
 *   GET  /templates/{id}/form              fields, clause choices, defaults
 *   GET  /templates/{id}/optional-clauses  clauses this template does not already use
 *   POST /templates/{id}/preview           the wording
 *   POST /templates/{id}/generate          creates the draft
 *
 * Validation is not duplicated here beyond `required` hints: the server is the system of
 * record, and a second copy of the rules in the browser is a second copy to drift.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Check,
  Eye,
  FileText,
  Lock,
  Scale,
  Sparkles,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { PageHeader } from "@/components/shell";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  ErrorBanner,
  Field,
  Input,
  Select,
  Skeleton,
  Textarea,
} from "@/components/ui";
import type {
  ContractDetail,
  TemplateField,
  TemplateForm,
  TemplatePreview,
} from "@/lib/types";

type Values = Record<string, unknown>;

type ClauseOption = {
  key: string;
  title: string;
  position: string;
  risk_level: string;
  guidance: string;
  body: string;
  is_default: boolean;
};
type ClauseChoice = { key: string; title: string; options: ClauseOption[] };
type OptionalClause = {
  key: string;
  title: string;
  category: string;
  risk_level: string;
  guidance: string;
};

const STEPS = ["Clauses", "Details", "Preview"] as const;
type Step = (typeof STEPS)[number];

const RISK_TONE: Record<string, string> = {
  low: "text-emerald-700",
  medium: "text-amber-700",
  high: "text-orange-700",
  critical: "text-red-700",
};

export default function IntakeWizardPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const templateId = params.id;

  const [form, setForm] = useState<TemplateForm | null>(null);
  const [optional, setOptional] = useState<OptionalClause[]>([]);
  const [step, setStep] = useState<Step>("Clauses");
  const [values, setValues] = useState<Values>({});
  const [choices, setChoices] = useState<Record<string, string>>({});
  const [extras, setExtras] = useState<string[]>([]);
  const [title, setTitle] = useState("");
  const [counterparty, setCounterparty] = useState("");
  const [value, setValue] = useState("");
  const [effectiveDate, setEffectiveDate] = useState("");
  const [preview, setPreview] = useState<TemplatePreview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .get<TemplateForm>(`/templates/${templateId}/form`)
      .then((f) => {
        setForm(f);
        const seeded: Values = {};
        for (const field of f.fields) {
          if (field.default !== null && field.default !== undefined && field.default !== "") {
            seeded[field.key] = field.default;
          }
        }
        setValues(seeded);
        // No clause choices to make? Skip straight to the form rather than showing an
        // empty step just to keep the wizard symmetrical.
        if ((f.clause_choices ?? []).length === 0) setStep("Details");
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Template not found."));
    api
      .get<OptionalClause[]>(`/templates/${templateId}/optional-clauses`)
      .then(setOptional)
      .catch(() => setOptional([]));
  }, [templateId]);

  const clauseChoices = useMemo(
    () => (form?.clause_choices ?? []) as unknown as ClauseChoice[],
    [form],
  );

  const groups = useMemo(() => {
    if (!form) return [];
    const byGroup = new Map<string, TemplateField[]>();
    for (const field of form.fields) {
      const key = field.group || "";
      byGroup.set(key, [...(byGroup.get(key) ?? []), field]);
    }
    return Array.from(byGroup.entries());
  }, [form]);

  const setField = useCallback((key: string, next: unknown) => {
    setValues((v) => ({ ...v, [key]: next }));
    setPreview(null);
  }, []);

  const runPreview = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      setPreview(
        await api.post<TemplatePreview>(`/templates/${templateId}/preview`, {
          values,
          title,
          counterparty,
          clause_choices: choices,
          extra_clauses: extras,
        }),
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not render the preview.");
    } finally {
      setBusy(false);
    }
  }, [templateId, values, title, counterparty, choices, extras]);

  useEffect(() => {
    if (step === "Preview") void runPreview();
  }, [step, runPreview]);

  async function generate() {
    setBusy(true);
    setError("");
    try {
      const contract = await api.post<ContractDetail>(`/templates/${templateId}/generate`, {
        title: title.trim(),
        counterparty: counterparty.trim(),
        value: Number(value) || 0,
        effective_date: effectiveDate || null,
        values,
        clause_choices: choices,
        extra_clauses: extras,
      });
      router.push(`/contracts/${contract.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The draft could not be generated.");
      setBusy(false);
    }
  }

  if (error && !form) return <ErrorBanner message={error} />;
  if (!form) return <Skeleton className="h-64" />;

  const stepIndex = STEPS.indexOf(step);
  const canGenerate = form.usable && title.trim().length > 0;

  return (
    <div>
      <PageHeader
        title={form.name}
        subtitle={
          form.usable
            ? `Approved wording v${form.version_no} — fill the steps and the draft generates itself`
            : "This template is not approved for use yet"
        }
        actions={
          <Link href="/templates">
            <Button size="sm" variant="ghost">
              <ArrowLeft className="h-3.5 w-3.5" /> Templates
            </Button>
          </Link>
        }
      />

      <div className="space-y-5 p-6">
        {error && <ErrorBanner message={error} />}

        {!form.usable && (
          <Card className="border-amber-300/60">
            <CardBody className="flex items-start gap-2 py-3 text-sm text-ink-2">
              <Lock className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
              <span>
                This template is <strong>{form.status.replace("_", " ")}</strong>. Agreements can
                only be raised from wording somebody has approved.
              </span>
            </CardBody>
          </Card>
        )}

        {form.problems.length > 0 && (
          <Card className="border-red-300/60">
            <CardBody className="space-y-1 py-3">
              <div className="flex items-center gap-2 text-sm font-medium text-ink">
                <AlertTriangle className="h-4 w-4 text-red-600" /> This template has defects
              </div>
              {form.problems.map((p) => (
                <p key={p} className="text-sm text-ink-2">
                  {p}
                </p>
              ))}
            </CardBody>
          </Card>
        )}

        {/* step rail */}
        <div className="flex flex-wrap items-center gap-2">
          {STEPS.map((s, i) => (
            <button
              key={s}
              onClick={() => setStep(s)}
              className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm transition ${
                s === step
                  ? "bg-accent text-white"
                  : i < stepIndex
                    ? "bg-accent-subtle text-accent"
                    : "bg-surface-3 text-ink-3"
              }`}
            >
              <span className="font-mono text-xs">{i + 1}</span>
              {s}
              {i < stepIndex && <Check className="h-3 w-3" />}
            </button>
          ))}
        </div>

        {step === "Clauses" && (
          <ClauseStep
            choices={clauseChoices}
            chosen={choices}
            optional={optional}
            extras={extras}
            disabled={!form.usable}
            onChoose={(key, option) => {
              setChoices((c) => ({ ...c, [key]: option }));
              setPreview(null);
            }}
            onToggleExtra={(key) => {
              setExtras((e) => (e.includes(key) ? e.filter((k) => k !== key) : [...e, key]));
              setPreview(null);
            }}
          />
        )}

        {step === "Details" && (
          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-1.5">
                  <FileText className="h-4 w-4" /> The agreement
                </CardTitle>
              </CardHeader>
              <CardBody className="grid gap-3 sm:grid-cols-2">
                <div className="sm:col-span-2">
                  <Field label="Title *">
                    <Input
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      disabled={!form.usable}
                      placeholder="e.g. Acme Acquiring Agreement"
                    />
                  </Field>
                </div>
                <Field label="Counterparty">
                  <Input
                    value={counterparty}
                    onChange={(e) => setCounterparty(e.target.value)}
                    disabled={!form.usable}
                  />
                </Field>
                <Field label={`Value (${form.defaults.currency ?? ""})`}>
                  <Input
                    type="number"
                    min={0}
                    step="0.01"
                    value={value}
                    onChange={(e) => setValue(e.target.value)}
                    disabled={!form.usable}
                  />
                </Field>
                <Field label="Effective date">
                  <Input
                    type="date"
                    value={effectiveDate}
                    onChange={(e) => setEffectiveDate(e.target.value)}
                    disabled={!form.usable}
                  />
                </Field>
              </CardBody>
            </Card>

            {groups.map(([group, fields]) => (
              <Card key={group || "_"}>
                <CardHeader>
                  <CardTitle className="flex items-center gap-1.5">
                    <Sparkles className="h-4 w-4 text-accent" />
                    {group || "Agreement details"}
                  </CardTitle>
                </CardHeader>
                <CardBody className="grid gap-3 sm:grid-cols-2">
                  {fields.map((field: TemplateField) => (
                    <FieldInput
                      key={field.key}
                      field={field}
                      value={values[field.key]}
                      disabled={!form.usable}
                      onChange={(next) => setField(field.key, next)}
                    />
                  ))}
                </CardBody>
              </Card>
            ))}
          </div>
        )}

        {step === "Preview" && <PreviewPane preview={preview} busy={busy} />}

        {/* navigation */}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Button
            variant="ghost"
            disabled={stepIndex === 0}
            onClick={() => setStep(STEPS[Math.max(0, stepIndex - 1)])}
          >
            <ArrowLeft className="h-3.5 w-3.5" /> Back
          </Button>
          {step === "Preview" ? (
            <Button loading={busy} disabled={!canGenerate} onClick={generate}>
              Generate the draft <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          ) : (
            <Button onClick={() => setStep(STEPS[Math.min(STEPS.length - 1, stepIndex + 1)])}>
              Next <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------- clauses ---------- */

function ClauseStep({
  choices,
  chosen,
  optional,
  extras,
  disabled,
  onChoose,
  onToggleExtra,
}: {
  choices: ClauseChoice[];
  chosen: Record<string, string>;
  optional: OptionalClause[];
  extras: string[];
  disabled: boolean;
  onChoose: (key: string, option: string) => void;
  onToggleExtra: (key: string) => void;
}) {
  return (
    <div className="space-y-4">
      {choices.length === 0 && optional.length === 0 && (
        <Card>
          <CardBody className="py-8 text-center text-sm text-ink-2">
            This template does not compose any library clauses, so there is nothing to choose.
          </CardBody>
        </Card>
      )}

      {choices.map((choice) => {
        const selected = chosen[choice.key] ?? choice.key;
        return (
          <Card key={choice.key}>
            <CardHeader>
              <CardTitle className="flex items-center gap-1.5">
                <Scale className="h-4 w-4" /> {choice.title}
              </CardTitle>
            </CardHeader>
            <CardBody className="space-y-2">
              {choice.options.length === 1 && (
                <p className="text-xs text-ink-3">
                  No fallback position is approved for this clause — the standard wording is
                  the only option.
                </p>
              )}
              {choice.options.map((option) => (
                <label
                  key={option.key}
                  className={`block cursor-pointer rounded-md border p-2 transition ${
                    selected === option.key ? "border-accent bg-accent-subtle/30" : "border-line"
                  }`}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <input
                      type="radio"
                      name={choice.key}
                      checked={selected === option.key}
                      disabled={disabled}
                      onChange={() => onChoose(choice.key, option.key)}
                    />
                    <span className="text-sm font-medium text-ink">{option.title}</span>
                    <Badge tone={option.is_default ? "accent" : "neutral"}>
                      {option.is_default ? "standard" : option.position}
                    </Badge>
                    <span
                      className={`text-xs font-medium ${RISK_TONE[option.risk_level] ?? "text-ink-3"}`}
                    >
                      {option.risk_level} risk
                    </span>
                  </div>
                  <p className="mt-1 line-clamp-3 text-xs text-ink-2">{option.body}</p>
                  {option.guidance && (
                    <p className="mt-1 text-xs text-ink-3">{option.guidance}</p>
                  )}
                </label>
              ))}
            </CardBody>
          </Card>
        );
      })}

      {optional.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Optional clauses</CardTitle>
          </CardHeader>
          <CardBody className="space-y-2">
            <p className="text-xs text-ink-3">
              Approved wording this template does not already include. Anything you add is
              appended to the draft.
            </p>
            {optional.map((c) => (
              <label
                key={c.key}
                className="flex cursor-pointer items-start gap-2 rounded-md border border-line p-2"
              >
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={extras.includes(c.key)}
                  disabled={disabled}
                  onChange={() => onToggleExtra(c.key)}
                />
                <span>
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-ink">{c.title}</span>
                    {c.category && (
                      <span className="rounded-full bg-surface-3 px-2 py-0.5 text-[10px] text-ink-3">
                        {c.category}
                      </span>
                    )}
                    <span
                      className={`text-xs font-medium ${RISK_TONE[c.risk_level] ?? "text-ink-3"}`}
                    >
                      {c.risk_level} risk
                    </span>
                  </span>
                  {c.guidance && <span className="block text-xs text-ink-3">{c.guidance}</span>}
                </span>
              </label>
            ))}
          </CardBody>
        </Card>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------- fields ---------- */

function FieldInput({
  field,
  value,
  disabled,
  onChange,
}: {
  field: TemplateField;
  value: unknown;
  disabled: boolean;
  onChange: (next: unknown) => void;
}) {
  const wide = field.type === "textarea" || field.type === "multiselect";
  const label = field.required ? `${field.label} *` : field.label;

  let control: React.ReactNode;
  switch (field.type) {
    case "textarea":
      control = (
        <Textarea
          rows={4}
          value={String(value ?? "")}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
        />
      );
      break;
    case "select":
      control = (
        <Select
          value={String(value ?? "")}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">Select…</option>
          {field.options.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </Select>
      );
      break;
    case "multiselect": {
      const selected = Array.isArray(value) ? (value as string[]) : [];
      control = (
        <div className="flex flex-wrap gap-2">
          {field.options.map((o) => (
            <label
              key={o}
              className="inline-flex items-center gap-1.5 rounded-md border border-line px-2 py-1 text-sm text-ink-2"
            >
              <input
                type="checkbox"
                checked={selected.includes(o)}
                disabled={disabled}
                onChange={(e) =>
                  onChange(e.target.checked ? [...selected, o] : selected.filter((s) => s !== o))
                }
              />
              {o}
            </label>
          ))}
        </div>
      );
      break;
    }
    case "boolean":
      control = (
        <label className="inline-flex items-center gap-2 text-sm text-ink-2">
          <input
            type="checkbox"
            checked={Boolean(value)}
            disabled={disabled}
            onChange={(e) => onChange(e.target.checked)}
          />
          Yes
        </label>
      );
      break;
    case "date":
      control = (
        <Input
          type="date"
          value={String(value ?? "")}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
        />
      );
      break;
    case "number":
    case "money":
      control = (
        <Input
          type="number"
          step={field.type === "money" ? "0.01" : "1"}
          min={field.minimum ?? undefined}
          max={field.maximum ?? undefined}
          value={String(value ?? "")}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
        />
      );
      break;
    default:
      control = (
        <Input
          value={String(value ?? "")}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
        />
      );
  }

  return (
    <div className={wide ? "sm:col-span-2" : ""}>
      <Field label={label} hint={field.help || undefined}>
        {control}
      </Field>
    </div>
  );
}

/* ------------------------------------------------------------------- preview ---------- */

function PreviewPane({ preview, busy }: { preview: TemplatePreview | null; busy: boolean }) {
  if (busy && !preview) return <Skeleton className="h-64" />;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5">
          <Eye className="h-4 w-4" /> Draft preview
          {preview?.ok && (
            <Badge tone="accent" className="ml-1">
              <Check className="h-3 w-3" /> ready
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardBody className="space-y-3">
        {preview?.errors.length ? (
          <div className="space-y-1 rounded-md border border-red-300/60 p-2">
            {preview.errors.map((e) => (
              <p key={e} className="text-sm text-ink-2">
                {e}
              </p>
            ))}
          </div>
        ) : null}

        {preview?.missing_clauses?.length ? (
          <div className="rounded-md border border-red-300/60 p-2 text-sm text-ink-2">
            <div className="flex items-center gap-1.5 font-medium text-ink">
              <AlertTriangle className="h-4 w-4 text-red-600" /> Clauses with no approved wording
            </div>
            <p>{preview.missing_clauses.join(", ")} — the draft cannot be generated.</p>
          </div>
        ) : null}

        {preview?.unresolved.length ? (
          <div className="rounded-md border border-amber-300/60 p-2 text-sm text-ink-2">
            <div className="flex items-center gap-1.5 font-medium text-ink">
              <AlertTriangle className="h-4 w-4 text-amber-600" /> Nothing fills these
            </div>
            <p>
              {preview.unresolved.map((u) => `{{${u}}}`).join(", ")} — the draft will not be
              generated with gaps in it.
            </p>
          </div>
        ) : null}

        {preview && (
          <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-md bg-surface-3 p-3 font-mono text-xs text-ink">
            {preview.body}
          </pre>
        )}
      </CardBody>
    </Card>
  );
}
