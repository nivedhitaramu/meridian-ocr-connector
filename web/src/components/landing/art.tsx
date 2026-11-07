/** Drawn illustrations for the landing page. All decorative, so hidden from screen readers. */

export function LogoMark({ className = "size-8" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <rect x="2" y="6" width="13" height="20" rx="3" className="fill-neutral-950" />
      <path d="M17 6h6.5a6.5 6.5 0 0 1 6.5 6.5V26H17z" className="fill-orange-500" />
      <rect x="20" y="13" width="7" height="2.5" rx="1.25" className="fill-neutral-950" />
    </svg>
  );
}

/** An isometric shipping container in charcoal, with the product's mark on its side. */
export function ContainerArt({ className = "" }: { className?: string }) {
  const ribs = Array.from({ length: 13 }, (_, i) => i);
  return (
    <svg viewBox="0 0 640 420" className={className} aria-hidden>
      <defs>
        <linearGradient id="side" x1="0" x2="1">
          <stop offset="0" stopColor="#3a3a3c" />
          <stop offset="1" stopColor="#1c1c1e" />
        </linearGradient>
        <linearGradient id="end" x1="0" x2="1">
          <stop offset="0" stopColor="#2a2a2c" />
          <stop offset="1" stopColor="#141416" />
        </linearGradient>
        <linearGradient id="top" x1="0" x2="1">
          <stop offset="0" stopColor="#4a4a4d" />
          <stop offset="1" stopColor="#2e2e30" />
        </linearGradient>
        <radialGradient id="glow" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0" stopColor="#fb923c" stopOpacity="0.35" />
          <stop offset="1" stopColor="#fb923c" stopOpacity="0" />
        </radialGradient>
      </defs>
      <ellipse cx="420" cy="300" rx="200" ry="110" fill="url(#glow)" />
      <ellipse cx="330" cy="372" rx="250" ry="26" fill="#000" opacity="0.18" />
      {/* top */}
      <polygon points="150,120 420,40 560,110 290,190" fill="url(#top)" />
      {/* long side */}
      <polygon points="150,120 290,190 290,360 150,290" fill="url(#end)" />
      {/* door end */}
      <polygon points="290,190 560,110 560,280 290,360" fill="url(#side)" />
      {ribs.map((i) => {
        const t = (i + 1) / 14;
        const x1 = 290 + (560 - 290) * t;
        const y1 = 190 + (110 - 190) * t;
        return <line key={i} x1={x1} y1={y1 + 6} x2={x1} y2={y1 + 164} stroke="#0d0d0e" strokeWidth="5" opacity="0.55" />;
      })}
      {[0, 1, 2, 3].map((i) => {
        const x = 170 + i * 30;
        return <line key={i} x1={x} y1={132 + i * 15} x2={x} y2={300 + i * 15} stroke="#0d0d0e" strokeWidth="4" opacity="0.7" />;
      })}
      {/* door bars */}
      <line x1="205" y1="160" x2="205" y2="318" stroke="#f97316" strokeWidth="3" />
      <line x1="245" y1="178" x2="245" y2="336" stroke="#f97316" strokeWidth="3" />
      {/* the mark on the side */}
      <g transform="matrix(1,-0.296,0,1,318,262)">
        <rect x="0" y="-30" width="26" height="44" rx="6" fill="#e5e5e5" />
        <path d="M31 -30h13a13 13 0 0 1 13 13V14H31z" fill="#f97316" />
        <text x="68" y="4" fill="#f5f5f5" fontSize="27" fontWeight="800" fontFamily="var(--font-urbanist), sans-serif" letterSpacing="1">
          MERIDIAN.
        </text>
      </g>
      {/* corner castings */}
      {[
        [150, 120],
        [290, 190],
        [560, 110],
        [290, 360],
        [560, 280],
        [150, 290],
      ].map(([x, y]) => (
        <rect key={`${x}-${y}`} x={x - 7} y={y - 7} width="14" height="14" rx="2" fill="#111" />
      ))}
    </svg>
  );
}

/** A small stack of document pages, for the document cards. */
export function DocumentArt({ tone }: { tone: "orange" | "slate" | "stone" }) {
  const accent = tone === "orange" ? "#f97316" : tone === "slate" ? "#38bdf8" : "#a3e635";
  return (
    <svg viewBox="0 0 220 180" className="h-full w-full" aria-hidden>
      <rect x="54" y="28" width="112" height="140" rx="10" fill="#ffffff" opacity="0.18" transform="rotate(-8 110 98)" />
      <rect x="58" y="22" width="112" height="140" rx="10" fill="#ffffff" />
      <rect x="72" y="40" width="54" height="8" rx="4" fill="#111" />
      <rect x="72" y="58" width="84" height="5" rx="2.5" fill="#d4d4d4" />
      <rect x="72" y="70" width="70" height="5" rx="2.5" fill="#d4d4d4" />
      <rect x="72" y="82" width="78" height="5" rx="2.5" fill="#d4d4d4" />
      <rect x="72" y="104" width="84" height="22" rx="6" fill={accent} opacity="0.2" />
      <rect x="80" y="111" width="40" height="8" rx="4" fill={accent} />
      <rect x="72" y="136" width="30" height="5" rx="2.5" fill="#d4d4d4" />
      <rect x="132" y="134" width="24" height="9" rx="4.5" fill="#111" />
    </svg>
  );
}
