import { describe, expect, it } from "vitest";
import { linkCitations, splitExplanation } from "./answer-content";

describe("splitExplanation", () => {
  it("separates a trailing explanation paragraph", () => {
    const r = splitExplanation("Employees get 28 days [1].\n\nExplanation: This is generous.");
    expect(r).toEqual({ answer: "Employees get 28 days [1].", explanation: "This is generous." });
  });

  it("handles bold markers", () => {
    const r = splitExplanation("Fact [2].\n**Explanation:** reasoning");
    expect(r.explanation).toBe("reasoning");
  });

  it("returns the content unchanged without an explanation", () => {
    expect(splitExplanation("Just facts [1].")).toEqual({ answer: "Just facts [1].", explanation: null });
  });
});

describe("linkCitations", () => {
  it("links valid citation numbers", () => {
    expect(linkCitations("A [1] B [2, 3]", 3)).toBe("A [1](#cite-1) B [2](#cite-2)[3](#cite-3)");
  });

  it("leaves out-of-range numbers and existing links alone", () => {
    expect(linkCitations("X [9] and [1](http://a)", 2)).toBe("X [9] and [1](http://a)");
  });
});
