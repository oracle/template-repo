# OGHO template compliance workflow

> **Status:** Draft
>
> **Audience:** Oracle GitHub repository owners, maintainers, and organization administrators
>
> **Applies to:** Repositories in the `github.com/oracle` organization

## Purpose

The OGHO template compliance workflow gives repository owners early feedback when a pull request does not conform to the required Oracle GitHub repository template. It runs the same class of repository-template checks described by the GitHub Compliance Audit Service (GCAS), but runs them directly in GitHub Actions against the repository and revision being reviewed.

The workflow is intended to:

- identify template-compliance problems before a pull request is merged;
- provide file-specific GitHub error annotations and a job summary;
- give existing repositories a reusable check without copying validation logic; and
- support centralized enforcement through an Oracle organization ruleset.

This workflow covers **template checks only**. It does not generate an SBOM, scan dependencies for vulnerabilities, or verify business approvals. Those remain separate GCAS dependency-check capabilities.

## Checks performed

| Area | Requirement |
| --- | --- |
| Repository name | Uses lowercase letters, digits, and single dashes. |
| Default branch | Is named `main`. |
| Required files | `LICENSE.txt`, `README.md`, and `SECURITY.md` exist at the repository root with the exact filename and case. `CONTRIBUTING.md` is optional by default so repositories can inherit Oracle's organization-wide community health file. |
| License format | `LICENSE.txt` contains printable ASCII text and LF line endings. |
| README | Contains a level-one project title and the Installation, Documentation, Examples, Help, Contributing, Security, and License sections. `How to Run` and `Getting Started` are accepted alternatives to `Installation`. |
| Contributing guide | When a local `CONTRIBUTING.md` is present, it contains a level-one title; the Opening Issues, Contributing Code, Pull Request Process, and Code of Conduct sections; and a link to the Oracle Contributor Agreement application. |
| Security policy | `SECURITY.md` is byte-for-byte identical to the canonical policy bundled with the selected action version. |

## Implementation

The implementation is maintained in `oracle/template-repo`:

- Composite action: `.github/actions/ogho-template-check/action.yml`
- Validator: `.github/actions/ogho-template-check/check.py`
- Canonical security policy: `.github/actions/ogho-template-check/templates/SECURITY.md`
- Template-repository workflow: `.github/workflows/ogho-template-compliance.yml`

The action uses Bash and Python's standard library. It does not install dependencies or execute application code from the repository being inspected.

## Using the workflow in another repository

### Repositories created from `oracle/template-repo`

If the action directory and workflow are present in the new repository, the included workflow uses the action locally:

```yaml
- name: Run OGHO template checks
  uses: ./.github/actions/ogho-template-check
```

No additional setup is required beyond enabling GitHub Actions.

### Existing repositories

Existing repositories should reference the centrally maintained action rather than copying the validator. Create `.github/workflows/ogho-template-compliance.yml` with the following content:

```yaml
name: OGHO template compliance

on:
  pull_request:
  merge_group:

permissions:
  contents: read

jobs:
  validate:
    name: Validate repository template
    runs-on: ubuntu-latest
    steps:
      - name: Check out repository
        uses: actions/checkout@v7

      - name: Run OGHO template checks
        uses: oracle/template-repo/.github/actions/ogho-template-check@<FULL_COMMIT_SHA>
```

Replace `<FULL_COMMIT_SHA>` with an approved commit containing a released version of the action. Pinning the full commit SHA prevents an unreviewed change to the action from changing the code executed by repository workflows.

The workflow runs when a pull request is opened or updated and when GitHub creates a merge group. It intentionally does not run on `push` or `workflow_dispatch`. Repository or organization rules must require pull requests and block direct changes to the protected default branch; the pull request check then prevents noncompliant changes from merging. The `merge_group` event ensures that the same required check runs for repositories using a merge queue.

The workflow needs only `contents: read`. It does not require repository or organization secrets.

### Action inputs

Normal GitHub workflows do not need to set any inputs.

