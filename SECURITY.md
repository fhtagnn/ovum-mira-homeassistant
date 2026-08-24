# Security policy

## Supported versions

Security fixes are applied to the latest published release line.

## Reporting a vulnerability

Please do not publish credentials, Modbus login codes, serial numbers, private
network addresses, or full Home Assistant diagnostics in a public issue.

Before the repository is published, replace the placeholder security contact in
`RELEASE_SETUP.md` with the maintainer's preferred private contact method.

## Device-safety note

This integration can write persistent controller parameters. The implementation
uses change-only writes and read-back verification for persistent `P_*`
parameters to reduce unnecessary flash writes. Nevertheless, users remain
responsible for safe heat-pump configuration and operation.
