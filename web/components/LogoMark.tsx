/* The textchef mark: a round character in big glasses wearing a chef's hat,
 * simplified for small sizes (the full drawing is docs/logo.svg).
 * Colours come from the theme (see .logo-mark in globals.css): the hat and the
 * face take the header's text colour, the lenses and the gaps take the header's
 * background, and the hat band takes the accent. */
export function LogoMark() {
  return (
    <svg className="logo-mark" viewBox="0 0 100 100" aria-hidden="true" focusable="false">
      <circle cx="50" cy="66" r="32" />
      <circle className="logo-cut" cx="37.5" cy="63" r="11" />
      <circle className="logo-cut" cx="62.5" cy="63" r="11" />
      <circle cx="37.5" cy="63" r="4.8" />
      <circle cx="62.5" cy="63" r="4.8" />
      <g transform="rotate(-9 50 36)">
        <circle cx="36" cy="21" r="11" />
        <circle cx="64" cy="21" r="11" />
        <circle cx="50" cy="15" r="13" />
        <rect x="29" y="22" width="42" height="12" />
        <rect className="logo-band" x="27.5" y="29" width="45" height="10" rx="2" />
      </g>
    </svg>
  );
}
