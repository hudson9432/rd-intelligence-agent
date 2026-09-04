/**
 * Form state shared by the mission Server Action and the client form.
 *
 * This deliberately lives outside `app/actions.ts`: a `"use server"` module
 * registers *every* export as a Server Function reference, so exporting a
 * plain value from it makes React throw "Server Functions cannot be called
 * during initial render" when that value is used as initial state.
 */

export interface CreateMissionState {
  status: "idle" | "success" | "error";
  message: string;
  /** Field-level messages keyed by input name, for inline validation. */
  fieldErrors: Partial<Record<"title" | "goal", string>>;
}

export const initialCreateMissionState: CreateMissionState = {
  status: "idle",
  message: "",
  fieldErrors: {},
};
