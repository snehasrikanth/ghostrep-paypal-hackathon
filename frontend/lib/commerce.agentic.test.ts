import assert from "node:assert/strict";
import test from "node:test";
import { parseBudget, usd } from "./commercePolicy.ts";

test("checkout budget uses exact cents and rejects malformed or excessive values", () => {
  assert.equal(parseBudget("4.99"), 499);
  assert.equal(parseBudget(" 30 "), 3000);
  assert.equal(parseBudget(""), null);
  assert.equal(parseBudget("0"), 0);
  assert.equal(parseBudget("1000.00"), 100000);
  for (const value of ["4.999", "-1", "1e2", "1000.01", "0x10", "NaN", "Infinity", "$30"]) {
    assert.throws(() => parseBudget(value));
  }
});

test("receipt currency formatting preserves catalog cents", () => {
  assert.equal(usd(499), "$4.99");
  assert.equal(usd(1499), "$14.99");
  assert.equal(usd(2999), "$29.99");
});
