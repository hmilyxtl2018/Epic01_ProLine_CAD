import clsx from "clsx";

export function StatusBadge({ status }: { status: string }) {
  const cls = (() => {
    switch (status) {
      case "SUCCESS":
        return "bg-status-success/15 text-status-success ring-status-success/30";
      case "SUCCESS_WITH_WARNINGS":
        return "bg-status-warn/15 text-status-warn ring-status-warn/30";
      case "ERROR":
        return "bg-status-error/15 text-status-error ring-status-error/30";
      case "RUNNING":
        return "bg-status-running/15 text-status-running ring-status-running/30";
      default:
        return "bg-status-pending/15 text-status-pending ring-status-pending/30";
    }
  })();
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ring-1",
        cls,
      )}
    >
      {status}
    </span>
  );
}
