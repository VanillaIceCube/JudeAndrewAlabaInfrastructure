const assert = require("node:assert/strict");
const test = require("node:test");
const verifyBranchRules = require("../../actions/verify-branch-rules/verify-branch-rules");

function probe(rules, fields) {
  const github = {
    rest: { repos: { getBranchRules() {} } },
    paginate: async (endpoint, input) => {
      assert.equal(endpoint, github.rest.repos.getBranchRules);
      assert.equal(input.repo, "notoli");
      assert.equal(input.branch, "main");
      return rules.map(type => ({ type }));
    },
    graphql: async () => ({ __type: { inputFields: fields.map(name => ({ name })) } }),
  };
  return verifyBranchRules({ github, context: { repo: { owner: "VanillaIceCube", repo: "notoli" } }, core: { info() {} } });
}

test("the branch probe requires protected checks and the exact-head auto-merge API", async () => {
  await probe(["required_status_checks"], ["expectedHeadOid"]);
  await assert.rejects(probe([], ["expectedHeadOid"]), /protected main-branch/);
  await assert.rejects(probe(["required_status_checks"], []), /atomic head guard/);
});
