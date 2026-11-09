"use client";

import { useState } from "react";
import { sendFeedback, type FeedbackContext } from "@/lib/api";

/** "Was this plan useful?" with thumbs, then an optional note. */
export function PlanFeedback({ context }: { context: FeedbackContext }) {
  const [useful, setUseful] = useState<boolean | null>(null);
  const [text, setText] = useState("");
  const [sent, setSent] = useState(false);

  if (sent) return <div className="text-xs text-text3">Thanks for the feedback!</div>;
  return (
    <div className="flex flex-col gap-1.5" data-testid="plan-feedback">
      <div className="flex items-center gap-2 text-xs text-text3">
        Was this plan useful?
        {[true, false].map((v) => (
          <button
            key={String(v)}
            type="button"
            aria-pressed={useful === v}
            aria-label={v ? "Useful" : "Not useful"}
            onClick={() => {
              setUseful(v);
              sendFeedback({ kind: "plan", useful: v, text: "", context }).catch(() => {});
            }}
            className={`rounded-full border px-2 py-0.5 text-sm ${useful === v ? "border-accent bg-row-on" : "border-line"}`}
          >
            {v ? "👍" : "👎"}
          </button>
        ))}
      </div>
      {useful !== null && (
        <Note
          placeholder={useful ? "What did you like? (optional)" : "What would make it better? (optional)"}
          text={text}
          setText={setText}
          onSend={() => sendFeedback({ kind: "plan", useful, text, context }).finally(() => setSent(true))}
        />
      )}
    </div>
  );
}

/** A general "Send feedback" link that opens a note box. */
export function FeedbackLink({ context }: { context: FeedbackContext }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [sent, setSent] = useState(false);
  if (sent) return <div className="text-center text-xs text-text3">Thanks for the feedback!</div>;
  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className="self-center text-xs font-semibold text-link" data-testid="feedback-link">
        Send feedback
      </button>
    );
  }
  return (
    <div className="flex flex-col gap-1.5 rounded-xl border border-line bg-surface p-3" data-testid="feedback-form">
      <div className="text-xs font-semibold">Feedback, ideas or something broken?</div>
      <Note placeholder="Tell us anything" text={text} setText={setText} onSend={() => sendFeedback({ kind: "general", useful: null, text, context }).finally(() => setSent(true))} />
    </div>
  );
}

function Note({ placeholder, text, setText, onSend }: { placeholder: string; text: string; setText: (t: string) => void; onSend: () => void }) {
  return (
    <div className="flex gap-2">
      <textarea
        value={text}
        maxLength={1000}
        rows={2}
        onChange={(e) => setText(e.target.value)}
        placeholder={placeholder}
        aria-label="Feedback note"
        className="min-w-0 flex-1 resize-none rounded-lg border border-input-line bg-input px-2 py-1.5 text-[13px] text-text placeholder:text-text3"
      />
      <button type="button" onClick={onSend} disabled={!text.trim()} className="self-end rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50">
        Send
      </button>
    </div>
  );
}
