/** Optional examples only. Never a recording, personal reference, or analysis input. */
const DEMOS: Record<string, { src: string; title: string; description: string }> = {
  barbell_squat: {
    src: "/demos/squat-example.mp4",
    title: "Barbell squat · recorded example",
    description: "A recorded barbell squat set for movement context. Your own recorded reps provide your personal comparison reference; this example is not a technique assessment.",
  },
};

export function exerciseDemo(exerciseId: string) {
  return Object.hasOwn(DEMOS, exerciseId) ? DEMOS[exerciseId] : null;
}
