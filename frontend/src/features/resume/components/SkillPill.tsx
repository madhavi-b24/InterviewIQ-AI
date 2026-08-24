import { Badge } from "@/components";
import type { SkillOut } from "../api";

export interface SkillPillProps {
  skill: SkillOut;
}

/** One extracted skill — the evidence snippet (the resume text it was
 * detected from) is available as a native tooltip rather than always
 * shown, keeping a skills section scannable at a glance. */
export function SkillPill({ skill }: SkillPillProps) {
  return (
    <Badge variant="brand" title={skill.evidence ?? undefined}>
      {skill.name}
    </Badge>
  );
}
