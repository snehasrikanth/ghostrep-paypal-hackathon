export const usd = (cents: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(cents / 100);

export function parseBudget(value: string): number | null {
  if (!value.trim()) return null;
  if (!/^\d{1,4}(\.\d{1,2})?$/.test(value.trim())) throw new Error("Enter a USD budget with at most two decimal places.");
  const [whole, fraction = ""] = value.trim().split(".");
  const cents = Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
  if (cents > 100000) throw new Error("The maximum budget is $1,000.");
  return cents;
}
