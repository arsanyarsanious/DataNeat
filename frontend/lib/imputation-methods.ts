const statisticalAliases: Record<string, string> = {
  group_mean: "mean",
  group_median: "median",
  group_mode: "mode",
};

// Existing plans may still contain the grouped aliases. Grouping is selected
// separately, so the menus expose each statistic only once.
export function imputationMethod(method: string): string {
  return statisticalAliases[method] || method;
}

export function imputationMethods(methods: string[]): string[] {
  return [...new Set(methods.map(imputationMethod))];
}
