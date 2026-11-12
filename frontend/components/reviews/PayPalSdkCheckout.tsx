"use client";

import { useEffect, useRef, useState } from "react";
import { loadPayPalSdk } from "@/lib/paypalSdk";
import { Button } from "@/components/ui/button";
import { commerceRequest, type PaymentConfig, type ReviewOrder } from "@/lib/commerce";

type PaypalNamespace = {
  createInstance: (options: {
    clientToken?: string;
    clientId?: string;
    components: string[];
    pageType?: string;
  }) => Promise<{
    findEligibleMethods: (options: { currencyCode: string }) => Promise<{ isEligible: (method: string) => boolean }>;
    createPayPalOneTimePaymentSession: (options: {
      onApprove: (data: { orderId: string }) => Promise<unknown> | unknown;
      onCancel?: (data: { orderId?: string }) => void;
      onError?: (error: unknown) => void;
    }) => {
      start: (options: { presentationMode: string }, orderPromise: Promise<{ orderId: string }>) => Promise<void>;
    };
  }>;
};

declare global {
  interface Window {
    paypal?: PaypalNamespace;
  }
}

export function PayPalSdkCheckout({
  order,
  onUpdated,
  onError,
}: {
  order: ReviewOrder;
  onUpdated: (order: ReviewOrder) => void;
  onError: (message: string) => void;
}) {
  const [config, setConfig] = useState<PaymentConfig | null>(null);
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const [retry, setRetry] = useState(0);
  const [setupError, setSetupError] = useState("");
  const sdk = useRef<Awaited<ReturnType<PaypalNamespace["createInstance"]>> | null>(null);
  const starting = useRef(false);

  useEffect(() => {
    let alive = true;
    commerceRequest<PaymentConfig>("/api/payments/config").then(async cfg => {
      if (!alive) return;
      setConfig(cfg);
      if (!cfg.configured || (!cfg.client_token && !cfg.client_id)) return;
      try {
        await loadPayPalSdk();
        if (!window.paypal) throw new Error("PayPal did not initialize. Use redirect checkout or retry.");
        const instance = await window.paypal.createInstance({
          ...(cfg.client_id ? { clientId: cfg.client_id } : { clientToken: cfg.client_token! }),
          components: ["paypal-payments"], pageType: "checkout",
        });
        const methods = await instance.findEligibleMethods({ currencyCode: "USD" });
        if (!methods.isEligible("paypal")) throw new Error("PayPal popup checkout is unavailable in this browser. Use secure redirect checkout below.");
        if (alive) { sdk.current = instance; setReady(true); setSetupError(""); }
      } catch (e) {
        if (alive) { setReady(false); setSetupError(e instanceof Error ? e.message : "PayPal unavailable. Try secure redirect checkout."); }
      }
    }).catch(() => { if (alive) setSetupError("PayPal configuration could not load. Retry or use secure redirect checkout."); });
    return () => { alive = false; };
  }, [retry]);

  async function startCheckout() {
    if (starting.current || !config || !sdk.current || !order.provider_order_id) return;
    starting.current = true;
    setBusy(true);
    onError("");
    try {
      const session = sdk.current.createPayPalOneTimePaymentSession({
        onApprove: async data => {
          if (data.orderId !== order.provider_order_id) {
            onError("PayPal returned a different order. Refresh payment status before continuing.");
            return;
          }
          const captured = await commerceRequest<ReviewOrder>(`/api/payments/orders/${order.id}/capture`, {});
          onUpdated(captured);
        },
        onCancel: () => onError("PayPal checkout closed. No payment has been confirmed. You can retry this order or refresh its status."),
        onError: () => onError("PayPal checkout failed. No fulfillment was unlocked."),
      });
      await session.start(
        { presentationMode: "auto" },
        Promise.resolve({ orderId: order.provider_order_id }),
      );
    } catch (e) {
      onError(e instanceof Error ? e.message : "PayPal checkout could not start.");
    } finally {
      starting.current = false;
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      {!config && !setupError && <p role="status" className="text-xs text-white/60">Preparing secure PayPal checkout…</p>}
      {config && !config.configured && <p className="text-xs leading-6 text-amber">PayPal is not configured yet. Your order is saved.</p>}
      {setupError && <div role="status" className="rounded-xl border border-amber/25 p-3 text-xs leading-6 text-amber">{setupError}<Button variant="ghost" onClick={() => { setSetupError(""); setRetry(n => n+1); }}>Retry PayPal</Button></div>}
      <Button className="w-full bg-[#ffc439] text-[#003087] hover:bg-[#ffd15f]" disabled={busy || !ready || !order.provider_order_id} loading={busy} loadingLabel="Opening PayPal…" onClick={startCheckout}>
        Pay with PayPal
      </Button>
      {order.approval_url && (
        <a className="flex min-h-11 items-center justify-center rounded-full border border-white/15 px-4 text-xs text-white/70 hover:border-teal hover:text-teal" href={order.approval_url}>
          Continue to PayPal securely
        </a>
      )}
      <p className="text-[11px] leading-5 text-white/55">
        Your request is sent after payment confirmation. One-time purchase, with no automatic renewal.
      </p>
    </div>
  );
}
