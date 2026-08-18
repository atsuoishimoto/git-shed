# History

## 0.1.0 (unreleased)

- Initial release.
- Commands: `sync` / `add` / `link` / `unlink` / `remove` / `status` /
  `list` / `path` / `open`.
- Shed definitions in `~/.git-shed/config.toml`, storage under
  `~/.git-shed/sheds/<name>` (root overridable via `GIT_SHED_ROOT`).
- Repository remotes resolved to canonical identities and matched against
  shed patterns (`*`, `**`, case-insensitive).
- Links created as `repo/.shed/<name>` (symlinks on Linux/macOS, directory
  junctions on Windows); `/.shed/` is kept in `.git/info/exclude`.
