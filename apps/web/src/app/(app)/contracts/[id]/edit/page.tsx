"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/shell";
import { ContractForm } from "@/components/contract-form";
import { Card, CardBody, Skeleton } from "@/components/ui";
import type { ContractDetail } from "@/lib/types";

export default function EditContractPage() {
  const { id } = useParams<{ id: string }>();
  const [contract, setContract] = useState<ContractDetail | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get<ContractDetail>(`/contracts/${id}`).then(setContract).catch((e) => setError(e.message));
  }, [id]);

  return (
    <div>
      <PageHeader title="Edit contract" subtitle={contract ? `${contract.reference_no} · ${contract.title}` : "…"} />
      {error && (
        <div className="p-6">
          <Card>
            <CardBody className="text-sm text-danger">{error}</CardBody>
          </Card>
        </div>
      )}
      {!contract && !error ? (
        <div className="mx-auto max-w-3xl p-6">
          <Skeleton className="h-96 rounded-xl" />
        </div>
      ) : contract ? (
        <ContractForm mode="edit" contractId={contract.id} initial={contract} />
      ) : null}
    </div>
  );
}
