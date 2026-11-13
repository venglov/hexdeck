// The HexDeck mark, drawn for Decky's plugin list.
//
// It sizes itself like a react-icons glyph (1em square), so it matches the
// other plugins' icons, and its mark is centred in a 24x24 box. The outer
// rings use currentColor: Decky draws them light on the dark row and dark on
// the white focus highlight, so they stay visible in both states. Only the
// gradient hexagon keeps its own colours.
export function HexDeckIcon() {
  return (
    <svg viewBox="0 0 24 24" width="1em" height="1em" aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id="hexdeck-icon-fill" gradientUnits="userSpaceOnUse" x1="4.4" y1="6.2" x2="14.5" y2="17.8">
          <stop offset="0" stopColor="#19d6ff" />
          <stop offset="1" stopColor="#6b46ef" />
        </linearGradient>
      </defs>
      <path d="M9.45 6.2 14.47 9.1v5.8L9.45 17.8 4.43 14.9V9.1Z" fill="url(#hexdeck-icon-fill)" />
      <path
        d="M9.45 3.65 16.68 7.83v8.35L9.45 20.35M9.45 1 18.98 6.5v11L9.45 23"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.2"
      />
    </svg>
  );
}
