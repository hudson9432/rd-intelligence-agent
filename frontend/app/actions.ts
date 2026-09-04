"use server";

import { revalidatePath } from "next/cache";

import { createMission } from "@/lib/api";
import type { CreateMissionState } from "@/lib/mission-form";

/** Mirrors the `max_length=200` bound on `ResearchMissionBase.title`. */
const TITLE_MAX_LENGTH = 200;

export async function createMissionAction(
  _previous: CreateMissionState,
  formData: FormData,
): Promise<CreateMissionState> {
  const title = String(formData.get("title") ?? "").trim();
  const goal = String(formData.get("goal") ?? "").trim();

  const fieldErrors: CreateMissionState["fieldErrors"] = {};
  if (!title) {
    fieldErrors.title = "A mission title is required.";
  } else if (title.length > TITLE_MAX_LENGTH) {
    fieldErrors.title = `Keep the title within ${TITLE_MAX_LENGTH} characters.`;
  }
  if (!goal) {
    fieldErrors.goal = "Describe the research goal.";
  }

  if (Object.keys(fieldErrors).length > 0) {
    return {
      status: "error",
      message: "Fix the highlighted fields and try again.",
      fieldErrors,
    };
  }

  const result = await createMission({ title, goal });

  if (!result.ok) {
    return {
      status: "error",
      message: result.error.message,
      fieldErrors: {},
    };
  }

  revalidatePath("/");

  return {
    status: "success",
    message: `Mission "${result.data.title}" created.`,
    fieldErrors: {},
  };
}
