"use client";

import * as React from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

// ---------- Button ----------

type ButtonVariant = "primary" | "secondary" | "ghost" | "outline" | "danger" | "link";
type ButtonSize = "sm" | "md" | "lg";

const BTN_BASE =
  "inline-flex items-center justify-center gap-2 font-medium rounded-md transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-canvas disabled:opacity-50 disabled:pointer-events-none whitespace-nowrap";

const BTN_VARIANT: Record<ButtonVariant, string> = {
  primary: "bg-accent text-accent-fg hover:bg-accent-hover shadow-sm",
  secondary: "bg-white text-ink border border-line hover:bg-surface-3 shadow-sm",
  ghost: "text-ink-2 hover:bg-surface-3 hover:text-ink",
  outline: "border border-line text-ink hover:bg-surface-3",
  danger: "bg-danger text-white hover:opacity-90 shadow-sm",
  link: "text-accent hover:underline px-0 h-auto",
};

const BTN_SIZE: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-[13px]",
  md: "h-10 px-4 text-sm",
  lg: "h-11 px-5 text-sm",
};

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant = "primary", size = "md", loading, children, disabled, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      className={cn(BTN_BASE, BTN_VARIANT[variant], variant !== "link" && BTN_SIZE[size], className)}
      disabled={disabled || loading}
      {...props}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  );
});

// ---------- Card ----------

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-xl border border-line bg-white shadow-card", className)} {...props} />;
}

export function CardHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex items-center justify-between gap-3 border-b border-line px-5 py-4", className)} {...props} />;
}

export function CardTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn("text-[15px] font-semibold text-ink", className)} {...props} />;
}

export function CardBody({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-5", className)} {...props} />;
}

// ---------- Inputs ----------

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(function Input(
  { className, ...props },
  ref,
) {
  return (
    <input
      ref={ref}
      className={cn(
        "h-10 w-full rounded-sm border border-line bg-white px-3 text-sm text-ink placeholder:text-ink-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:border-accent disabled:opacity-60",
        className,
      )}
      {...props}
    />
  );
});

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className, ...props }, ref) {
    return (
      <textarea
        ref={ref}
        className={cn(
          "w-full rounded-sm border border-line bg-white px-3 py-2 text-sm text-ink placeholder:text-ink-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:border-accent disabled:opacity-60",
          className,
        )}
        {...props}
      />
    );
  },
);

export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(function Select(
  { className, children, ...props },
  ref,
) {
  return (
    <select
      ref={ref}
      className={cn(
        "h-10 w-full rounded-sm border border-line bg-white px-3 text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:border-accent disabled:opacity-60",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  );
});

export function Label({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cn("mb-1.5 block text-[13px] font-medium text-ink-2", className)} {...props} />;
}

/**
 * A labelled form control.
 *
 * The label is **associated** with the control, not merely placed above it. It previously
 * rendered a bare `<label>` with no `htmlFor`, which looks identical and means a screen reader
 * announces "edit text, blank" for every field in the product — axe rated it critical on the
 * sign-in form, and the same defect was in every form because they all come through here.
 *
 * Fixed in this one place rather than by adding an `id` to a few hundred call sites: `Field`
 * generates the id, clones the child to attach it, and wires the hint and any error with
 * `aria-describedby` so both are announced with the field rather than read out separately at
 * the end of the form (WCAG 1.3.1, 3.3.1, 3.3.2).
 *
 * A child that already carries an `id` keeps it — a caller that needed a specific id had a
 * reason, and silently replacing it would break whatever pointed at it.
 */
export function Field({
  label,
  hint,
  error,
  htmlFor,
  children,
}: {
  label: string;
  hint?: string;
  /** Shown below the field and announced with it. Also marks the control `aria-invalid`. */
  error?: string;
  htmlFor?: string;
  children: React.ReactNode;
}) {
  const generatedId = React.useId();
  const child = React.isValidElement(children) ? children : null;
  const childId = (child?.props as { id?: string } | undefined)?.id;
  const fieldId = htmlFor || childId || generatedId;

  const hintId = hint ? `${fieldId}-hint` : undefined;
  const errorId = error ? `${fieldId}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;

  const control = child
    ? React.cloneElement(child, {
        id: fieldId,
        "aria-describedby":
          [(child.props as { "aria-describedby"?: string })["aria-describedby"], describedBy]
            .filter(Boolean)
            .join(" ") || undefined,
        ...(error ? { "aria-invalid": true } : {}),
      } as Record<string, unknown>)
    : children;

  return (
    <div>
      <Label htmlFor={fieldId}>{label}</Label>
      {control}
      {hint && (
        <p id={hintId} className="mt-1 text-xs text-ink-3">
          {hint}
        </p>
      )}
      {error && (
        // `role="alert"` so a validation message that appears after submit is announced,
        // rather than sitting there silently for somebody who cannot see it.
        <p id={errorId} role="alert" className="mt-1 text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

// ---------- misc ----------

export function Badge({
  className,
  tone = "neutral",
  children,
}: {
  className?: string;
  tone?: "neutral" | "accent" | "ai";
  children: React.ReactNode;
}) {
  const tones = {
    neutral: "bg-surface-3 text-ink-2",
    accent: "bg-accent-subtle text-accent",
    ai: "bg-ai-bg text-ai",
  };
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium", tones[tone], className)}>
      {children}
    </span>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("h-5 w-5 animate-spin text-ink-3", className)} />;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-surface-3", className)} />;
}

export function Avatar({ name, color, size = 28 }: { name: string; color?: string; size?: number }) {
  const init = name
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
  return (
    <span
      className="inline-flex shrink-0 items-center justify-center rounded-full font-semibold text-white"
      style={{ width: size, height: size, background: color || "#3E7BFA", fontSize: Math.max(10, size * 0.4) }}
      title={name}
    >
      {init || "?"}
    </span>
  );
}

export function ErrorBanner({ message, className }: { message: string; className?: string }) {
  if (!message) return null;
  return (
    <div className={cn("rounded-md border border-danger/30 bg-danger-bg px-3.5 py-2.5 text-sm text-danger", className)}>{message}</div>
  );
}

export function ConfidenceChip({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const cls =
    pct >= 90 ? "text-violet-700 bg-violet-50" : pct >= 60 ? "text-amber-800 bg-amber-50" : "text-red-700 bg-red-50";
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[11px] font-medium tnum", cls)}>
      <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70" />
      {pct}%
    </span>
  );
}
