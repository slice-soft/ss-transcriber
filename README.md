# ss-transcriber

Desktop application and CLI for transcribing YouTube or local audio/video sources.

## Release Flow

- Feature work lands in `release` through squash merges.
- Pushes to `release` generate prereleases such as `v0.2.0-rc.1`.
- After QA on the generated desktop artifacts, run the `Promote Release` workflow to open the PR from `release` to `main`.
- Stable releases are created only after the promotion merge into `main`.
