"use client";

import { useActionState, useId, useState } from "react";

import { createMissionAction } from "@/app/actions";
import { initialCreateMissionState } from "@/lib/mission-form";
import styles from "./mission.module.css";

interface NewMissionFormProps {
  /** Styling for the trigger, so the hero button keeps its page-level design. */
  triggerClassName: string;
}

export function NewMissionForm({ triggerClassName }: NewMissionFormProps) {
  const [open, setOpen] = useState(false);
  const [state, action, pending] = useActionState(
    createMissionAction,
    initialCreateMissionState,
  );
  const [seenState, setSeenState] = useState(state);
  const panelId = useId();
  const titleId = useId();
  const goalId = useId();

  // `useActionState` returns a fresh object per submission, so comparing
  // identity collapses the panel exactly once per successful create. Adjusting
  // state during render is preferred over an effect here: it avoids the extra
  // commit that `setState` inside `useEffect` would cause. Closing unmounts the
  // form, which clears the fields without a manual reset.
  if (seenState !== state) {
    setSeenState(state);
    if (state.status === "success") {
      setOpen(false);
    }
  }

  return (
    <div className={styles.formWrapper}>
      <button
        className={triggerClassName}
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((previous) => !previous)}
      >
        <span aria-hidden="true">{open ? "×" : "＋"}</span>
        {open ? "Cancel" : "New Research Mission"}
      </button>

      {state.status !== "idle" && (
        <p
          className={
            state.status === "success" ? styles.successNote : styles.errorNote
          }
          role="status"
        >
          {state.message}
        </p>
      )}

      {open && (
        <form
          className={styles.form}
          id={panelId}
          action={action}
        >
          <div className={styles.field}>
            <label htmlFor={titleId}>Mission title</label>
            <input
              id={titleId}
              name="title"
              type="text"
              maxLength={200}
              required
              placeholder="On-device inference for edge robotics"
              aria-describedby={
                state.fieldErrors.title ? `${titleId}-error` : undefined
              }
            />
            {state.fieldErrors.title && (
              <span className={styles.fieldError} id={`${titleId}-error`}>
                {state.fieldErrors.title}
              </span>
            )}
          </div>

          <div className={styles.field}>
            <label htmlFor={goalId}>Research goal</label>
            <textarea
              id={goalId}
              name="goal"
              rows={3}
              required
              placeholder="Decide whether we should invest in quantized on-device models for our robotics line over the next two quarters."
              aria-describedby={
                state.fieldErrors.goal ? `${goalId}-error` : undefined
              }
            />
            {state.fieldErrors.goal && (
              <span className={styles.fieldError} id={`${goalId}-error`}>
                {state.fieldErrors.goal}
              </span>
            )}
          </div>

          <button className={styles.submit} type="submit" disabled={pending}>
            {pending ? "Creating…" : "Create mission"}
          </button>
        </form>
      )}
    </div>
  );
}
