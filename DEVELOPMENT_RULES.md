# Development Rules

These rules apply to future work on this repository.

## Source of truth
- The GitHub `main` branch is the authoritative source for the current project state.
- Source code and project files must be stored unpacked and directly browsable in the repository.
- Do not store the project source as a ZIP archive in the repository.
- Create a ZIP only when the user explicitly asks for a transfer/download package.

## Change workflow
- Read the current repository state before making code changes.
- For substantial or experimental work, use a dedicated branch and keep `main` stable.
- Preserve previous versions through Git history, tags, and releases rather than duplicate source ZIPs.
- Avoid destructive replacement of a known working version without a recoverable Git reference.

## Validation
- Run the available automated tests before treating a change as ready.
- Windows standalone builds are produced by GitHub Actions.
- A successful build must at minimum compile/package successfully and pass the repository's smoke checks.
- Test artifacts may be temporary; stable versions should be identifiable by version/tag.

## Deliverables
- GitHub keeps the source, history, tests, workflows, and version references.
- EXE files may be provided as build artifacts or stable release assets.
- ZIP packages are generated only on explicit request and are not the normal working format.

## Working principle
For future maintenance, start from GitHub rather than reconstructing the project from chat copies or ZIP archives.
