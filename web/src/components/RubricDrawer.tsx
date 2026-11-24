import { useEffect } from "react";
import type { RubricCheckMeta, RubricConfig } from "../types";
import { CloseIcon } from "./Icons";

interface RubricDrawerProps {
  open: boolean;
  rubric: RubricConfig;
  defaultRubric: RubricConfig;
  checks: RubricCheckMeta[];
  onChange: (next: RubricConfig) => void;
  onClose: () => void;
}

export function RubricDrawer({
  open,
  rubric,
  defaultRubric,
  checks,
  onChange,
  onClose,
}: RubricDrawerProps) {
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const mandatoryTotal = Object.entries(rubric.weights)
    .filter(([key]) => key !== "opt_dns")
    .reduce((sum, [, val]) => sum + val, 0);

  return (
    <div
      className="drawer-backdrop"
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <aside
        className="drawer-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="rubric-drawer-title"
      >
        <div className="drawer-header">
          <div>
            <h2 id="rubric-drawer-title" className="inspector-title">
              Konfigurasi Rubrik Penilaian
            </h2>
            <p className="metric-label">
              Bobot wajib: {mandatoryTotal.toFixed(1)} poin (nilai akhir maksimum tetap 100%)
            </p>
          </div>
          <button
            type="button"
            className="btn btn-ghost btn-icon"
            aria-label="Tutup pengaturan rubrik"
            onClick={onClose}
          >
            <CloseIcon size={16} />
          </button>
        </div>

        <div className="drawer-body">
          <div className="field-group">
            <label htmlFor="pass-threshold-input" className="field-label">
              Ambang batas lulus (%)
            </label>
            <input
              id="pass-threshold-input"
              type="number"
              min={0}
              max={100}
              step={1}
              className="text-input mono"
              value={rubric.pass_threshold}
              onChange={(e) =>
                onChange({
                  ...rubric,
                  pass_threshold: Math.max(0, Math.min(100, Number(e.target.value) || 0)),
                })
              }
            />
          </div>

          <label className="toggle-row">
            <div>
              <p className="field-label">Wajib explicit allowed VLAN pada trunk</p>
              <p className="metric-label">Jika nonaktif, trunk tanpa perintah allowed tetap dinilai penuh.</p>
            </div>
            <input
              type="checkbox"
              checked={rubric.require_explicit_trunk_allowed}
              onChange={(e) =>
                onChange({
                  ...rubric,
                  require_explicit_trunk_allowed: e.target.checked,
                })
              }
            />
          </label>

          <label className="toggle-row">
            <div>
              <p className="field-label">Terima static route berbasis exit-interface</p>
              <p className="metric-label">Jika nonaktif, hanya next-hop IP yang memperoleh poin penuh.</p>
            </div>
            <input
              type="checkbox"
              checked={rubric.allow_exit_interface_route}
              onChange={(e) =>
                onChange({
                  ...rubric,
                  allow_exit_interface_route: e.target.checked,
                })
              }
            />
          </label>

          <div className="field-group">
            <p className="field-label">Bobot per item evaluasi</p>
            <div>
              {checks.map((item) => (
                <div key={item.id} className="weight-row">
                  <div>
                    <p className="check-title">{item.label}</p>
                    <p className="metric-label">
                      {item.device} · {item.category}
                    </p>
                  </div>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    step={0.5}
                    aria-label={`Bobot ${item.label}`}
                    className="text-input mono"
                    value={rubric.weights[item.id] ?? 0}
                    onChange={(e) =>
                      onChange({
                        ...rubric,
                        weights: {
                          ...rubric.weights,
                          [item.id]: Math.max(0, Number(e.target.value) || 0),
                        },
                      })
                    }
                  />
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="drawer-footer">
          <button
            type="button"
            className="btn btn-destructive"
            onClick={() => onChange(structuredClone(defaultRubric))}
          >
            Reset default
          </button>
          <button type="button" className="btn btn-primary" onClick={onClose}>
            Simpan &amp; tutup
          </button>
        </div>
      </aside>
    </div>
  );
}
