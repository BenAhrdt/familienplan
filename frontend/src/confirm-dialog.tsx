import React, { useState } from "react";

type ConfirmDialogProps = {
  title: string;
  message: React.ReactNode;
  confirmLabel?: string;
  danger?: boolean;
  onConfirm: () => void | Promise<void>;
  onCancel: () => void;
};

export function ConfirmDialog({
  title,
  message,
  confirmLabel = "Bestätigen",
  danger = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const [busy, setBusy] = useState(false);

  async function confirm() {
    setBusy(true);
    try {
      await onConfirm();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal confirmmodal" role="dialog" aria-modal="true" aria-labelledby="confirm-dialog-title">
      <section className="panel">
        <button type="button" className="close" onClick={onCancel} disabled={busy} aria-label="Schließen">×</button>
        <h2 id="confirm-dialog-title">{title}</h2>
        <p>{message}</p>
        <div className="modalactions">
          <button type="button" className={danger ? "danger" : undefined} onClick={() => void confirm()} disabled={busy}>
            {busy ? "Wird verarbeitet …" : confirmLabel}
          </button>
          <button type="button" className="secondary" onClick={onCancel} disabled={busy}>Abbrechen</button>
        </div>
      </section>
    </div>
  );
}
