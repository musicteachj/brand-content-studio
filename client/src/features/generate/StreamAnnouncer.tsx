import { useEffect, useState } from "react";

/** Announces a streamed generation to screen readers once, when it settles.
 *
 *  The streaming text must NOT sit inside an aria-live region: React rewrites the
 *  whole text node on every SSE token, so the reader re-announces the entire
 *  accumulated draft on each one — hundreds of ever-lengthening announcements per
 *  generation. Instead, the streaming container is marked `aria-busy` and this
 *  visually-hidden region emits one message when streaming starts and one when it
 *  finishes. Errors are left alone: each surface already has a `role="alert"`.
 */
export function StreamAnnouncer({
  status,
  label,
  chars,
}: {
  status: string;
  label: string;
  chars?: number;
}) {
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (status === "streaming") setMessage(`Generating ${label}…`);
    else if (status === "done")
      setMessage(chars != null ? `${label} ready, ${chars} characters.` : `${label} ready.`);
    else setMessage("");
  }, [status, label, chars]);

  return (
    <p aria-live="polite" className="sr-only">
      {message}
    </p>
  );
}
