const LABELS: Record<string, string> = {
  uploaded: "Uploaded",
  processing: "Processing",
  ready: "Ready for review",
  approved: "Approved",
  failed: "Failed",
};

export function StatusChip({ status }: { status: string }) {
  return (
    <span className={`chip chip-${status}`}>{LABELS[status] ?? status}</span>
  );
}