| Input | Default | Purpose |
| --- | --- | --- |
| `path` | `.` | Repository path to inspect, relative to `GITHUB_WORKSPACE`. |
| `repository-name` | GitHub event metadata | Overrides the repository name, primarily for local testing or nonstandard execution contexts. |
| `default-branch` | GitHub event metadata | Overrides the default branch, primarily for local testing or nonstandard execution contexts. |
| `contributing-policy` | `optional` | Controls local `CONTRIBUTING.md` validation: `optional` allows inheritance and validates a local file when present; `required` requires and validates a root-level file; `disabled` skips it entirely. |

Example for checking a repository staged in a subdirectory:

```yaml
- uses: oracle/template-repo/.github/actions/ogho-template-check@<FULL_COMMIT_SHA>
  with:
    path: checked-out-repository
```

Repositories that must maintain their own contributing guide can require it explicitly:

```yaml
- uses: oracle/template-repo/.github/actions/ogho-template-check@<FULL_COMMIT_SHA>
  with:
    contributing-policy: required
```

The default `optional` policy does not fetch or validate Oracle's inherited file. It allows the local file to be absent because GitHub can display the organization-wide `CONTRIBUTING.md` from `oracle/.github`. If a repository provides its own root-level file, the action validates it. Use `disabled` only when neither local nor inherited contributing guidance should be part of this check.

## Organization-wide enforcement

Adding a workflow to individual repositories provides visibility, but it does not prevent a repository administrator from removing or disabling that workflow. Organization-wide enforcement should use a centrally maintained **ruleset workflow**.

### Central ruleset workflow

Store the following workflow in `.github/workflows/required-ogho-template-compliance.yml` in an Oracle-owned source repository. `oracle/template-repo` can be used as the source while it remains publicly accessible.

```yaml
name: Required OGHO template compliance

on:
  pull_request:
  merge_group:

permissions:
  contents: read

jobs:
  validate:
    name: Validate repository template
    if: true
    runs-on: ubuntu-latest
    steps:
      - name: Check out repository
        uses: actions/checkout@v7

      - name: Run OGHO template checks
        uses: oracle/template-repo/.github/actions/ogho-template-check@<FULL_COMMIT_SHA>
```

The `merge_group` trigger is required for repositories using a merge queue. A ruleset workflow supports `pull_request`, `pull_request_target`, and `merge_group`; `push` and `workflow_dispatch` are not enforcement triggers. Do not use `pull_request_target`: the validator needs only the pull request contents and a read-only token.

### Organization ruleset configuration

An Oracle organization owner, or a user with the organization ruleset-management permission, should:

1. Open the Oracle organization settings and select **Repository → Rulesets**.
2. Create an organization branch ruleset.
3. Target the intended repositories:
   - select **All repositories** for full organization coverage; or
   - initially select repositories by custom property or a limited repository list for a staged rollout.
4. Target the **default branch**, not every branch.
5. Enable **Require a pull request before merging**.
6. Enable **Require workflows to pass before merging**.
7. Select the source repository and `required-ogho-template-compliance.yml` workflow.
8. Limit bypass access to a designated break-glass team or provisioning GitHub App. Repository administrators should not receive general bypass access.
9. Start the ruleset in **Evaluate** mode and review the rule insights.
10. Remediate or explicitly exempt noncompliant repositories, then move the ruleset to **Active**.

Organization rulesets layer with existing repository rulesets and branch-protection rules. A repository can add stricter rules but cannot weaken the organization rule.

### Organization prerequisites

Before activation, confirm that:

- GitHub Actions is enabled for all targeted repositories.
- Organization Actions policy permits `actions/checkout` and the action under `oracle/template-repo`.
- GitHub-hosted runners are available, or self-hosted runners provide Bash, Python 3.10 or later, and a current Actions runner compatible with `actions/checkout@v7`.
- The source workflow repository has suitable visibility. A public workflow can target repositories of any visibility; an internal workflow can target internal and private repositories; a private workflow can target private repositories.
- If the source repository is internal or private, **Actions → General → Access** allows access from repositories in the Oracle organization.
- The workflow does not use `cancel-in-progress` concurrency, which is unsuitable for ruleset-required workflows.

