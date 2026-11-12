export { usd, parseBudget } from "./commercePolicy";
import { resolveApiBase } from "./apiBase";
import type { Overlay } from "./types";

export const commerceBase = resolveApiBase(
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8100",
  typeof window === "undefined" ? undefined : window.location.hostname,
);

export async function commerceRequest<T>(path: string, body?: unknown, method?: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${commerceBase}${path}`, {
      method: method || (body === undefined ? "GET" : "POST"), credentials: "include", cache: "no-store",
      headers: { "Content-Type": "application/json", "X-GhostRep-CSRF": "1" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch { throw new Error("We couldn’t connect to your coaching space. Please try again in a moment; your saved sets haven’t changed."); }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "This request could not be completed. Check your inputs and try again.");
  return data as T;
}

export type ReviewPackage = {
  id: string; name: string; description: string; price_cents: number; currency: string; clip_count: number;
  deliverables: string[]; kind?: "live_calls" | "written_review" | "ai_report";
  family?: "agentic" | "instructor" | "legacy"; human_delivery?: boolean; delivery_label?: string;
  min_clips?: number; session_count?: number; session_minutes?: number;
};
export type ReviewCatalog = { packages: ReviewPackage[]; merchant: string; sandbox_configured: boolean; simulator_available: boolean; ai_available: boolean; notice?: string };
export type PaymentConfig = { sandbox: boolean; currency: string; client_id: string | null; client_token: string | null; sdk_url: string; configured: boolean };
export type MovementAnalysis = { severity: number; recurring: boolean; issues: string[]; beneficial: boolean; summary: string; findings?: { metric: string; recording_id: string; rep_id: number; seconds: number | null; text: string }[] };
export type ServiceAlternative = { id: string; name: string; price_cents: number; kind?: string; deliverables?: string[] };
export type AgenticRecommendation = Recommendation & {
  analysis?: MovementAnalysis;
  alternatives?: ServiceAlternative[];
  comparison?: { id: string; name: string; price_cents: number; expertise?: string; deliverable?: string }[];
};
export type AgenticRecommendResponse = {
  id: string; recommendation: AgenticRecommendation; mode: string; recording_ids: string[];
  question: string; budget_cents: number | null; catalog: ReviewPackage[]; requires_approval: boolean; notice?: string;
};
export type Fulfillment = {
  family?: string; kind?: string; human_delivery?: boolean; delivery_label?: string;
  unlocked?: boolean; status?: string; demo_notice?: string | null; delivered_at?: string | null;
};
export type SharedCoachingContext = {
  recording_id: string;
  suggestion: { id?: string; revision?: number; source?: string; source_label?: string; summary?: string; reason?: string; primary_cue?: string | null; suggested_action?: string; suggested_reps?: number | null; suggested_rest_seconds?: number | null; suggested_load_kg?: number | null; actionable?: boolean; user_decision?: string } | null;
  latest_answer: { question: string; headline?: string; answer: string; uncertainty?: string | null; source?: string; notice?: string | null; basis?: string } | null;
};
export type HandoffPreview = { context: SharedCoachingContext | null; fingerprint: string | null };
export type ReviewRecording = { id: string; set_index: number | null; created_at: string; exercise_id: string; processing_status: string; synthetic: boolean; has_video: boolean; analysis_ready: boolean; detected_reps: number | null; logged_reps: number | null };
export type Recommendation = { outcome: "recommend" | "no_match" | "follow_up"; package_id: string | null; source: string; source_label: string; explanation: string; limits: string };
export type ReviewIntake = { id: string; question: string; recommendation: Recommendation; mode: string; recording_ids: string[]; budget_cents: number | null };
export type ReviewTask = { id: string; status: string; delivered_text: string | null; author: string | null; delivered_at: string | null; draft?: string; draft_source?: string; revision?: number; assessment?: string | null; ai_comparison?: string | null; next_steps?: string | null };
export type CoachingCall = { id: string; session_index: number; requested_at: string; requested_timezone: string; change_requested_at: string | null; change_timezone: string | null; starts_at: string | null; meeting_url: string | null; status: "requested" | "confirmed" | "completed" | "paused" | "canceled" };
export type ReviewOrder = { plan_review?: PlanReviewContext | null; shared_context: SharedCoachingContext | null; previous_order_id: string | null; followup_available: boolean; calls: CoachingCall[]; id: string; mode: "sandbox" | "simulated"; package: ReviewPackage; amount_cents: number; currency: string; payment_state: string; provider_order_id: string | null; capture_id: string | null; approval_url: string | null; question: string; recommendation: Recommendation; sharing: { recording_ids: string[]; consented_at: string; ai_consented_at: string | null }; fulfillment?: Fulfillment; task: ReviewTask | null; last_error: string | null; created_at: string; refund: { state: string; provider_id: string | null; last_error: string | null } | null; history: { state: string; detail: string; at: string }[] };
export type SharedClip = { recording_id: string; synthetic: boolean; has_video: boolean; reference_rep: number | null; facts: Record<string, { text: string; evidence_ids: string[] }>; reps: { rep_index: number; start_seconds: number; end_seconds: number; is_reference: boolean }[]; overlay: Overlay | null };
export const stateLabel = (value: string) => ({ paid: "Payment confirmed", checkout_ready: "Awaiting buyer approval", capture_pending: "Payment pending", refund_pending: "Refund pending", uncertain: "Needs reconciliation", canceled: "Canceled", refunded: "Refunded", failed: "Payment failed", created: "Order saved", queued: "In coach inbox", draft: "Coach is reviewing", delivered: "Feedback delivered" }[value] || value);
export const fieldClass = "mt-2 w-full rounded-xl border border-white/15 px-4 py-3 text-sm leading-6 focus:border-teal";

export type PlanReviewContext = {
  kind: "plan_review"; plan_id: string; fingerprint: string; mode: "sandbox" | "simulated";
  plan: { name: string; notes?: string; exercises: { name: string; sets: number; target_reps: number; rest_seconds: number; notes?: string }[]; schedule?: unknown };
  restrictions: string[]; training_preferences: Record<string, unknown>;
  preferences?: { gender: string; nationality: string; language: string; experience: string; specialty: string; preferred_at: string; timezone: string };
  availability_status?: string;
};
