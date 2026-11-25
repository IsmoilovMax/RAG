/** Helpers for presenting model answers (citation links, explanation split). */

const EXPLANATION = /(^|\n)[ \t]*(?:\*\*|__)?Explanation:?(?:\*\*|__)?:?[ \t]*/i;
const CITATION = /\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\](?!\()/g;

export interface SplitAnswer {
  answer: string;
  explanation: string | null;
}

/**
 * The system prompt asks the model to put anything not stated directly in the
 * documents in a final paragraph starting with "Explanation:". We split it out
 * so the UI can visually separate retrieved facts from model reasoning.
 */
export function splitExplanation(content: string): SplitAnswer {
  const match = EXPLANATION.exec(content);
  if (!match || match.index === undefined) return { answer: content, explanation: null };
  const answer = content.slice(0, match.index).trim();
  const explanation = content.slice(match.index + match[0].length).trim();
  if (!answer) return { answer: content, explanation: null };
  return { answer, explanation: explanation || null };
}

/** Turn [1] / [1, 2] markers into markdown links the renderer shows as chips. */
export function linkCitations(text: string, maxIndex: number): string {
  return text.replace(CITATION, (whole, nums: string) => {
    const parts = nums
      .split(",")
      .map((n) => Number(n.trim()))
      .filter((n) => n >= 1 && n <= maxIndex);
    if (!parts.length) return whole;
    return parts.map((n) => `[${n}](#cite-${n})`).join("");
  });
}
