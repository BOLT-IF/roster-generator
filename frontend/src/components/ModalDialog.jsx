import { useEffect, useRef } from "react";

// Native <dialog> wrapper: showModal() gives top-layer rendering, focus
// containment, Esc dismissal, ::backdrop, and focus return to the invoker
// without any hand-rolled focus-trap code. The dialog stays in the DOM (the
// UA hides closed dialogs); React state drives open/close through the effect.
//
// Styling notes (modern-web-guidance: ui-components/dialog):
// - overscroll-contain on the dialog and its ::backdrop stops scroll
//   gestures inside the dialog from chaining to the page behind it.
// - Do NOT add role="dialog"/aria-modal or a focus trap: the native modal
//   already provides them.
export default function ModalDialog({ open, onClose, labelledBy, className = "", children }) {
  const dialogRef = useRef(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  return (
    <dialog
      ref={dialogRef}
      onClose={onClose}
      aria-labelledby={labelledBy}
      className={`w-[calc(100vw-2rem)] rounded-2xl border border-gray-200 bg-white p-5 text-left shadow-xl overscroll-contain [&::backdrop]:overflow-hidden [&::backdrop]:overscroll-contain [&::backdrop]:bg-slate-950/40 ${className}`}
    >
      {/* Children render only while open: closed-dialog content stays out of
          the DOM so it can never reference missing data or collide with
          page-level getByLabel/strict-mode lookups. */}
      {open ? children : null}
    </dialog>
  );
}
