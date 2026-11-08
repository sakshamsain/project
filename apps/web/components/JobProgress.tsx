"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

type Job = { status: string; message: string | null; error: string | null };

export default function JobProgress({ id }: { id: string }) {
  const router = useRouter();
  const [job, setJob] = useState<Job | null>(null);

  useEffect(() => {
    let stop = false;
    async function tick() {
      try {
        const res = await fetch(`/api/jobs/${id}`, { cache: "no-store" });
        if (res.ok) {
          const j = (await res.json()) as Job;
          if (stop) return;
          setJob(j);
          if (j.status === "done") {
            router.replace(window.location.pathname);
            router.refresh();
            return;
          }
          if (j.status === "failed") return;
        }
      } catch {
        // keep polling
      }
      if (!stop) setTimeout(tick, 3000);
    }
    tick();
    return () => {
      stop = true;
    };
  }, [id, router]);

  if (job?.status === "failed") {
    return (
      <p className="notice" role="status">
        The ledger could not be built: {job.error ?? "unknown error"}. Try again later.
      </p>
    );
  }
  return (
    <div className="panel building" role="status" aria-live="polite">
      <p className="building-title">Building the ledger</p>
      <p className="section-note" style={{ margin: 0 }}>
        {job?.status === "queued" || !job
          ? "Waiting for a worker; this takes about a minute."
          : (job.message ?? "Working")}
      </p>
    </div>
  );
}
