export function CarePathArtwork() {
  return <svg aria-hidden="true" className="pointer-events-none absolute inset-0 h-full w-full opacity-70" viewBox="0 0 720 520" fill="none" preserveAspectRatio="xMidYMid slice">
    <defs><linearGradient id="care-path" x1="70" y1="80" x2="650" y2="440" gradientUnits="userSpaceOnUse"><stop stopColor="#0F766E"/><stop offset="1" stopColor="#67E8F9" stopOpacity=".35"/></linearGradient><pattern id="care-dots" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1" fill="#0F766E" fillOpacity=".14"/></pattern></defs>
    <rect width="720" height="520" fill="url(#care-dots)"/><path className="care-path-line" d="M32 110C150 62 124 230 268 212s123-135 255-86c77 29 65 139 173 135" stroke="url(#care-path)" strokeWidth="2" strokeDasharray="7 9"/>
    {[[62,100],[268,212],[440,140],[615,340],[690,245]].map(([cx, cy], index) => <g key={index}><circle cx={cx} cy={cy} r="14" fill="white" fillOpacity=".8"/><circle cx={cx} cy={cy} r="6" fill="#0F766E"/><circle className="care-node" cx={cx} cy={cy} r="12" stroke="#2DD4BF" strokeOpacity=".45"/></g>)}
  </svg>;
}
