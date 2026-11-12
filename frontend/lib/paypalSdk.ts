/** One shared load per document, bounded wait, and recovery after a blocked/failed script. */
const loads = new WeakMap<Document, Promise<void>>();
export function loadPayPalSdk(doc: Document = document, timeoutMs = 15000): Promise<void> {
  const active = loads.get(doc);
  if (active) return active;
  const promise = new Promise<void>((resolve, reject) => {
    let script = doc.querySelector<HTMLScriptElement>('script[data-ghostrep-paypal="v6"]');
    if (script?.dataset.loaded === "1") { resolve(); return; }
    if (!script) {
      script = doc.createElement("script");
      script.src = "https://www.sandbox.paypal.com/web-sdk/v6/core";
      script.async = true;
      script.dataset.ghostrepPaypal = "v6";
    }
    const target = script;
    const cleanup = () => { clearTimeout(timer); target.removeEventListener("load", loaded); target.removeEventListener("error", failed); };
    const loaded = () => { cleanup(); target.dataset.loaded = "1"; resolve(); };
    const failed = () => { cleanup(); target.remove(); reject(new Error("PayPal could not load. Retry or use secure redirect checkout below.")); };
    const timer = setTimeout(failed, timeoutMs);
    target.addEventListener("load", loaded, { once: true });
    target.addEventListener("error", failed, { once: true });
    if (!target.isConnected) doc.body.appendChild(target);
  });
  loads.set(doc, promise);
  void promise.catch(() => { if (loads.get(doc) === promise) loads.delete(doc); });
  return promise;
}
