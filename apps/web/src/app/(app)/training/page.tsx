"use client";

/**
 * Training hub (Phase 9, item 3).
 *
 *   GET  /training                                — my courses and progress
 *   GET  /training/courses/{id}                   — modules + the quiz (no answer key)
 *   POST /training/courses/{id}/modules/{index}   — mark a module read
 *   POST /training/courses/{id}/quiz              — sit the quiz
 *   GET  /training/certificate/{id}               — the PDF
 *   GET  /training/sessions                       — the webinar and onsite calendar
 *
 * MMBL scores training at 8% and wants ≥15 people trained onsite. Onsite training happens once
 * and the attendees move on; this is the half still standing in eighteen months when a new
 * joiner needs the same thing.
 */

import { useCallback, useEffect, useState } from "react";
import {
  Award,
  BookOpenCheck,
  CalendarDays,
  Check,
  ChevronLeft,
  Clock,
  GraduationCap,
  MapPin,
  X,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { PageHeader } from "@/components/shell";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  ErrorBanner,
  Skeleton,
} from "@/components/ui";

type Course = {
  id: string;
  slug: string;
  title: string;
  summary: string;
  pass_mark: number;
  estimated_minutes: number;
  certificate_valid_months: number;
  is_required: boolean;
};

type CourseDetail = Course & {
  modules: { title: string; body?: string; minutes?: number; article_slug?: string }[];
  quiz: { q: string; options: string[] }[];
};

type Progress = {
  status: string;
  completed_modules: number[];
  attempts: number;
  best_score: number;
  last_score: number;
  passed_at: string | null;
  expires_at: string | null;
  certificate_no: string;
};

type Item = {
  course: Course;
  progress: Progress | null;
  modules_total: number;
  modules_done: number;
  percent: number;
  certificate: "none" | "valid" | "expired";
};

type Hub = { items: Item[]; required_total: number; required_done: number };

type Session = {
  id: string;
  title: string;
  description: string;
  kind: string;
  starts_at: string;
  duration_minutes: number;
  location: string;
  trainer: string;
  capacity: number;
  registered_user_ids: string[];
};

type QuizResult = {
  score: number;
  passed: boolean;
  pass_mark: number;
  correct: number;
  total: number;
  certificate_no: string;
  expires_at: string | null;
  review: { index: number; question: string; why: string }[];
};

