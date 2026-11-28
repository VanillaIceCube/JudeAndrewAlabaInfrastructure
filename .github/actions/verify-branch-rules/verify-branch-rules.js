"use strict";

module.exports = async function verifyBranchRules({ github, context, core }) {
  // API 2026-03-10 requires Metadata: read for this endpoint:
  // https://docs.github.com/en/rest/repos/rules#get-rules-for-a-branch
  const rules = await github.paginate(github.rest.repos.getBranchRules, {
    ...context.repo, branch: 'main', per_page: 100,
    headers: { 'X-GitHub-Api-Version': '2026-03-10' },
  });
  if (!rules.some((rule) => rule.type === 'required_status_checks')) {
    throw new Error('Expected protected main-branch status rules.');
  }
  core.info('Live branch rules are readable with the read-only workflow token.');
  const schema = await github.graphql('query { __type(name: "EnablePullRequestAutoMergeInput") { inputFields { name } } }');
  if (!schema.__type.inputFields.some((field) => field.name === 'expectedHeadOid')) {
    throw new Error('GitHub auto-merge schema lacks the required atomic head guard.');
  }
  core.info('Live GitHub schema supports expectedHeadOid for native auto-merge.');
};
