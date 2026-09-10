"use client";

/**
 * Folders — the repository tree.
 *
 *   GET/POST /folders, POST /folders/{id}/move, DELETE /folders/{id}
 *
 * Paths are materialised server-side (`/Legal/Vendors/2026`), so a folder filter in search
 * means "this folder and everything beneath it". Deleting refuses while anything is filed
 * here or below — a delete must never orphan an agreement.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ChevronRight, FolderPlus, FolderTree, Lock, Move, Trash2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { PageHeader } from "@/components/shell";
import {
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
} from "@/components/ui";
import type { Folder } from "@/lib/types";

const ROLES = ["owner", "admin", "manager", "approver", "author", "viewer"];

export default function FoldersPage() {
  const { me } = useAuth();
  const role = me?.user.role;
  const canEdit = role === "owner" || role === "admin" || role === "manager";

  const [items, setItems] = useState<Folder[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [moving, setMoving] = useState<Folder | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api.get<Folder[]>("/folders").then(setItems).catch(() => setItems([]));
  }, []);
  useEffect(load, [load]);

  const total = useMemo(
    () => (items ?? []).reduce((sum, f) => sum + f.contract_count, 0),
    [items],
  );

  async function remove(folder: Folder) {
    if (!window.confirm(`Delete ${folder.path}?`)) return;
    setError("");
    try {
      await api.del(`/folders/${folder.id}`);
      load();
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "Couldn't delete that folder.");
    }
  }

  return (
    <div>
      <PageHeader
        title="Folders"
        subtitle={
          items === null
            ? "Loading…"
            : `${items.length} folder${items.length === 1 ? "" : "s"} · ${total} agreement${total === 1 ? "" : "s"} filed`
        }
        actions={
          canEdit ? (
            <Button size="sm" onClick={() => setCreating(true)}>
              <FolderPlus className="h-3.5 w-3.5" /> New folder
            </Button>
          ) : null
        }
      />

      <div className="space-y-4 p-6">
        {error && <ErrorBanner message={error} />}

        {creating && (
          <FolderForm
            folders={items ?? []}
            onCancel={() => setCreating(false)}
            onSaved={() => {
              setCreating(false);
              load();
            }}
            onError={setError}
          />
        )}

        {moving && (
          <MoveForm
            folder={moving}
            folders={items ?? []}
            onCancel={() => setMoving(null)}
            onSaved={() => {
              setMoving(null);
              load();
            }}
            onError={setError}
          />
        )}

        {items === null && <Skeleton className="h-32" />}

        {items?.length === 0 && (
          <Card>
            <CardBody className="py-10 text-center text-sm text-ink-2">
              <FolderTree className="mx-auto mb-3 h-10 w-10 text-ink-3" />
              <div className="text-base font-semibold text-ink">No folders yet</div>
              <p className="mt-1">
                Folders give the repository a shape you can filter by — and a subtree you can
                restrict to particular roles.
              </p>
            </CardBody>
          </Card>
        )}

        {items && items.length > 0 && (
          <Card>
            <CardBody className="divide-y divide-line p-0">
              {items.map((f) => (
                <div
                  key={f.id}
                  className="flex flex-wrap items-center gap-2 px-3 py-2"
                  style={{ paddingLeft: `${12 + f.depth * 20}px` }}
                >
                  {f.depth > 0 && <ChevronRight className="h-3 w-3 shrink-0 text-ink-3" />}
                  <FolderTree className="h-4 w-4 shrink-0 text-accent" />
                  <span className="text-sm text-ink">{f.name}</span>
                  <span className="text-[11px] text-ink-3">
                    {f.contract_count} agreement{f.contract_count === 1 ? "" : "s"}
                  </span>
                  {f.visible_to_roles.length > 0 && (
                    <span
                      className="inline-flex items-center gap-1 rounded-full bg-surface-3 px-2 py-0.5 text-[10px] text-ink-3"
                      title={f.visible_to_roles.join(", ")}
                    >
                      <Lock className="h-3 w-3" /> {f.visible_to_roles.join(", ")}
                    </span>
                  )}
                  <span className="ml-auto flex items-center gap-1">
                    <Link
                      href={`/search?folder=${encodeURIComponent(f.path)}`}
                      className="text-xs text-ink-3 hover:text-ink"
                    >
                      view
                    </Link>
                    {canEdit && (
                      <>
                        <button
                          onClick={() => setMoving(f)}
                          className="p-1 text-ink-3 hover:text-ink"
                          title="Move"
                        >
                          <Move className="h-3.5 w-3.5" />
                        </button>
                        <button
                          onClick={() => remove(f)}
                          className="p-1 text-ink-3 hover:text-ink"
                          title="Delete"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </>
                    )}
                  </span>
                </div>
              ))}
            </CardBody>
          </Card>
        )}
      </div>
    </div>
  );
}

function FolderForm({
  folders,
  onCancel,
  onSaved,
  onError,
}: {
  folders: Folder[];
  onCancel: () => void;
  onSaved: () => void;
  onError: (m: string) => void;
}) {
  const [name, setName] = useState("");
  const [parentId, setParentId] = useState("");
  const [roles, setRoles] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    onError("");
    try {
      await api.post("/folders", {
        name: name.trim(),
        parent_id: parentId || null,
        visible_to_roles: roles,
      });
      onSaved();
    } catch (e: unknown) {
      onError(e instanceof ApiError ? e.message : "Couldn't create that folder.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>New folder</CardTitle>
      </CardHeader>
      <CardBody>
        <form onSubmit={save} className="grid gap-3 sm:grid-cols-12">
          <div className="sm:col-span-4">
            <Field label="Name">
              <Input value={name} onChange={(e) => setName(e.target.value)} required />
            </Field>
          </div>
          <div className="sm:col-span-4">
            <Field label="Inside">
              <Select value={parentId} onChange={(e) => setParentId(e.target.value)}>
                <option value="">Top level</option>
                {folders.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.path}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <div className="sm:col-span-4">
            <Field label="Visible to" hint="Leave empty for everyone">
              <div className="flex flex-wrap gap-1.5 pt-1">
                {ROLES.map((r) => (
                  <label
                    key={r}
                    className="inline-flex items-center gap-1 rounded-md border border-line px-1.5 py-0.5 text-xs text-ink-2"
                  >
                    <input
                      type="checkbox"
                      checked={roles.includes(r)}
                      onChange={(e) =>
                        setRoles((prev) =>
                          e.target.checked ? [...prev, r] : prev.filter((x) => x !== r),
                        )
                      }
                    />
                    {r}
                  </label>
                ))}
              </div>
            </Field>
          </div>
          <div className="flex justify-end gap-2 sm:col-span-12">
            <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
              Cancel
            </Button>
            <Button type="submit" size="sm" loading={busy}>
              Create
            </Button>
          </div>
        </form>
      </CardBody>
    </Card>
  );
}

function MoveForm({
  folder,
  folders,
  onCancel,
  onSaved,
  onError,
}: {
  folder: Folder;
  folders: Folder[];
  onCancel: () => void;
  onSaved: () => void;
  onError: (m: string) => void;
}) {
  const [parentId, setParentId] = useState(folder.parent_id ?? "");
  const [busy, setBusy] = useState(false);

  // A folder cannot move into itself or its own subtree — the server refuses too, but
  // offering the option and then rejecting it is a worse experience than not offering it.
  const candidates = folders.filter(
    (f) => f.id !== folder.id && !f.path.startsWith(`${folder.path}/`),
  );

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    onError("");
    try {
      await api.post(`/folders/${folder.id}/move`, { parent_id: parentId || null });
      onSaved();
    } catch (e: unknown) {
      onError(e instanceof ApiError ? e.message : "Couldn't move that folder.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Move {folder.path}</CardTitle>
      </CardHeader>
      <CardBody>
        <form onSubmit={save} className="flex flex-wrap items-end gap-3">
          <div className="min-w-[240px] flex-1">
            <Field label="Into">
              <Select value={parentId} onChange={(e) => setParentId(e.target.value)}>
                <option value="">Top level</option>
                {candidates.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.path}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <Button type="submit" size="sm" loading={busy}>
            Move
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
            Cancel
          </Button>
        </form>
        <p className="mt-2 text-xs text-ink-3">
          Everything beneath this folder moves with it.
        </p>
      </CardBody>
    </Card>
  );
}
