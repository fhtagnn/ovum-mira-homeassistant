# Security policy

## Supported versions

Security fixes are applied to the latest published release line.

## Reporting a vulnerability

Please do not publish credentials, Modbus login codes, serial numbers, private
network addresses, or full Home Assistant diagnostics in a public issue.

Use GitHub's **Report a vulnerability** action on the repository's **Security**
page when it is available. If that action is unavailable, open a public issue
containing only the title **Private security contact requested** and no technical
details. The maintainer will arrange a private follow-up channel.

Ordinary integration bugs that contain no sensitive information should use the
public bug-report form instead.

## Device-safety note

This integration can write persistent controller parameters. The implementation
uses change-only writes and read-back verification for persistent `P_*`
parameters to reduce unnecessary flash writes. Nevertheless, users remain
responsible for safe heat-pump configuration and operation.
