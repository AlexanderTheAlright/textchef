/* The textchef mark: three lines of text, the middle one cut short by a point.
 * Colours come from the theme: the lines take the surrounding text colour and
 * the point takes the accent (see .logo-mark in globals.css). */
export function LogoMark() {
  return (
    <svg className="logo-mark" viewBox="0 0 64 64" aria-hidden="true" focusable="false">
      <polygon points="11,9 59,9 54,19 6,19" />
      <polygon points="11,27 32,27 27,37 6,37" />
      <circle className="logo-point" cx="46" cy="32" r="9" />
      <polygon points="11,45 47,45 42,55 6,55" />
    </svg>
  );
}
