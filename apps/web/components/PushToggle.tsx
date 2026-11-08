"use client";

import { useEffect, useState } from "react";

type State = "checking" | "unsupported" | "ios-install" | "off" | "on" | "busy" | "denied" | "error";

function keyBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const pad = "=".repeat((4 - (base64url.length % 4)) % 4);
  const raw = atob((base64url + pad).replace(/-/g, "+").replace(/_/g, "/"));
  const out = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

export default function PushToggle({ vapidKey }: { vapidKey: string }) {
  const [state, setState] = useState<State>("checking");

  useEffect(() => {
    const ios = /iPhone|iPad|iPod/.test(navigator.userAgent);
    const standalone = window.matchMedia("(display-mode: standalone)").matches;
    if (!("serviceWorker" in navigator) || !("PushManager" in window) || !vapidKey) {
      setState(ios && !standalone ? "ios-install" : "unsupported");
      return;
    }
    if (Notification.permission === "denied") {
      setState("denied");
      return;
    }
    navigator.serviceWorker.ready
      .then((reg) => reg.pushManager.getSubscription())
      .then((sub) => setState(sub ? "on" : "off"))
      .catch(() => setState("error"));
  }, [vapidKey]);

  async function turnOn() {
    setState("busy");
    try {
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setState(permission === "denied" ? "denied" : "off");
        return;
      }
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: keyBytes(vapidKey),
      });
      const res = await fetch("/api/push", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(sub.toJSON()),
      });
      setState(res.ok ? "on" : "error");
    } catch {
      setState("error");
    }
  }

  async function turnOff() {
    setState("busy");
    try {
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.getSubscription();
      if (sub) {
        await fetch("/api/push", {
          method: "DELETE",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ endpoint: sub.endpoint }),
        });
        await sub.unsubscribe();
      }
      setState("off");
    } catch {
      setState("error");
    }
  }

  const note: Record<State, string> = {
    checking: "Checking this browser.",
    unsupported: "This browser cannot receive notifications from FINN.",
    "ios-install":
      "On iPhone, add FINN to your Home Screen first (Share, then Add to Home Screen), open it from there and turn notifications on here.",
    off: "Get a notification when a filing makes the front page, and after the close when a holding moves past your limits.",
    on: "Notifications are on for this device.",
    busy: "Working on it.",
    denied: "Notifications are blocked for this site. Allow them in the browser's site settings, then come back.",
    error: "Could not change notifications. Try again.",
  };

  return (
    <div className="panel">
      <p className="section-note" style={{ margin: "0 0 0.75rem" }} aria-live="polite">
        {note[state]}
      </p>
      {state === "off" || state === "error" ? (
        <button className="button" type="button" onClick={turnOn}>
          Turn on notifications
        </button>
      ) : state === "on" ? (
        <button className="button ghost" type="button" onClick={turnOff}>
          Turn off notifications
        </button>
      ) : null}
    </div>
  );
}
