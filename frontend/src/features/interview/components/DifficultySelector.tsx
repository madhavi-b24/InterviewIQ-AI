import type { RequestedDifficulty } from "../api";

export interface DifficultySelectorProps {
  value: RequestedDifficulty;
  onChange: (value: RequestedDifficulty) => void;
  hasResume: boolean;
}

const OPTIONS: { value: RequestedDifficulty; label: string }[] = [
  { value: "auto", label: "Auto" },
  { value: "easy", label: "Easy" },
  { value: "medium", label: "Medium" },
  { value: "hard", label: "Hard" },
];

/** A native radio group (fieldset/legend/name) rather than a styled
 * button toggle — full keyboard/screen-reader semantics for free, no
 * extra ARIA needed. */
export function DifficultySelector({ value, onChange, hasResume }: DifficultySelectorProps) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="text-sm font-medium text-slate-700">Difficulty</legend>
      <div className="flex flex-wrap gap-2">
        {OPTIONS.map((option) => (
          <label
            key={option.value}
            className={[
              "flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm",
              value === option.value
                ? "border-brand-500 bg-brand-50 text-brand-700"
                : "border-slate-300 text-slate-700 hover:bg-slate-50",
            ].join(" ")}
          >
            <input
              type="radio"
              name="difficulty"
              value={option.value}
              checked={value === option.value}
              onChange={() => onChange(option.value)}
              className="sr-only"
            />
            {option.label}
          </label>
        ))}
      </div>
      <p className="text-xs text-slate-500">
        {value === "auto"
          ? hasResume
            ? "Adapts to your selected resume's gap analysis when available, or starts at medium."
            : "No resume selected — starts at medium."
          : "Starts at your chosen level and adapts as you answer."}
      </p>
    </fieldset>
  );
}
