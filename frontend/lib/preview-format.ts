export function previewNumber(value: unknown, kind: string, enabled: boolean): string {
  const text = String(value);
  if (!enabled || !["integer", "decimal", "currency", "percentage"].includes(kind)) return text;
  const match = text.match(/^([^\d]*?)([+-]?)(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?([^\d]*)$/);
  if (!match) return text;
  const digits = match[3].replaceAll(",", "");
  if (/^0\d/.test(digits)) return text;
  return match[1] + match[2] + digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",") + (match[4] || "") + match[5];
}
