import { useEffect, useId, useRef, useState } from "react";
import { CheckIcon, ChevronDownIcon } from "./Icons";

export interface SortOption {
  value: string;
  label: string;
}

interface SortListboxProps {
  label: string;
  value: string;
  options: SortOption[];
  onChange: (value: string) => void;
}

export function SortListbox({ label, value, options, onChange }: SortListboxProps) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(
    Math.max(0, options.findIndex((o) => o.value === value))
  );
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const listboxId = useId();

  const selected = options.find((o) => o.value === value) ?? options[0];

  useEffect(() => {
    const onPointerDown = (ev: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(ev.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, []);

  const commit = (idx: number) => {
    const opt = options[idx];
    if (opt) {
      onChange(opt.value);
      setActiveIndex(idx);
    }
    setOpen(false);
    triggerRef.current?.focus();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!open) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp" || e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        setOpen(true);
        setActiveIndex(Math.max(0, options.findIndex((o) => o.value === value)));
      }
      return;
    }

    if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
      triggerRef.current?.focus();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((prev) => (prev + 1) % options.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((prev) => (prev - 1 + options.length) % options.length);
    } else if (e.key === "Home") {
      e.preventDefault();
      setActiveIndex(0);
    } else if (e.key === "End") {
      e.preventDefault();
      setActiveIndex(options.length - 1);
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      commit(activeIndex);
    }
  };

  return (
    <div className="listbox-wrap" ref={wrapRef} onKeyDown={handleKeyDown}>
      <button
        ref={triggerRef}
        type="button"
        className="listbox-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listboxId}
        aria-label={`${label}: ${selected.label}`}
        onClick={() => setOpen((prev) => !prev)}
      >
        <span>{selected.label}</span>
        <ChevronDownIcon />
      </button>

      {open && (
        <ul
          id={listboxId}
          role="listbox"
          aria-label={label}
          className="listbox-menu"
          tabIndex={-1}
        >
          {options.map((opt, idx) => {
            const isSelected = opt.value === value;
            return (
              <li
                key={opt.value}
                role="option"
                aria-selected={isSelected}
                data-active={idx === activeIndex ? "true" : "false"}
                className="listbox-option"
                onMouseEnter={() => setActiveIndex(idx)}
                onClick={() => commit(idx)}
              >
                <span>{opt.label}</span>
                {isSelected && <CheckIcon />}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
