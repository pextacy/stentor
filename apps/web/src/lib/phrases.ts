import type { AlertIntent, Instruction, Meta } from "./api";

const ACTION_BY_VERB: Record<string, AlertIntent["action"]> = {
  evacuate: "evacuate_now", prepare: "prepare_to_evacuate", shelter: "shelter_in_place", move: "move_to_higher_ground",
  stay: "stay_indoors", avoid: "avoid_area", boil: "boil_water", monitor: "monitor", all_clear: "all_clear",
};

export const isActionVerb = (verb: string) => verb in ACTION_BY_VERB;

const kinds = (phs: string[]) => phs.map((p) => p[1]).sort().join("");

function fill(tpl: string, phs: string[], mapping: Record<string, string>): string {
  let out = tpl;
  for (const p of phs) out = out.replace(`{${p[1]}}`, mapping[p] ?? p);
  return out;
}

/** The English sentence an instruction becomes, or null if no approved wording exists
 *  (for example after the operator negates an instruction that only has a positive form). */
export function instructionSentence(ins: Instruction, mapping: Record<string, string>, pb: Meta["phrasebook"]): string | null {
  const phs = ins.placeholders ?? [];
  const action = ACTION_BY_VERB[ins.verb];
  if (action) {
    if (ins.negated) return null;
    const key = kinds(phs) + (ins.object === "to" && phs.length ? ":to" : "");
    const tpl = pb.actions[action]?.[key];
    return tpl ? fill(tpl, phs, mapping) : null;
  }
  const spec = pb.instructions[ins.verb + (ins.object ? `:${ins.object}` : "")];
  if (!spec) return null;
  const variant = (ins.negated ? "neg" : "pos") + (phs.length ? `|${kinds(phs)}` : "");
  const tpl = spec[variant];
  return tpl ? fill(tpl, phs, mapping) : null;
}

export const human = (s: string) => s.replace(/_/g, " ").replace(":", " ");
