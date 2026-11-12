import assert from "node:assert/strict";
import test from "node:test";
import { loadPayPalSdk } from "./paypalSdk.ts";

class Script extends EventTarget {
  dataset: Record<string, string> = {};
  src = ""; async = false; isConnected = false;
  remove() { this.isConnected = false; }
}
function page() {
  const scripts: Script[] = [];
  return { scripts, doc: {
    querySelector: () => scripts.find(s => s.isConnected) || null,
    createElement: () => { const s = new Script(); scripts.push(s); return s; },
    body: { appendChild: (s: Script) => { s.isConnected = true; } },
  } as unknown as Document };
}

test("concurrent receipts share one SDK load and reuse it after success", async () => {
  const { doc, scripts } = page();
  const first = loadPayPalSdk(doc), second = loadPayPalSdk(doc);
  assert.equal(first, second);
  assert.equal(scripts.length, 1);
  assert.equal(scripts[0].src, "https://www.sandbox.paypal.com/web-sdk/v6/core");
  scripts[0].dispatchEvent(new Event("load"));
  await first;
  await loadPayPalSdk(doc);
  assert.equal(scripts.length, 1);
});

test("blocked SDK can be retried instead of leaving checkout permanently disabled", async () => {
  const { doc, scripts } = page();
  const failed = loadPayPalSdk(doc);
  scripts[0].dispatchEvent(new Event("error"));
  await assert.rejects(failed, /Retry/);
  assert.equal(scripts[0].isConnected, false);
  const retry = loadPayPalSdk(doc);
  scripts[1].dispatchEvent(new Event("load"));
  await retry;
  assert.equal(scripts.length, 2);
});

test("SDK load timeout removes the stalled script and allows recovery", async () => {
  const { doc, scripts } = page();
  await assert.rejects(loadPayPalSdk(doc, 5), /PayPal could not load/);
  assert.equal(scripts[0].isConnected, false);
  const retry = loadPayPalSdk(doc);
  scripts[1].dispatchEvent(new Event("load"));
  await retry;
});