export default function TrainingPage() {
  const { t, formatDate, formatDateTime } = useI18n();
  const [hub, setHub] = useState<Hub | null>(null);
  const [sessions, setSessions] = useState<Session[] | null>(null);
  const [openId, setOpenId] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api
      .get<Hub>("/training")
      .then(setHub)
      .catch(() => setHub({ items: [], required_total: 0, required_done: 0 }));
    api
      .get<Session[]>("/training/sessions?upcoming=true")
      .then(setSessions)
      .catch(() => setSessions([]));
  }, []);
  useEffect(load, [load]);

  async function toggleSession(session: Session, joined: boolean) {
    setError("");
    try {
      if (joined) await api.del(`/training/sessions/${session.id}/register`);
      else await api.post(`/training/sessions/${session.id}/register`, {});
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "That did not work.");
    }
  }

  if (openId) {
    return (
      <CourseView
        courseId={openId}
        onBack={() => {
          setOpenId("");
          load();
        }}
      />
    );
  }

  return (
    <div>
      <PageHeader
        title={t("training.hub")}
        subtitle="Learn the process, prove you have, and keep it current"
      />

      <div className="space-y-4 p-6">
        {error && <ErrorBanner message={error} />}

        {hub === null ? (
          <Skeleton className="h-32" />
        ) : (
          <>
            {hub.required_total > 0 && (
              <Card>
                <CardBody className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-ink">
                      Required training: {hub.required_done} of {hub.required_total} current
                    </div>
                    <p className="text-xs text-ink-2">
                      A certificate that has lapsed does not count. It stops being evidence of
                      training on the current process the day it expires.
                    </p>
                  </div>
                  <div
                    className="h-2 w-40 overflow-hidden rounded-full bg-surface-3"
                    role="progressbar"
                    aria-valuenow={hub.required_done}
                    aria-valuemin={0}
                    aria-valuemax={hub.required_total}
                    aria-label="Required training completed"
                  >
                    <div
                      className="h-full bg-accent transition-all"
                      style={{
                        width: `${hub.required_total ? (hub.required_done / hub.required_total) * 100 : 0}%`,
                      }}
                    />
                  </div>
                </CardBody>
              </Card>
            )}

            {hub.items.length === 0 ? (
              <Card>
                <CardBody className="py-10 text-center text-sm text-ink-2">
                  <GraduationCap className="mx-auto mb-3 h-9 w-9 text-ink-3" aria-hidden="true" />
                  <div className="text-base font-semibold text-ink">No courses yet</div>
                  <p className="mt-1">Somebody with content permissions can add one.</p>
                </CardBody>
              </Card>
            ) : (
              <ul className="grid gap-3 lg:grid-cols-2">
                {hub.items.map((item) => (
                  <li key={item.course.id}>
                    <Card className="h-full">
                      <CardBody className="flex h-full flex-col gap-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-semibold text-ink">
                            {item.course.title}
                          </span>
                          {item.course.is_required && (
                            <Badge tone="accent">{t("training.required")}</Badge>
                          )}
                          {item.certificate === "valid" && (
                            <Badge tone="neutral">
                              <Award className="h-3 w-3" aria-hidden="true" />{" "}
                              {t("training.certificate")}
                            </Badge>
                          )}
                          {item.certificate === "expired" && (
                            <span className="text-[11px] font-medium text-amber-700">
                              {t("training.expired")}
                            </span>
                          )}
                        </div>

                        {item.course.summary && (
                          <p className="text-xs text-ink-2">{item.course.summary}</p>
                        )}

                        <div className="flex flex-wrap items-center gap-3 text-[11px] text-ink-3">
                          <span className="inline-flex items-center gap-1">
                            <Clock className="h-3 w-3" aria-hidden="true" />
                            about {item.course.estimated_minutes} min
                          </span>
                          <span>
                            {t("training.pass_mark")} {item.course.pass_mark}%
                          </span>
                          {item.progress?.expires_at && item.certificate === "valid" && (
                            <span>
                              {t("training.valid_until")} {formatDate(item.progress.expires_at)}
                            </span>
                          )}
                        </div>

                        <div
                          className="h-1.5 overflow-hidden rounded-full bg-surface-3"
                          role="progressbar"
                          aria-valuenow={item.percent}
                          aria-valuemin={0}
                          aria-valuemax={100}
                          aria-label={`${item.course.title} progress`}
                        >
                          <div className="h-full bg-accent" style={{ width: `${item.percent}%` }} />
                        </div>
                        <span className="text-[11px] text-ink-3">
                          {item.modules_done} of {item.modules_total} sections read
                        </span>

                        <div className="mt-auto flex flex-wrap gap-2 pt-2">
                          <Button size="sm" onClick={() => setOpenId(item.course.id)}>
                            <BookOpenCheck className="h-3.5 w-3.5" aria-hidden="true" />
                            {item.certificate === "valid"
                              ? t("training.retake")
                              : item.modules_done
                                ? t("training.resume")
                                : t("training.start")}
                          </Button>
                          {item.certificate === "valid" && (
                            <a
                              href={`/api/training/certificate/${item.course.id}`}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 rounded-md px-3 py-1.5 text-xs font-medium text-accent underline underline-offset-2"
                            >
                              <Award className="h-3.5 w-3.5" aria-hidden="true" />
                              {t("training.certificate")}
                            </a>
                          )}
                        </div>
                      </CardBody>
                    </Card>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5">
              <CalendarDays className="h-4 w-4" aria-hidden="true" /> Sessions coming up
            </CardTitle>
          </CardHeader>
          <CardBody>
            {sessions === null ? (
              <Skeleton className="h-16" />
            ) : sessions.length === 0 ? (
              <p className="text-sm text-ink-2">
                Nothing scheduled. Onsite sessions are recorded here too, so the attendance
                record and the calendar stay the same list.
              </p>
            ) : (
              <ul className="divide-y divide-line">
                {sessions.map((s) => {
                  const joined = s.registered_user_ids.length > 0;
                  return (
                    <li key={s.id} className="flex flex-wrap items-center gap-3 py-2.5">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-medium text-ink">{s.title}</span>
                          <Badge tone="neutral">{s.kind.replace("_", " ")}</Badge>
                        </div>
                        <div className="flex flex-wrap items-center gap-3 text-[11px] text-ink-3">
                          <span>{formatDateTime(s.starts_at)}</span>
                          <span>{s.duration_minutes} min</span>
                          {s.location && (
                            <span className="inline-flex items-center gap-1">
                              <MapPin className="h-3 w-3" aria-hidden="true" /> {s.location}
                            </span>
                          )}
                          {s.trainer && <span>with {s.trainer}</span>}
                        </div>
                      </div>
                      <Button
                        size="sm"
                        variant={joined ? "ghost" : "primary"}
                        onClick={() => toggleSession(s, joined)}
                      >
                        {joined ? (
                          <>
                            <X className="h-3.5 w-3.5" aria-hidden="true" /> Leave
                          </>
                        ) : (
                          <>
                            <Check className="h-3.5 w-3.5" aria-hidden="true" /> Join
                          </>
                        )}
                      </Button>
                    </li>
                  );
                })}
              </ul>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

function CourseView({ courseId, onBack }: { courseId: string; onBack: () => void }) {
  const { t } = useI18n();
  const [course, setCourse] = useState<CourseDetail | null>(null);
  const [done, setDone] = useState<number[]>([]);
  const [answers, setAnswers] = useState<Record<number, number>>({});
  const [result, setResult] = useState<QuizResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get<CourseDetail>(`/training/courses/${courseId}`)
      .then(setCourse)
      .catch(() => setError("That course could not be opened."));
    api
      .get<Hub>("/training")
      .then((h) => {
        const mine = h.items.find((i) => i.course.id === courseId);
        setDone(mine?.progress?.completed_modules ?? []);
      })
      .catch(() => setDone([]));
  }, [courseId]);

  async function markRead(index: number) {
    if (done.includes(index)) return;
    setDone((d) => [...d, index]);
    try {
      await api.post(`/training/courses/${courseId}/modules/${index}`, {});
    } catch {
      // Reading progress is a convenience. Losing one tick is not worth an error banner in
      // front of somebody who is part-way through a course.
    }
  }

  async function submit() {
    if (!course) return;
    setBusy(true);
    setError("");
    try {
      const ordered = course.quiz.map((_, i) => answers[i] ?? -1);
      setResult(
        await api.post<QuizResult>(`/training/courses/${courseId}/quiz`, { answers: ordered }),
      );
      window.scrollTo({ top: 0 });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "That could not be submitted.");
    } finally {
      setBusy(false);
    }
  }

  if (!course) return <Skeleton className="m-6 h-40" />;

  const allAnswered = course.quiz.every((_, i) => answers[i] !== undefined);

  return (
    <div>
      <PageHeader
        title={course.title}
        subtitle={course.summary}
        actions={
          <Button size="sm" variant="ghost" onClick={onBack}>
            <ChevronLeft className="h-3.5 w-3.5 rtl:rotate-180" aria-hidden="true" />{" "}
            {t("action.back")}
          </Button>
        }
      />

      <div className="max-w-3xl space-y-4 p-6">
        {error && <ErrorBanner message={error} />}

        {result && (
          <Card className={result.passed ? "border-emerald-300" : "border-amber-300"}>
            <CardBody className="space-y-2">
              <div className="text-base font-semibold text-ink">
                {result.passed
                  ? `Passed — ${result.score}%`
                  : `Not this time — ${result.score}% (${result.pass_mark}% needed)`}
              </div>
              <p className="text-sm text-ink-2">
                {result.correct} of {result.total} correct.
                {result.passed && result.certificate_no
                  ? ` Certificate ${result.certificate_no} issued.`
                  : ""}
              </p>
              {result.review.length > 0 && (
                <div className="space-y-2 pt-1">
                  <div className="text-xs font-semibold text-ink">Worth going back over</div>
                  {result.review.map((r) => (
                    <div key={r.index} className="rounded border border-line bg-surface-2 p-2">
                      <div className="text-xs font-medium text-ink">{r.question}</div>
                      {r.why && <p className="mt-0.5 text-xs text-ink-2">{r.why}</p>}
                    </div>
                  ))}
                </div>
              )}
              <div className="flex gap-2 pt-1">
                {result.passed && (
                  <a
                    href={`/api/training/certificate/${courseId}`}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-sm font-medium text-accent underline underline-offset-2"
                  >
                    <Award className="h-4 w-4" aria-hidden="true" /> {t("training.certificate")}
                  </a>
                )}
                {!result.passed && (
                  <Button
                    size="sm"
                    onClick={() => {
                      setResult(null);
                      setAnswers({});
                    }}
                  >
                    {t("training.retake")}
                  </Button>
                )}
              </div>
            </CardBody>
          </Card>
        )}

        {!result && (
          <>
            {course.modules.map((m, i) => (
              <Card key={i}>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    {done.includes(i) && (
                      <Check className="h-4 w-4 text-accent" aria-label="Read" />
                    )}
                    {m.title}
                  </CardTitle>
                </CardHeader>
                <CardBody className="space-y-3">
                  {(m.body || "").split(/\n{2,}/).map((para, pi) => (
                    <p key={pi} className="text-sm leading-relaxed text-ink-2">
                      {para}
                    </p>
                  ))}
                  {!done.includes(i) && (
                    <Button size="sm" variant="ghost" onClick={() => markRead(i)}>
                      Mark as read
                    </Button>
                  )}
                </CardBody>
              </Card>
            ))}

            {course.quiz.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>Check your understanding</CardTitle>
                </CardHeader>
                <CardBody className="space-y-4">
                  {course.quiz.map((q, qi) => (
                    <fieldset key={qi} className="space-y-1.5">
                      <legend className="mb-1 text-sm font-medium text-ink">
                        {qi + 1}. {q.q}
                      </legend>
                      {q.options.map((option, oi) => (
                        <label
                          key={oi}
                          className="flex cursor-pointer items-start gap-2 rounded border border-line p-2 text-sm text-ink-2 hover:bg-surface-2 has-[:checked]:border-accent has-[:checked]:bg-accent-subtle"
                        >
                          <input
                            type="radio"
                            name={`q-${qi}`}
                            className="mt-0.5"
                            checked={answers[qi] === oi}
                            onChange={() => setAnswers((a) => ({ ...a, [qi]: oi }))}
                          />
                          <span>{option}</span>
                        </label>
                      ))}
                    </fieldset>
                  ))}
                  <div className="flex items-center gap-3">
                    <Button onClick={submit} loading={busy} disabled={!allAnswered}>
                      Submit
                    </Button>
                    {!allAnswered && (
                      <span className="text-xs text-ink-3">
                        Answer every question before submitting.
                      </span>
                    )}
                  </div>
                </CardBody>
              </Card>
            )}
          </>
        )}
      </div>
    </div>
  );
}
