import { useMemo } from "react";
import { motion } from "framer-motion";
import { STEP_CHIPS, PARALLEL_IDS, AI_IDS } from "../lib/constants";
import type { StepChipState } from "../types";

interface StepChipsProps {
  currentStep: string;
  allDone?: boolean;
}

function deriveStates(
  step: string,
  allDone: boolean
): Record<string, StepChipState> {
  const s: Record<string, StepChipState> = {};
  for (const chip of STEP_CHIPS) s[chip.id] = "idle";

  if (allDone) {
    for (const chip of STEP_CHIPS) s[chip.id] = "done";
    return s;
  }

  if (step.includes("Cache hit")) {
    s.cache = "done";
  } else if (step.includes("Gathering intelligence")) {
    for (const id of PARALLEL_IDS) s[id] = "active";
  } else if (step.includes("company profile")) {
    for (const id of PARALLEL_IDS) s[id] = "done";
    s.ai1 = "active";
  } else if (step.includes("sales insights")) {
    for (const id of PARALLEL_IDS) s[id] = "done";
    s.ai1 = "done";
    s.ai2 = "active";
  } else if (step.includes("Scoring lead")) {
    for (const id of PARALLEL_IDS) s[id] = "done";
    s.ai1 = "done";
    s.ai2 = "done";
    s.ai3 = "active";
  }

  return s;
}

export default function StepChips({ currentStep, allDone = false }: StepChipsProps) {
  const states = useMemo(
    () => deriveStates(currentStep, allDone),
    [currentStep, allDone]
  );

  return (
    <div className="steps-grid">
      {STEP_CHIPS.map((chip) => {
        const state = states[chip.id];
        return (
          <div
            key={chip.id}
            className={`step-chip${state !== "idle" ? ` ${state}` : ""}`}
          >
            {state === "active" ? (
              <motion.span
                className="step-dot"
                animate={{ opacity: [1, 0.25, 1] }}
                transition={{ repeat: Infinity, duration: 1.2, ease: "easeInOut" }}
              />
            ) : (
              <span className="step-dot" />
            )}
            {chip.label}
          </div>
        );
      })}
    </div>
  );
}