### New repository creation

A required workflow cannot run while a repository is being initialized. To avoid blocking repository creation:

- select **Do not require workflow checks on creation**, if available; or
- grant narrowly scoped bypass permission to the approved repository-provisioning GitHub App or team.

The new repository becomes subject to the ruleset after initialization.

## Recommended rollout

1. **Validate the action:** Run the action in `oracle/template-repo` and a representative set of public and private repositories.
2. **Publish an approved version:** Merge the action and record its full commit SHA.
3. **Pilot voluntary adoption:** Add the consumer workflow to several repositories and collect false-positive or usability feedback.
4. **Evaluate centrally:** Create the organization ruleset in Evaluate mode using a limited target set or repository custom property.
5. **Remediate:** Update noncompliant repository files and resolve runner or policy restrictions.
6. **Expand targeting:** Move from the pilot set to all applicable Oracle repositories.
7. **Enforce:** Change the ruleset to Active and monitor rule insights and support requests.

## Understanding failures

| Failure | Resolution |
| --- | --- |
| Invalid repository name | Rename the repository using lowercase words separated by dashes. Coordinate redirects and dependent automation before renaming. |
| Default branch is not `main` | Rename the default branch and update branch-protection, build, deployment, and documentation references. |
| Required file is missing | Add the exact root-level filename from `oracle/template-repo`. To require a repository-local `CONTRIBUTING.md`, set `contributing-policy: required`; otherwise it is optional. |
| Invalid `LICENSE.txt` format | Convert the file to printable ASCII and LF line endings. Do not replace the approved license text without the appropriate review. |
| README section is missing | Add the missing heading and relevant project content. Installation may instead be titled How to Run or Getting Started. |
| CONTRIBUTING section or OCA link is missing | Restore the required section or the `https://oca.opensource.oracle.com` reference. |
| `SECURITY.md` differs | Replace it with the canonical file bundled with the pinned action version. Project-specific security guidance belongs in product documentation, not as a modification to this policy. |
| Default branch cannot be determined | Ensure the workflow is running from a GitHub repository event, or supply the `default-branch` input for a nonstandard execution context. |

The action reports all detected failures in one run so repository owners can remediate them together.

## Maintaining the action

Changes to the Oracle repository template require coordinated action maintenance:

1. Update the root template files in `oracle/template-repo`.
2. Update the validator's required sections or accepted aliases as needed.
3. When `SECURITY.md` changes, update the bundled canonical copy in the same pull request.
4. Run the validator against the template repository and intentional negative fixtures.
5. Merge the reviewed change and record the new full commit SHA.
6. Update the central ruleset workflow to the new SHA.
7. Use Evaluate mode or a limited target set when a new requirement may affect existing repositories.

The source repository and central workflow should themselves be protected with required reviews and a CODEOWNERS rule owned by the OGHO administrators.

## References

- GitHub Compliance Audit Service documentation (Oracle internal; available in the OGHO Confluence space)
- [Oracle template repository](https://github.com/oracle/template-repo)
- [GitHub: Create a default community health file](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/creating-a-default-community-health-file)
- [GitHub: Require workflows to pass before merging](https://docs.github.com/en/enterprise-cloud@latest/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets#require-workflows-to-pass-before-merging)
- [GitHub: Create rulesets for repositories in an organization](https://docs.github.com/en/organizations/managing-organization-settings/creating-rulesets-for-repositories-in-your-organization)
- [GitHub: Troubleshoot ruleset workflows](https://docs.github.com/en/enterprise-cloud@latest/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/troubleshooting-rules#troubleshooting-ruleset-workflows)
- [GitHub: Control Actions and reusable workflow access](https://docs.github.com/en/organizations/managing-organization-settings/disabling-or-limiting-github-actions-for-your-organization)
