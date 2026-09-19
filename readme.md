# noqte (nöqtə)

[![Lint](https://github.com/RVFET/noqte/actions/workflows/lint.yml/badge.svg)](https://github.com/RVFET/noqte/actions/workflows/lint.yml)
[![Tests](https://github.com/RVFET/noqte/actions/workflows/test.yml/badge.svg)](https://github.com/RVFET/noqte/actions/workflows/test.yml)
[![Security](https://github.com/RVFET/noqte/actions/workflows/security.yml/badge.svg)](https://github.com/RVFET/noqte/actions/workflows/security.yml)
[![Python Version](https://img.shields.io/badge/python-%3E%3D3.12-3776AB.svg?logo=python&logoColor=white)](https://www.python.org)
[![Ruff](https://img.shields.io/badge/ruff-%3E%3D0.6.0-261230.svg?logo=ruff&logoColor=white)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Git based declarative dotfiles manager and machine bootstrapper. Noqte uses real-file replacement instead of symlinks. Features in-memory file/folder encryption for secrets, multi-OS package syncing, and layered safety rollbacks, all of which is configured from a single `noqte.yaml`.

---


> [!TIP]
> **Check out real-world usage before you commit**
>
> I use nöqtə myself for my cross-platform (Arch Linux & macOS) systems at **[rvfet/dotfiles](https://github.com/rvfet/dotfiles)**. It utilizes all the features of this tool and is being used on real machines. Could be really useful for grasping the philosophy behind it.


## Installation

Requires Python `>=3.12`. Install globally using [`uv`](https://github.com/astral-sh/uv) or `pipx`:

```shell
uv tool install git+https://github.com/rvfet/noqte
# or
pipx install git+https://github.com/rvfet/noqte
```

---

## What It Actually Does

- **Real File Transfer with Mode Preservation**: Rather than managing fragile symlink webs, `noqte` copies real files while recording, preserving, and restoring POSIX permission bits (even on write-protected files).
- **Temporary Elevated Staging (`sudo`)**: Managing root-owned system files outside `$HOME` (e.g. `/etc/environment` or `/etc/daemon.conf`) usually forces people to run their entire tool under `sudo` (breaking `$HOME` paths). `noqte` runs entirely unprivileged: when it hits a `PermissionError`, it stages that specific file into an isolated temporary folder, executes an elevated `sudo cp`, and purges the stage immediately.
- **In-Memory `age` Encryption (Files & Directories)**: Marks sensitive targets with `encrypted: true` using Rust `rage` bindings (`pyrage`). Single files are encrypted directly; entire directories (like `~/.ssh`) are packed into an in-memory gzipped tar stream and encrypted into a single `.encrypted` file. **Plaintext never touches the disk in transit**, and file names, directory trees, and secret counts are never leaked to Git.
- **Toggleable Safety Net (Local + Git)**:
  - *Local*: Bundles whatever is currently on your system into a timestamped `.tar.gz` archive under `~/.dotfiles-backups` before modifying anything.
  - *Git Snapshot*: Before deploying changes, creates an isolated `backup-<timestamp>` branch in your repository, commits your host's pre-modification state, pushes it to your remote, and switches back to your original branch.
  - *Zero bloat*: Both mechanisms can be turned off globally or via flags if you prefer running lean.
- **Package Delta Engine**: Queries installed packages to calculate the difference between your manifest and your machine, installing only what is missing. It runs pre-flight updates before installing to prevent broken partial upgrades on rolling distros.

---

## Comparison with Other Approaches

| Approach | File Mechanism | Secret Encryption | Package Management | `/etc` / System Files | Safety & Rollback |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **noqte** | Mode-preserving copy | In-memory `age` (files & dirs) | Built-in delta (`pacman`, `brew`, `flatpak`, `ir`, dead simple to add more) | Isolated `sudo` staging | Auto `.tar.gz` + Git snapshot branch (can be disabled) |
| **chezmoi** | Templated copy | `age`, `gpg`, password managers | Via custom run scripts | Via root run scripts | Interactive diff + file backup |
| **dotstate** | Automated symlinks | None (requires private repo) | Tool tracking (`brew`, `cargo`, etc.) | `$HOME` only | Pre-op local backups |
| **GNU Stow** | Symlink tree | None | None | Must run entire tool as root | None (manual) |
| **Bare Git** | In-place worktree | None (unless git-crypt) | None | `$HOME` only | Manual git stash / checkout |
| **Shell Scripts** | Ad-hoc `cp` / `ln` | Manual | Sequential shell lists | Shell `sudo` commands | Whatever you scripted |

---

### Honest Breakdown of the Trade-offs

* **`chezmoi`** is the powerhouse for complex templating (Go templates) and password-manager integration (1Password, Bitwarden), but has a steep learning curve and doesn't do native package deltas (delegates to shell scripts).
* **`dotstate`** offers a modern Rust TUI, profile inheritance, and basic CLI tool tracking, but relies on symlinks, lacks secret encryption, and cannot touch system paths outside `$HOME`.
* **`GNU Stow`** has zero dependencies and is universally available, but symlinks break easily with atomic file saves, it lacks any notion of packages or secrets, and managing `/etc/` requires running all of Stow as `root`.
* **`Bare Git ($HOME)`** avoids third-party tools, but turns your entire home directory into a Git tree where an accidental `git clean -fd` is catastrophic, and you cannot encrypt secrets or touch `/etc/`.
* **`Custom Scripts`** give absolute freedom, but turn into unmaintainable spaghetti, lack rollback handling, and aren't cross-platform idempotent without hundreds of lines of boilerplate.
* **`noqte`** is deliberately opinionated: real file copying with permission preservation, isolated `sudo` staging for `/etc/`, RAM-only `age` encryption for public repos, dual-layer rollbacks, and declarative package deltas across multiple managers (requires Python 3.12+ and `uv`).

---

## Quickstart

### 1. Initialize Your Repository
`noqte.yaml` is where configuration happens. It is simple, declarative, and covers practical everyday use cases:

```yaml
# Path to your dotfiles repository
repo_path: "."

settings:
  local_backups: true        # Create local archive at ~/.dotfiles-backups prior to changes
  git_backups: true          # Create snapshot branch (backup-{datetime}) in repo before to-host
  # `branch_cleanup` auto-prunes historical backup branches to prevent branch sprawl (~25 branches max/year).
  # Preserves all work done today, compresses previous days/weeks to single milestones,
  # and keeps 1 archive per month. Recommended to leave as default if you are unsure what this means.
  branch_cleanup:
    enabled: true            # Auto-prune backup branches. If false, branches accumulate indefinitely
    protect_today: true      # Never delete branches created today
    retain_daily: 7          # Keep 1 branch per day for the last 7 days (prunes same-day duplicates)
    retain_weekly: 4         # Keep 1 branch per week for the last 4 weeks
    retain_monthly: 12       # Keep 1 branch per month for the last 12 months
  preflight: true            # Run system upgrade before installing to avoid partial-upgrade breakage

packages:
  # Standard package, available on all package managers as is
  - name: "eza"

  # Package with different name on macOS (pacman: choose, brew: choose-rust)
  - name: "choose"
    mac: "choose-rust"

  # GUI application (brew cask on macOS)
  - name: "ghostty"
    mac:
      cask: true

  # Package that's only available on one OS
  - name: "inotify-tools"
    os: ["linux"]

  # Flatpak package (with macOS cask fallback)
  - name: "chat.simplex.simplex"
    manager: "flatpak"
    mac:
      name: "simplex"
      cask: true

  # GitHub release binary installed directly via 'ir' (install-release)
  - name: "https://github.com/starship/starship"
    manager: "ir"

configs:
  # Standard dotfile
  - name: ".zshrc"
    dest: "~/.zshrc"

  # Directory with file-type glob filtering
  - name: "yazi"
    dest: "~/.config/yazi"
    include:
      - "**/*.{toml,yaml,yml,lua}"

  # Non-destructive directory sync (merges files without wiping untracked local plugins)
  - name: "micro/plug"
    dest: "~/.config/micro/plug"
    overwrite: false
    include:
      - "**/*.{yaml,yml,lua,json}"
      - "**/help/"

  # System file outside $HOME (automatically uses elevated sudo staging only for this file)
  - name: "system/daemon.conf"
    dest: "/etc/daemon.conf"
    os: ["linux"]

  # Encrypted secret file (saved in repo as configs/.zshenv.encrypted)
  - name: ".zshenv"
    dest: "~/.zshenv"
    encrypted: true

  # Encrypted directory (bundled in-memory as tar.gz + age; saved as configs/.zsh.encrypted; structure and metadata fully hidden)
  - name: ".zsh"
    dest: "~/.zsh"
    encrypted: true
```

### 2. Pull Existing Configs from Your Machine
`from-host`, as the name suggests, collects current configuration files from your current machine (referred as `host`):
```shell
cd ~/dotfiles
noqte configs from-host
```
If an entry has `encrypted: true`, you will be prompted for an encryption passphrase upfront. Files are encrypted and written to `configs/` with a `.encrypted` extension.

### 3. Deploying or Bootstrapping a Machine
On any machine (new or existing), clone your repository and run:
```shell
# Optional: audit what would change first
noqte pkgs install --dry-run
noqte configs to-host --dry-run

# Run package installation and deploy your configs
noqte pkgs install
noqte configs to-host

# Note: -c / --config flag can be used if noqte.yaml is outside the current directory
```
`to-host` decrypts secret files/directories in memory, unpacks them to their destinations, creates safety backups, and deploys everything declaratively. You have full control over what gets merged, overwritten, or excluded.

---

## CLI Reference

### Configs Layer (`noqte configs`)

| Command | What it actually does |
| :--- | :--- |
| `noqte configs to-host` | Deploys **repository configurations to your host system**. Automatically backs up existing host files locally and snapshots them to a remote Git backup branch before overwriting (if not disabled). |
| `noqte configs from-host` | Collects live system configurations **from your host into the repository** `configs/` directory, encrypting any targets marked with `encrypted: true`. |
| `noqte configs clear` | Deletes tracked configs from the repository `configs/` folder and prunes any empty parent directory skeletons left behind. |

**Flags:**
* `--dry-run`: Previews all transfer, decrypt, and copy actions without touching files.
* `--no-local-backup`: Skips local `.tar.gz` archive generation.
* `--no-git-backup`: Skips the remote Git snapshot branch.
* `-c, --config <path>`: Custom configuration path (defaults to `./noqte.yaml` or `~/.config/noqte/noqte.yaml`).

---

### Packages Layer (`noqte pkgs`)

| Command | What it actually does |
| :--- | :--- |
| `noqte pkgs install` | Computes the missing delta across configured package managers, runs a pre-flight system upgrade to avoid partial-upgrade breakage (can be disabled), and installs missing packages. |

**Flags:**
* `-m, --manager <name>`: Restricts execution to specific package manager(s) (supports repeated flags or comma-separated lists, e.g., `-m pacman,flatpak`). Bypasses unselected managers. Can be repeated also, e.g., `-m ir -m flatpak`, will do same thing as `-m ir,flatpak`.
* `--dry-run`: Checks installed state across all managers and renders a terminal table of satisfied vs. missing packages with the exact shell commands that would run.
* `--no-preflight`: Skips the system upgrade step.
---

### Shell Completions

Generate native completions for `bash`, `zsh`, or `fish`:
```shell
noqte --install-completion
```

---

## FAQ

<details>
<summary>Why use this over GNU Stow, bare git repos, or custom shell scripts?</summary>

- **GNU Stow** relies on symlinks. Symlinks break when applications atomic-replace configs on save, Stow cannot manage `/etc/` or system files without running the entire tool as root, and it has zero native secret encryption or package management.
- **Bare git repos (`git --git-dir=$HOME/.cfg`)** pollute `$HOME`, make accidental `git clean -fd` commands catastrophic, track runtime caches that apps dump into config folders, and cannot encrypt files individually or manage software packages.
- **Custom shell scripts** are rarely idempotent, lack proper rollback handling, break across different OSes, and turn into unmaintainable spaghetti over time.
- **noqte** copies real files, handles non-destructive merging (`overwrite: false`), uses automated `sudo` staging only when hitting permission walls, manages packages and dotfiles under one declarative schema, and encrypts secrets in RAM.
</details>

<details>
<summary>What specific problems does noqte solve?</summary>

1. **Permission isolation without root pollution**: You never run `noqte` under `sudo`. If an operation targets a root-owned file like `/etc/environment` or `/etc/daemon.conf`, it stages that file in memory and escalates via `sudo cp` strictly for that single file.
2. **Toggleable double-layer safety nets with GFS cleanup**: Every mutating command creates a local `.tar.gz` archive in `~/.dotfiles-backups`. `to-host` also creates an isolated Git snapshot branch of what your machine had before overwriting, automatically pruned by a Grandfather-Father-Son retention policy (`branch_cleanup`) to prevent branch sprawl. Both layers are toggleable in `settings` or via `--no-local-backup` and `--no-git-backup` flags.
3. **Public dotfile security**: Encrypts sensitive configs in memory so you can make your entire repository public on GitHub without redacting keys, managing `.gitignore` hacks, or maintaining awkward private forks.
4. **Declarative package deltas**: Installs only what's missing across system package managers (`pacman`, `brew`), sandboxed desktop apps (`flatpak`), and release binaries (`ir`), with pre-flight updates to prevent broken dependencies on rolling distros.
</details>

<details>
<summary>Who is this project for?</summary>

Built primarily for:
- **Multi-machine/os users** (e.g. Linux workstation + macOS laptop) who want a unified, cross-platform manifest without duplicating config files.
- Users who want to **instantly spin up a new machine** from scratch in a declarative, predictable way without relying on opaque community install scripts.
- **Power users (and larpers)** who want to make their dotfiles public on GitHub while keeping sensitive configs (API tokens, SSH directories, VPN profiles, private shell history) cryptographically secure in the same tree.
- Anyone who wants effortless rollback ergonomics to recover from broken configs. Everything is archived locally and committed to backup branches before changes occur.
</details>

<details>
<summary>How does encryption work for private keys, credentials, and directories?</summary>

Setting `encrypted: true` on an entry uses `age` (rust implementation) passphrase encryption (via `pyrage`):
- **Single files**: Encrypted in RAM and saved as `configs/<name>.encrypted`.
- **Directories** (e.g. `~/.ssh`, `~/.gnupg`): Packed into an in-memory gzipped tarball and encrypted into a single `configs/<name>.encrypted` artifact.
- **No plaintext hits the disk**, and Git never sees your private file names, internal directory structures, or keys.
- You type your passphrase once per command run (or supply `NOQTE_PASSPHRASE` in headless/CI environments), and `to-host` decrypts and unpacks everything directly to destination paths.
</details>

<details>
<summary>Can I add other package managers?</summary>

Yes. While `pacman`/`paru`, Homebrew (formulae + casks), `flatpak`, and `ir` (install-release) are the currently established backends, the package engine is built around an extensible `PackageManager` base class. Adding support for `apt`, `dnf`, `cargo`, or any other tool requires a python file implementing just a single isolated class with four methods (`is_available`, `preflight`, `get_installed`, `install`). PRs adding new package managers are welcome and encouraged.
</details>

---

## Contributing

Contributions are welcome and encouraged.

If you have ideas for new package managers, platform fixes, or improvements, feel free to open a PR or an issue.

Before submitting a pull request, its recommended to ensure your changes pass all local quality checks to reduce conflicts:

```shell
# Linting & Formatting
uv run ruff check .
uv run ruff format --check .

# Test Suite
uv run pytest

# Security Audit
uv run bandit -c pyproject.toml -r .
```

**A note on code quality:** If you lack the time or skills to implement a feature cleanly yourself, **please open an issue instead**. A clear, thoughtful feature request or bug report is infinitely more valuable than submitting untested, unreviewed, completely AI-generated pull requests. If you submit a PR, make sure you understand the code, tested it against a real filesystem, and kept it clean.