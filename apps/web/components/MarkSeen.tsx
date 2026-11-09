"use client";

import { useEffect } from "react";

/** Records that the inbox was opened, so the tab badge clears. */
export default function MarkSeen() {
  useEffect(() => {
    void fetch("/api/inbox", { method: "POST" }).then(() => window.dispatchEvent(new Event("finn:inbox-seen")));
  }, []);
  return null;
}
