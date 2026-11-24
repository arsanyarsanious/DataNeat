export const columnDataTypes = [
  ["text", "Text"],
  ["category", "Category"],
  ["numeric", "Number"],
  ["identifier", "Serial / identifier"],
  ["phone", "Phone number"],
  ["email", "Email address"],
  ["boolean", "Boolean"],
  ["date", "Date"],
  ["datetime", "Date and time"],
  ["time", "Clock time"],
  ["duration", "Duration"],
  ["location", "Location / place name"],
  ["coordinate", "Geographical coordinate"],
  ["currency", "Currency"],
  ["percentage", "Percentage / ratio"],
  ["url", "URL"],
  ["ip", "IP address"],
] as const;
export function columnTypeLabel(type: string) {
  if (type === "salary") return "Number";
  return columnDataTypes.find(([value]) => value === type)?.[1] || type.replaceAll("_", " ");
}
