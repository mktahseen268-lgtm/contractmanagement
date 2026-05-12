"use client";

import { useAuth } from "@/lib/auth";
import { PageHeader } from "@/components/shell";
import { ContractForm } from "@/components/contract-form";

export default function NewContractPage() {
  const { me } = useAuth();
  return (
    <div>
      <PageHeader title="New contract" subtitle="Fill in the basics — you can refine the document afterwards." />
      <ContractForm mode="create" currency={me?.tenant.currency} />
    </div>
  );
}
