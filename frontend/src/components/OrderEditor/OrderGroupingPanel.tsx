import { useEffect, useMemo, useState } from "react";

import { Field } from "../Field";
import type { Translate } from "../../i18n";

type GroupablePart = {
  id: string;
  filename: string;
  orderId: string;
  orderName: string;
  priority: string;
  enabled: boolean;
  hasGeometry: boolean;
};

type OrderGroupingPanelProps = {
  parts: GroupablePart[];
  onPartChange: (partId: string, patch: Partial<Pick<GroupablePart, "orderId" | "orderName" | "priority">>) => void;
  t: Translate;
};

const inputClassName =
  "w-full rounded-2xl border border-[color:var(--border)] bg-black/20 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-accent";

export function OrderGroupingPanel({ parts, onPartChange, t }: OrderGroupingPanelProps) {
  const eligibleParts = useMemo(() => parts.filter((part) => part.enabled && part.hasGeometry), [parts]);
  const eligibleIds = useMemo(() => new Set(eligibleParts.map((part) => part.id)), [eligibleParts]);
  const [selectedPartIds, setSelectedPartIds] = useState<string[]>([]);
  const [draftOrderId, setDraftOrderId] = useState("");
  const [draftOrderName, setDraftOrderName] = useState("");
  const [draftPriority, setDraftPriority] = useState("");

  useEffect(() => {
    setSelectedPartIds((current) => {
      const next = current.filter((partId) => eligibleIds.has(partId));
      if (next.length > 0) return next;
      return eligibleParts.map((part) => part.id);
    });
  }, [eligibleIds, eligibleParts]);

  const selectedCount = selectedPartIds.length;
  const canApply = selectedCount > 0 && (draftOrderId.trim() || draftOrderName.trim() || draftPriority.trim());

  const togglePartSelection = (partId: string, checked: boolean) => {
    setSelectedPartIds((current) => {
      if (checked) return current.includes(partId) ? current : [...current, partId];
      return current.filter((item) => item !== partId);
    });
  };

  const applyGrouping = () => {
    for (const partId of selectedPartIds) {
      onPartChange(partId, {
        orderId: draftOrderId,
        orderName: draftOrderName,
        priority: draftPriority,
      });
    }
  };

  return (
    <div className="rounded-[1.5rem] border border-[color:var(--border)] bg-black/15 px-4 py-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-slate-100">{t("orderEditor.title")}</div>
          <div className="mt-1 text-xs text-slate-500">{t("orderEditor.subtitle")}</div>
        </div>
        <div className="text-xs uppercase tracking-[0.16em] text-slate-500">
          {t("orderEditor.eligibleCount", { count: eligibleParts.length })}
        </div>
      </div>

      {eligibleParts.length === 0 ? (
        <div className="rounded-2xl border border-[color:var(--border)] bg-white/[0.03] px-4 py-3 text-sm text-slate-400">
          {t("orderEditor.noParts")}
        </div>
      ) : (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <button
              className="rounded-full border border-[color:var(--border)] px-3 py-1 text-xs font-semibold text-slate-200 hover:border-accent"
              onClick={() => setSelectedPartIds(eligibleParts.map((part) => part.id))}
              type="button"
            >
              {t("orderEditor.selectAll")}
            </button>
            <button
              className="rounded-full border border-[color:var(--border)] px-3 py-1 text-xs font-semibold text-slate-200 hover:border-accent"
              onClick={() => setSelectedPartIds([])}
              type="button"
            >
              {t("orderEditor.clearSelection")}
            </button>
            <div className="text-xs text-slate-500">
              {selectedCount > 0
                ? t("orderEditor.selectedCount", { count: selectedCount })
                : t("orderEditor.selectedNone")}
            </div>
          </div>

          <div className="mb-4 grid gap-2 md:grid-cols-2">
            {eligibleParts.map((part) => (
              <label
                key={part.id}
                className="flex items-center gap-3 rounded-2xl border border-[color:var(--border)] bg-white/[0.03] px-3 py-3 text-sm text-slate-300"
              >
                <input
                  checked={selectedPartIds.includes(part.id)}
                  onChange={(event) => togglePartSelection(part.id, event.target.checked)}
                  type="checkbox"
                />
                <span className="min-w-0">
                  <span className="block truncate font-semibold text-slate-100">{part.filename}</span>
                  <span className="block text-xs text-slate-500">
                    {part.orderName || part.orderId || t("common.notSet")}
                  </span>
                </span>
              </label>
            ))}
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            <Field label={t("orderEditor.orderId")}>
              <input
                className={inputClassName}
                onChange={(event) => setDraftOrderId(event.target.value)}
                type="text"
                value={draftOrderId}
              />
            </Field>
            <Field label={t("orderEditor.orderName")}>
              <input
                className={inputClassName}
                onChange={(event) => setDraftOrderName(event.target.value)}
                type="text"
                value={draftOrderName}
              />
            </Field>
            <Field label={t("orderEditor.priority")}>
              <input
                className={inputClassName}
                min="1"
                onChange={(event) => setDraftPriority(event.target.value)}
                type="number"
                value={draftPriority}
              />
            </Field>
          </div>

          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            <div className="text-xs text-slate-500">{t("orderEditor.actionHint")}</div>
            <button
              className="rounded-2xl bg-[linear-gradient(135deg,var(--brand-primary)_0%,#059669_100%)] px-4 py-3 text-sm font-semibold text-white shadow-[0_14px_28px_rgba(16,185,129,0.22)] transition hover:brightness-110 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:shadow-none"
              disabled={!canApply}
              onClick={applyGrouping}
              type="button"
            >
              {t("orderEditor.apply")}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
