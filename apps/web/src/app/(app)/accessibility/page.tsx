"use client";

/**
 * Accessibility statement (Phase 9, item 5).
 *
 * Written for the person who hit the barrier, not for an auditor. It states the target, names
 * the things that are known not to work yet, and gives a way to report the rest — a statement
 * that claims full conformance and offers no route to report a problem is a page nobody can
 * act on, and it is also almost always untrue.
 *
 * The working record behind this is `docs/32-accessibility.md`.
 */

import { Accessibility, Keyboard, Mail, Type, Volume2 } from "lucide-react";
import { PageHeader } from "@/components/shell";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui";

const KNOWN_ISSUES = [
  {
    title: "Videos in the help centre have no captions",
    impact: "If you are deaf or hard of hearing, a video gives you nothing.",
    workaround:
      "Every video has a written guide below it covering the same ground. Read that instead — it is not an abridged version.",
  },
  {
    title: "The document editor is only partly usable with a screen reader",
    impact:
      "The rich-text editor's toolbar can be reached, but the editing surface is not fully announced.",
    workaround:
      "Agreements can be produced from a template or from a Word document without opening the editor at all. Both routes are fully supported.",
  },
  {
    title: "Wide tables scroll sideways on a narrow screen",
    impact: "The audit log and the analytics tables need horizontal scrolling below about 320px.",
    workaround:
      "The same data is available as an export. The signing and approval screens do not have this problem — they were rebuilt for small screens.",
  },
];

export default function AccessibilityPage() {
  return (
    <div>
      <PageHeader
        title="Accessibility"
        subtitle="What we aim for, what works, and what does not work yet"
      />

      <div className="max-w-3xl space-y-4 p-6">
        <Card>
          <CardBody className="space-y-3 text-sm leading-relaxed text-ink-2">
            <p>
              This system aims to meet{" "}
              <strong className="text-ink">WCAG 2.1 level AA</strong>. We are{" "}
              <strong className="text-ink">substantially conformant</strong> — most of it meets
              that standard, and the parts that do not are listed below rather than left for you
              to discover.
            </p>
            <p>
              Signing an agreement matters more than the rest. Some people who sign here are
              customers at a branch counter, not staff, and a signing flow somebody cannot
              complete themselves produces a signature that somebody else obtained for them.
              That is why the signing screens got the most attention and are the ones we test
              most.
            </p>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>What works</CardTitle>
          </CardHeader>
          <CardBody>
            <ul className="space-y-3 text-sm text-ink-2">
              <li className="flex gap-3">
                <Keyboard className="mt-0.5 h-4 w-4 shrink-0 text-accent" aria-hidden="true" />
                <span>
                  <strong className="text-ink">Everything without a mouse.</strong> Every action
                  is reachable by keyboard, focus is always visible, and a &ldquo;skip to the
                  main content&rdquo; link is the first thing you reach on each page.
                </span>
              </li>
              <li className="flex gap-3">
                <Volume2 className="mt-0.5 h-4 w-4 shrink-0 text-accent" aria-hidden="true" />
                <span>
                  <strong className="text-ink">Screen readers.</strong> Tested with NVDA on the
                  sign-in, signing, approval and agreement screens. Status and progress are
                  announced, not just coloured.
                </span>
              </li>
              <li className="flex gap-3">
                <Type className="mt-0.5 h-4 w-4 shrink-0 text-accent" aria-hidden="true" />
                <span>
                  <strong className="text-ink">Zoom and text size.</strong> Usable at 200% zoom
                  without losing content. Assisted mode on the signing screen makes the text and
                  buttons larger again and shows one step at a time.
                </span>
              </li>
              <li className="flex gap-3">
                <Accessibility
                  className="mt-0.5 h-4 w-4 shrink-0 text-accent"
                  aria-hidden="true"
                />
                <span>
                  <strong className="text-ink">Reduced motion and touch.</strong> Animation is
                  switched off if your system asks for that, and touch targets are at least 44
                  pixels on a touch screen.
                </span>
              </li>
            </ul>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>What does not work yet</CardTitle>
          </CardHeader>
          <CardBody>
            <ul className="space-y-4">
              {KNOWN_ISSUES.map((issue) => (
                <li key={issue.title} className="border-s-2 border-amber-300 ps-3">
                  <div className="text-sm font-medium text-ink">{issue.title}</div>
                  <p className="mt-0.5 text-sm text-ink-2">{issue.impact}</p>
                  <p className="mt-1 text-sm text-ink-2">
                    <span className="font-medium text-ink">In the meantime: </span>
                    {issue.workaround}
                  </p>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5">
              <Mail className="h-4 w-4" aria-hidden="true" /> Tell us about a barrier
            </CardTitle>
          </CardHeader>
          <CardBody className="space-y-2 text-sm text-ink-2">
            <p>
              If something here stops you doing your job, or stops a customer signing, report it
              to your system administrator. Say what you were trying to do, what happened, and
              what you were using — a screen reader and its version, or the browser and whether
              you were using a keyboard only. That last part is what makes a report
              reproducible.
            </p>
            <p>
              Barriers on the signing screens are treated as faults, not enhancements. Somebody
              who cannot sign for themselves has not been served by a workaround.
            </p>
          </CardBody>
        </Card>

        <p className="text-xs text-ink-3">
          Automated accessibility checks run on every change to the signed-in application and the
          public signing portal. Automated checking finds roughly a third of accessibility
          problems, which is a useful third and not a substitute for testing with the people who
          use the system. An independent audit by a qualified tester has not yet been carried
          out.
        </p>
      </div>
    </div>
  );
}
