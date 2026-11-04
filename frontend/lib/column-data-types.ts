export const columnDataTypes = [
  ["identifier","Identifier"], ["numeric","Number"], ["currency","Currency"],
  ["percentage","Percentage/ratio"], ["phone","Phone number"],
  ["coordinate","Location (longitude-latitude)"], ["duration","Duration"],
  ["time","Clock hour"], ["text","Text"], ["boolean","Boolean"], ["date","Date"]
] as const;
export function columnTypeLabel(type: string) {
  return columnDataTypes.find(([value]) => value === type)?.[1] || type.replaceAll("_", " ");
}
