# Code signing policy

Free code signing provided by [SignPath.io](https://about.signpath.io), certificate by
[SignPath Foundation](https://signpath.org).

> Status: application to the SignPath Foundation program pending. Until it is approved,
> releases are published unsigned and are marked as such in the release notes.

## What is signed

Only `APPhash.exe`, the program built from the source code of this repository.
Third-party runtime files shipped next to it in the `_internal` folder (the Python runtime
and the libraries listed in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md)) are not
signed with this project's certificate.

## How releases are built

- Every release is built by GitHub Actions on GitHub-hosted runners from a `vX.Y.Z` tag on
  the `main` branch, using [.github/workflows/build.yml](.github/workflows/build.yml).
- The build script, the PyInstaller spec file and the CI configuration are part of this
  repository.
- No binary is built or signed on a developer machine.
- Every signing request is approved manually by an approver.

## Team roles

| Role | Members |
|---|---|
| Committers and reviewers | [Giovanni Ciccarese (@gcblack84)](https://github.com/gcblack84) |
| Approvers | [Giovanni Ciccarese (@gcblack84)](https://github.com/gcblack84) |

Changes proposed by external contributors (pull requests) are reviewed by a committer before
being merged. All team members use multi-factor authentication for GitHub and SignPath.

## Privacy policy

APPhash does not transfer any information to other networked systems. It works entirely
offline on the user's computer, collects no data and contains no telemetry, update checks
or advertising. The files being analysed are opened read-only and never leave the computer.

The third-party components included in the program are used only as local libraries and do
not transmit data either.

## System changes and uninstallation

APPhash is portable: it is not installed, does not modify the system configuration and does
not write to the registry. To remove it, delete its folder.

## Reporting a problem

If you believe a signed release of APPhash violates this policy, please open an
[issue](https://github.com/gcblack84/APPhash/issues) or see [SECURITY.md](SECURITY.md).
