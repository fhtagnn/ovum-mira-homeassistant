# Repository and release workflow

The repository is `fhtagnn/ovum-mira-homeassistant`. Release decisions remain a maintainer action; development changes are not tagged or published automatically.

## Before a beta release

1. Keep feature development on a review branch until the maintainer has checked the code and documentation.
2. Verify that `manifest.json`, `INTEGRATION_VERSION`, and the intended Semantic Versioning number match.
3. Run the test workflow, Ruff, and Hassfest successfully on the review branch.
4. Review `CHANGELOG.md`, the user documentation, English strings, and German translations.
5. Verify the neutral project branding in `custom_components/ovum_mira/brand/`. Do not use the OVUM corporate logo without permission.
6. Perform an in-place upgrade test on an existing Home Assistant config entry when persistent storage or entity/statistics semantics changed. Take a Home Assistant backup first.
7. Confirm that existing entity IDs, unique IDs, long-term statistics, and integration-managed stored counters remain attached after the upgrade.
8. Only after maintainer approval, merge the reviewed branch into `main`.
9. Let the workflows run again on `main`.
10. Create the Git tag and GitHub prerelease only after the maintainer explicitly approves publication.

## HACS testing

The repository contains `hacs.json` and can be added as a HACS custom integration once the repository visibility and GitHub access are suitable for the intended testers. For broad community testing and normal public HACS distribution, the repository should be public.

A useful update-path test is:

1. Install one beta from GitHub/HACS without deleting the existing Home Assistant config entry.
2. Publish a later beta.
3. Verify that HACS detects the newer version.
4. Upgrade in place and restart Home Assistant if requested.
5. Verify storage migration, entity identity, and long-term statistics after the update.

## Versioning

The manifest follows Semantic Versioning. The public beta line starts at `0.1.0-beta.1`; compatible prerelease iterations use subsequent beta identifiers such as `0.1.0-beta.2`.

Do not create or move a release tag merely to test branch code. A tag should identify a reviewed release commit on `main`.
