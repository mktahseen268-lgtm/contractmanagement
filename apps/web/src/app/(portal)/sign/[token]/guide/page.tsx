"use client";

/**
 * Printable step-by-step signing guide (Phase 9, item 7).
 *
 * For the customer who is not comfortable online, and for the branch staff member helping them.
 * Printed and handed over, or read on screen.
 *
 * Public, like the signing portal itself — it is reached from a signing link and needs no
 * account. It shows **no contract content**: the guide explains the process, and a printed page
 * that carried the agreement's terms would be a copy of a confidential document lying on a
 * branch counter.
 */

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Printer } from "lucide-react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { LocaleSwitch } from "@/components/locale-switch";

type Info = { valid: boolean; org_name?: string; contract_title?: string };

const STEPS_EN = [
  {
    title: "Open the agreement",
    body: "Press “Read the agreement”. It opens in a new tab. Read all of it. If anything is unclear, ask the branch staff member before you go on — that is what they are there for.",
  },
  {
    title: "Check the details",
    body: "Make sure your name is spelled correctly, and that the dates and amounts are what you were told. If any of it is wrong, stop and say so. It is far easier to correct now than after signing.",
  },
  {
    title: "Agree to sign electronically",
    body: "Tick the box that says you agree to use electronic records and signatures. An electronic signature has the same standing as one on paper.",
  },
  {
    title: "Type your full name",
    body: "Type your full legal name — the one on your CNIC. This becomes your signature on the document.",
  },
  {
    title: "Add your signature",
    body: "Choose “Type” to use your typed name, or “Draw” to sign with your finger on the screen. Either is valid. Draw is often easier on a tablet.",
  },
  {
    title: "Press “I agree & sign”",
    body: "Nothing is signed until you press this. Once you do, the agreement records your signature, the time, and that it was you.",
  },
  {
    title: "Keep your copy",
    body: "A copy is emailed to you. If you do not have an email address, ask for a printed copy before you leave the branch. Do not leave without a copy.",
  },
];

const STEPS_UR = [
  {
    title: "معاہدہ کھولیں",
    body: "«معاہدہ پڑھیں» دبائیں۔ یہ نئے صفحے میں کھلے گا۔ پورا پڑھیں۔ اگر کوئی بات سمجھ نہ آئے تو آگے بڑھنے سے پہلے برانچ کے عملے سے پوچھیں — وہ اسی لیے موجود ہیں۔",
  },
  {
    title: "تفصیلات جانچیں",
    body: "دیکھیں کہ آپ کا نام درست لکھا ہے، اور تاریخیں اور رقم وہی ہیں جو آپ کو بتائی گئیں۔ اگر کچھ غلط ہے تو رک جائیں اور بتائیں۔ دستخط کے بعد درست کرنا بہت مشکل ہے۔",
  },
  {
    title: "برقی دستخط کی اجازت دیں",
    body: "اس خانے پر نشان لگائیں جس میں لکھا ہے کہ آپ برقی ریکارڈ اور دستخط کے استعمال پر رضامند ہیں۔ برقی دستخط کاغذ پر دستخط کے برابر ہے۔",
  },
  {
    title: "اپنا پورا نام لکھیں",
    body: "اپنا پورا قانونی نام لکھیں — وہی جو آپ کے شناختی کارڈ پر ہے۔ یہی دستاویز پر آپ کا دستخط بنے گا۔",
  },
  {
    title: "اپنا دستخط بنائیں",
    body: "«ٹائپ» چنیں تاکہ آپ کا لکھا نام استعمال ہو، یا «ڈرا» چنیں اور اسکرین پر انگلی سے دستخط کریں۔ دونوں درست ہیں۔ ٹیبلٹ پر ڈرا کرنا اکثر آسان رہتا ہے۔",
  },
  {
    title: "«میں متفق ہوں اور دستخط کرتا ہوں» دبائیں",
    body: "جب تک آپ یہ نہ دبائیں، کچھ بھی دستخط نہیں ہوتا۔ دبانے کے بعد آپ کا دستخط، وقت اور شناخت ریکارڈ ہو جاتی ہے۔",
  },
  {
    title: "اپنی نقل رکھیں",
    body: "ایک نقل آپ کو ای میل کر دی جائے گی۔ اگر آپ کے پاس ای میل نہیں ہے تو برانچ سے نکلنے سے پہلے پرنٹ شدہ نقل طلب کریں۔ نقل کے بغیر نہ جائیں۔",
  },
];

export default function SigningGuidePage() {
  const { token } = useParams<{ token: string }>();
  const { locale, t } = useI18n();
  const [info, setInfo] = useState<Info | null>(null);

  useEffect(() => {
    // The same view call the portal makes. If the link is dead the guide says so rather than
    // printing instructions for something nobody can sign.
    api
      .post<Info>(`/sign/${token}/view`)
      .then(setInfo)
      .catch(() => setInfo({ valid: false }));
  }, [token]);

  const steps = locale === "ur" ? STEPS_UR : STEPS_EN;

  return (
    <div className="mx-auto max-w-2xl px-6 py-8 print:max-w-none print:px-0 print:py-0">
      {/* Hidden when printed: controls are not part of the handout. */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3 print:hidden">
        <LocaleSwitch />
        <button
          type="button"
          onClick={() => window.print()}
          className="inline-flex h-11 items-center gap-2 rounded-md bg-accent px-4 text-base font-medium text-white"
        >
          <Printer className="h-4 w-4" aria-hidden="true" /> {t("action.print")}
        </button>
      </div>

      <h1 className="text-2xl font-bold text-ink">How to sign this agreement</h1>
      {info?.org_name && (
        <p className="mt-1 text-base text-ink-2">
          Sent by {info.org_name}
          {info.contract_title ? ` · ${info.contract_title}` : ""}
        </p>
      )}

      {info && !info.valid && (
        <p className="mt-4 rounded-md border border-amber-300 bg-amber-50 p-3 text-base text-amber-900">
          This signing link is no longer active. Ask the person who sent it for a new one before
          following these steps.
        </p>
      )}

      <ol className="mt-6 space-y-5">
        {steps.map((s, i) => (
          <li key={i} className="flex gap-4 break-inside-avoid">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-accent text-lg font-bold text-white print:border print:border-black print:bg-white print:text-black">
              {i + 1}
            </span>
            <div>
              <div className="text-lg font-semibold text-ink">{s.title}</div>
              <p className="mt-0.5 text-base leading-relaxed text-ink-2">{s.body}</p>
            </div>
          </li>
        ))}
      </ol>

      <div className="mt-8 rounded-lg border-2 border-ink p-4 print:border-black">
        <div className="text-lg font-semibold text-ink">If you are not sure, do not sign</div>
        <p className="mt-1 text-base text-ink-2">
          You can stop at any point. Nothing is recorded until you press the sign button. Ask the
          branch staff member to explain anything you do not understand, and take the guide home
          to read if you would rather decide later.
        </p>
      </div>

      <p className="mt-6 text-sm text-ink-3">
        Staff: do not sign on the customer&rsquo;s behalf, do not enter the code sent to their
        phone, and do not skip the reading step to save time. The record shows what was displayed
        and for how long.
      </p>
    </div>
  );
}
