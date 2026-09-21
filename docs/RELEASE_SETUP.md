# Repository and release workflow

The repository is `fhtagnn/ovum-mira-homeassistant`. Release decisions remain a maintainer action; development changes are not tagged or published automatically.

## Before a release

1. Keep feature development on a review branch until the maintainer has checked the code and documentation.
2. Verify that `manifest.json`, `INTEGRATION_VERSION`, and the intended Semantic Versioning number match.
3. Run the test workflow, Ruff, and Hassfest successfully on the review branch.
4. Review `CHANGELOG.md`, the user documentation, English strings, and German translations.
5. Verify the neutral project branding in `custom_components/ovum_mira/brand/`. Do not use the OVUM corporate logo without permission.
6. Perform an in-place upgrade test on an existing Home Assistant config entry when persistent storage or entity/statistics semantics changed. Take a Home Assistant backup first.
7. Confirm that existing entity IDs, unique IDs, long-term statistics, and integration-managed stored counters remain attached after the upgrade.
8. Only after maintainer approval, merge the reviewed branch into `main`.
9. Let the workflows run again on `main`.
10. Create the Git tag and GitHub release only after the maintainer explicitly approves publication. Mark preview versions as prereleases; stable versions must not be marked as prereleases.
11. Verify independently that the tag and release point to the tested `main` commit and that HACS detects the intended version.

## HACS testing and distribution

The public repository contains `hacs.json` and can be installed as a HACS custom integration through the button in `README.md` or by adding the repository URL manually. Keep the HACS and Hassfest workflows green before sharing a release or submitting the repository to the HACS default list.

A useful update-path test is:

1. Install one release from GitHub/HACS without deleting the existing Home Assistant config entry.
2. Publish a later compatible version.
3. Verify that HACS detects the newer version.
4. Upgrade in place and restart Home Assistant if requested.
5. Verify storage migration, entity identity, and long-term statistics after the update.

## Versioning

The manifest follows Semantic Versioning. Stable public releases started with `0.1.0`. Use patch versions for compatible fixes, minor versions for compatible features, and prerelease suffixes when additional hardware validation is intentionally required.

Do not create or move a release tag merely to test branch code. A tag should identify a reviewed release commit on `main`. After a release is complete, delete merged development and temporary publication branches; retain `main`, immutable tags, and GitHub releases.
