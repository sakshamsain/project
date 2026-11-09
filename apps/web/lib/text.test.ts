import assert from "node:assert/strict";
import { test } from "node:test";
import { findQuote, rupee } from "./text.ts";

test("a stray rupee glyph before an amount reads as ₹", () => {
  assert.equal(rupee("loans aggregated C 1,23,745.05 crore (net)"), "loans aggregated ₹ 1,23,745.05 crore (net)");
  assert.equal(rupee("Paid-up Capital : H361.8 crore"), "Paid-up Capital : ₹361.8 crore");
  assert.equal(rupee("Note C 12 refers to"), "Note C 12 refers to");
  assert.equal(rupee("TCS and HCL"), "TCS and HCL");
});

test("a quote is found across line breaks and curly quotes", () => {
  const page = "We operate in an environment\nmarked by “intense competition” in traditional\nservices, rapid technology";
  const quote = 'We operate in an environment marked by "intense competition" in traditional services';
  const hit = findQuote(page, quote);
  assert.ok(hit);
  assert.equal(page.slice(hit[0], hit[0] + 10), "We operate");
  assert.ok(page.slice(hit[0], hit[1]).endsWith("services"));
  assert.equal(findQuote(page, "nothing like this appears here at all"), null);
  assert.equal(findQuote(page, "two words"), null);
});
