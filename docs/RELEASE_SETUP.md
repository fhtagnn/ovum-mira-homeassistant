# One-time repository setup before publishing

The maintainer GitHub username is configured as `fhtagnn`.

Before pushing to GitHub:

1. Choose the repository name, recommended: `ovum-mira-homeassistant`.
2. The recommended repository name is `ovum-mira-homeassistant`; the manifest and README currently point to `https://github.com/fhtagnn/ovum-mira-homeassistant`.
3. If a different repository name is used, update the documentation and issue-tracker URLs.
4. Update `SECURITY.md` with a private security contact method if desired.
5. Verify the neutral project branding in `custom_components/ovum_mira/brand/` and replace it only
   with artwork you have rights to use. Do not use the OVUM corporate logo without permission.
6. Create a public GitHub repository, enable Issues, add a short description, and add topics such as
   `home-assistant`, `hacs`, `ovum`, `mira`, `heat-pump`, and `modbus`.
7. Push the repository and let the HACS and Hassfest workflows pass.
8. Create a GitHub prerelease tagged `v0.1.0-beta.1`.
9. Test installation by adding the repository to HACS as a custom integration.
10. After beta testing, publish `v0.1.0`. Use `0.x` minor releases for compatible feature additions and patch releases for fixes; reserve `v1.0.0` for a mature, stable public interface.

The `manifest.json` version follows Semantic Versioning. The first public line starts at `0.1.0-beta.1`.
