// Small inline SVG icons used in the app UI (stroke icons, currentColor).

const base = (size) => ({
  width: size, height: size, viewBox: "0 0 24 24", fill: "none",
  stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round",
});

export const Flame = ({ size = 28 }) => (
  <svg width={size} height={size * 1.3} viewBox="0 0 40 52" aria-hidden="true">
    <defs>
      <linearGradient id="fl" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stopColor="#E7B964" />
        <stop offset="1" stopColor="#C8963E" />
      </linearGradient>
    </defs>
    <path d="M20 2C24 14 36 20 34 34c-1.4 9.5-8 16-14 16S7.4 43.5 6 34C4 20 16 14 20 2z" fill="url(#fl)" />
    <path d="M20 22c2 6 7 9 6 16-.6 4-3 7-6 7s-5.4-3-6-7c-1-7 4-10 6-16z" fill="#F6F3EC" opacity=".9" />
  </svg>
);

export const Home = ({ size = 24, filled }) => (
  <svg {...base(size)}>
    <path d="M3 11 12 3.5 21 11v9.5h-6.5v-6h-5v6H3z" fill={filled ? "currentColor" : "none"} />
  </svg>
);
export const Library = ({ size = 24 }) => (
  <svg {...base(size)}><path d="M5 4h10a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3zM8 17h10M9 8h5M9 11h5" /></svg>
);
export const Search = ({ size = 24 }) => (
  <svg {...base(size)}><circle cx="10.5" cy="10.5" r="6.5" /><path d="m15.5 15.5 5 5" /></svg>
);
export const More = ({ size = 24 }) => (
  <svg {...base(size)}><circle cx="5" cy="12" r="1.2" /><circle cx="12" cy="12" r="1.2" /><circle cx="19" cy="12" r="1.2" /></svg>
);
export const Back = ({ size = 24 }) => (
  <svg {...base(size)}><path d="M15 5 8 12l7 7" /></svg>
);
export const Chevron = ({ size = 18 }) => (
  <svg {...base(size)}><path d="M15 6 9 12l6 6" /></svg>
);
export const Play = ({ size = 16 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24"><path d="M7 4.5v15l12-7.5z" fill="currentColor" /></svg>
);
export const Pause = ({ size = 16 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24"><path d="M6.5 4.5h4v15h-4zM13.5 4.5h4v15h-4z" fill="currentColor" /></svg>
);
export const Plus = ({ size = 18 }) => (
  <svg {...base(size)}><path d="M12 5v14M5 12h14" /></svg>
);
export const Check = ({ size = 14 }) => (
  <svg {...base(size)} strokeWidth="2.6"><path d="m5 12.5 4.5 4.5L19 7.5" /></svg>
);
export const External = ({ size = 16 }) => (
  <svg {...base(size)}><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" /></svg>
);
export const Book = ({ size = 16 }) => (
  <svg {...base(size)}><path d="M3 5.5C5.5 4 9 4 12 6c3-2 6.5-2 9-.5V19c-2.5-1.5-6-1.5-9 .5-3-2-6.5-2-9-.5z" /><path d="M12 6v13.5" /></svg>
);
export const User = ({ size = 16 }) => (
  <svg {...base(size)}><circle cx="12" cy="8" r="4" /><path d="M4 21c1-4.5 4.5-7 8-7s7 2.5 8 7" /></svg>
);
export const Bulb = ({ size = 18 }) => (
  <svg {...base(size)}><path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z" /></svg>
);
export const Sparkle = ({ size = 14 }) => (
  <svg {...base(size)}><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6" /></svg>
);
export const Star = ({ size = 13 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24"><path d="M12 2.5l2.9 6 6.6.8-4.9 4.5 1.3 6.5L12 17l-5.9 3.3 1.3-6.5-4.9-4.5 6.6-.8z" fill="currentColor" /></svg>
);
export const Trash = ({ size = 16 }) => (
  <svg {...base(size)}><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13" /></svg>
);
