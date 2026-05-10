# Publishing ContextOps to PyPI

> The PyPI name `contextops` is available as of 2026-05-10. This is a
> step-by-step for the very first publish. After v0.1.0 ships, the
> "subsequent releases" section at the bottom is the short version.

The goal is that once this is done, the README's quickstart can drop
the `git+...` form and say:

```bash
pip install contextops
```

That single line is what makes someone on Hacker News willing to try
the tool.

---

## One-time setup (you do this once, ever)

### 1. Create a PyPI account

- Go to https://pypi.org/account/register/
- Verify the email address.
- **Enable 2FA** (PyPI requires it for any maintainer who publishes).
  Use a TOTP app (1Password, Authy, Google Authenticator).

### 2. Create a project-scoped API token

After v0.1.0 is published you can scope the token to just `contextops`.
For the very first upload, scope is "Entire account":

- https://pypi.org/manage/account/token/
- Token name: `contextops-launch`
- Scope: **Entire account** (will scope down later, see below).
- Copy the token. It starts with `pypi-` and is shown **only once**.

### 3. Save the token in `~/.pypirc`

```bash
cat > ~/.pypirc <<'EOF'
[pypi]
  username = __token__
  password = pypi-AgEI…YOUR-TOKEN-HERE…
EOF
chmod 600 ~/.pypirc
```

Verify nobody else can read it:

```bash
ls -l ~/.pypirc   # expect: -rw------- 1 you  staff  ... ~/.pypirc
```

---

## Publishing v0.1.0 (the launch release)

Pre-flight: you should already have…

- [ ] PR #3 (`contextops fix`) merged into `main`.
- [ ] PR #4 (this branch) merged into `main`.
- [ ] `main` checked out locally and up to date.
- [ ] No uncommitted changes (`git status` clean).

### 1. Tag the release

```bash
git checkout main
git pull origin main
git tag -a v0.1.0 -m "ContextOps v0.1.0 — initial public release"
git push origin v0.1.0
```

### 2. Build the artifacts

```bash
python3 -m venv /tmp/contextops-publish
source /tmp/contextops-publish/bin/activate
pip install --upgrade build twine
python -m build
```

You should see `dist/contextops-0.1.0.tar.gz` and
`dist/contextops-0.1.0-py3-none-any.whl`. Sanity-check them:

```bash
twine check dist/*
# Expect: PASSED for both.
```

### 3. (Optional but recommended) Test on TestPyPI first

```bash
twine upload -r testpypi dist/*
# Username: __token__
# Password: a TestPyPI token (separate account at https://test.pypi.org)

# Then in a fresh venv:
python3 -m venv /tmp/contextops-testpypi
source /tmp/contextops-testpypi/bin/activate
pip install -i https://test.pypi.org/simple/ contextops
contextops --help
deactivate && rm -rf /tmp/contextops-testpypi
```

If TestPyPI looks good, deactivate and continue.

### 4. Upload to PyPI

```bash
twine upload dist/*
```

If `~/.pypirc` is set up, no credential prompt. Otherwise paste the
token when asked.

### 5. Verify the install works on a clean venv

```bash
python3 -m venv /tmp/contextops-pypi-verify
source /tmp/contextops-pypi-verify/bin/activate
pip install contextops
contextops --help
contextops list
deactivate && rm -rf /tmp/contextops-pypi-verify
```

### 6. Update the README quickstart

Once verified live on PyPI, replace the git+ install line with the
canonical PyPI line and commit:

```bash
sed -i.bak 's|pip install git+https://github.com/desmartinguillaume-a11y/contextops|pip install contextops|' README.md
rm README.md.bak

git add README.md
git commit -m "docs: switch quickstart to 'pip install contextops' (PyPI v0.1.0 live)"
git push origin main
```

### 7. Scope the API token down (security)

Now that `contextops` exists on PyPI, the Entire-account token from
step 2 is over-privileged. Replace it:

- https://pypi.org/manage/account/token/
- Revoke the `contextops-launch` token.
- Create a new token: name `contextops-publish`, **scope: Project →
  contextops**.
- Update `~/.pypirc` with the new token.

---

## Subsequent releases (v0.1.1, v0.2.0, …)

```bash
# 1. Bump version in pyproject.toml
# 2. Commit, tag, push
git add pyproject.toml
git commit -m "chore: bump version to 0.1.1"
git tag -a v0.1.1 -m "ContextOps v0.1.1"
git push origin main v0.1.1

# 3. Rebuild and upload
rm -rf dist/ build/ *.egg-info
python -m build
twine check dist/*
twine upload dist/*
```

(After enough releases, automate this with a `release.yml` GitHub
Action that triggers on tag push and uses a Trusted Publisher
configuration — no token needed in CI. Out of scope for v0.1.0.)

---

## What was already verified locally

On the working branch, before opening PR #4:

- `python -m build` produces both wheel and sdist without errors.
- `twine check dist/*` returns `PASSED` for both.
- The wheel installs cleanly in a fresh venv.
- `contextops version` returns `0.1.0` after install from the wheel.

So if `pyproject.toml` doesn't change between now and tagging, the
launch-day build should just work.
