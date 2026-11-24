interface IconProps {
  size?: number;
}

export function NetworkMarkIcon({ size = 16 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <rect x="2.5" y="2.5" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.5" />
      <rect x="12.5" y="2.5" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.5" />
      <rect x="7.5" y="12.5" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.5" />
      <path d="M5 7.5V10H15V7.5M10 10V12.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

export function UploadIcon({ size = 20 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M10 13V4M10 4L6.5 7.5M10 4L13.5 7.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M3.5 13.5V15.5C3.5 16.05 3.95 16.5 4.5 16.5H15.5C16.05 16.5 16.5 16.05 16.5 15.5V13.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

export function DownloadIcon({ size = 16 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M10 3.5V12.5M10 12.5L6.5 9M10 12.5L13.5 9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M3.5 14.5V16C3.5 16.28 3.72 16.5 4 16.5H16C16.28 16.5 16.5 16.28 16.5 16V14.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

export function SlidersIcon({ size = 16 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M3 5.5H17M3 10H17M3 14.5H17" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <circle cx="7" cy="5.5" r="2" fill="var(--bg-surface)" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="13" cy="10" r="2" fill="var(--bg-surface)" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="9" cy="14.5" r="2" fill="var(--bg-surface)" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

export function SunIcon({ size = 16 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="10" cy="10" r="3.5" stroke="currentColor" strokeWidth="1.5" />
      <path d="M10 2.5V4.2M10 15.8V17.5M2.5 10H4.2M15.8 10H17.5M4.7 4.7L5.9 5.9M14.1 14.1L15.3 15.3M15.3 4.7L14.1 5.9M5.9 14.1L4.7 15.3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

export function MoonIcon({ size = 16 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M15.8 12.2A6.2 6.2 0 0 1 7.8 4.2a6.4 6.4 0 1 0 8 8Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

export function SearchIcon({ size = 16 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="9" cy="9" r="5.5" stroke="currentColor" strokeWidth="1.5" />
      <path d="M13.2 13.2L17 17" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

export function CheckIcon({ size = 14 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M3.5 8.5L6.5 11.5L12.5 4.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function MinusCircleIcon({ size = 14 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.4" />
      <path d="M5.2 8H10.8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

export function CloseIcon({ size = 14 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M4.5 4.5L11.5 11.5M11.5 4.5L4.5 11.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

export function ChevronDownIcon({ size = 14 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M4 6.5L8 10.5L12 6.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function FileIcon({ size = 15 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M4 2.5H9.5L12.5 5.5V13.5H4V2.5Z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
      <path d="M9.5 2.5V5.5H12.5" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
    </svg>
  );
}

export function CopyIcon({ size = 14 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <rect x="5.5" y="5.5" width="7.5" height="8" rx="1" stroke="currentColor" strokeWidth="1.3" />
      <path d="M10.5 5.5V3.5C10.5 2.95 10.05 2.5 9.5 2.5H3.5C2.95 2.5 2.5 2.95 2.5 3.5V9.5C2.5 10.05 2.95 10.5 3.5 10.5H5.5" stroke="currentColor" strokeWidth="1.3" />
    </svg>
  );
}
