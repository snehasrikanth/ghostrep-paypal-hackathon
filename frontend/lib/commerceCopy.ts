/** Presentation for server-owned service/status copy, never athlete questions or coach advice. */
export function serviceText(value: string | null | undefined): string {
  return (value || "")
    .replace(/PayPal Sandbox/gi, "PayPal")
    .replace(/\bSandbox\b/g, "test checkout")
    .replace(/Demo coaching workflow · no real coach is hired automatically/g, "Coach assignment and session time require confirmation")
    .replace(/Demo booking request · pending confirmation/g, "Awaiting coach confirmation")
    .replace(/\(demo workflow\)/gi, "")
    .replace(/One-time demo purchase/gi, "One-time purchase")
    .replace(/Demo coaching workflow\./g, "Coach review and automated feedback are separate services.")
    .replace(/\bdemo\b/gi, "sample")
    .replace(/human coaching/gi, "live coaching")
    .replace(/human coach/gi, "live coach")
    .trim();
}
