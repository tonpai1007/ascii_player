# CI template

GitHub App tokens in some environments cannot create files under
`.github/workflows`. To enable CI, copy the workflow into place:

```bash
mkdir -p .github/workflows
cp ci/github-actions-ci.yml .github/workflows/ci.yml
```

The workflow runs the test suite on Python 3.9 and 3.12, plus a ruff pass for
syntax/undefined-name errors.
