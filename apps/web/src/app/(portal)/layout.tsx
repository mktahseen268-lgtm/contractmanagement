export default function PortalLayout({ children }: { children: React.ReactNode }) {
  // Standalone surface for external signers — no app shell, no auth guard.
  return <div className="min-h-screen bg-canvas">{children}</div>;
}
