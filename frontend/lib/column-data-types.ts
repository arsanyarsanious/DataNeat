export const columnDataTypes = [
  ["", "Auto — detect from data"],
  ["text", "Text"], ["category", "Category / labels"],
  ["numeric", "Number"], ["salary", "Salary / numeric amount"],
  ["identifier", "Serial / identifier"], ["phone", "Phone number"],
  ["email", "Email address"], ["boolean", "Boolean — Yes / No"],
  ["date", "Date"], ["datetime", "Date and time"],
  ["time", "Clock time — AM / PM or 24-hour"], ["duration", "Elapsed duration"],
  ["location", "Location / place name"], ["coordinate", "Geographical coordinate"],
  ["currency", "Currency amount"], ["percentage", "Percentage / ratio"],
  ["url", "Website / URL"], ["ip", "IP address"],
] as const;
export function columnTypeLabel(type: string) {
  return columnDataTypes.find(([value]) => value === type)?.[1] || type.replaceAll("_", " ");
}
