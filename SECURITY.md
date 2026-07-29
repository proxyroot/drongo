# Security Policy

## Supported versions

`gato` is pre-1.0; security fixes land on the latest released version. Please
always test against the most recent release.

| Version | Supported |
| ------- | --------- |
| latest  | ✅        |
| older   | ❌        |

## Reporting a vulnerability

Please **do not** open a public issue for security vulnerabilities.

Instead, report privately via GitHub's
[private vulnerability reporting](https://github.com/proxyroot/gato/security/advisories/new)
or email **security@proxyroot.com**.

Include, if possible:

- A description of the vulnerability and its impact
- Steps to reproduce
- Affected version(s)

We aim to acknowledge reports within 72 hours and to provide a remediation
timeline after triage.

## Scope note

`gato` is a **testing** tool that fakes cloud APIs in-process. It is not
intended for production use and should never hold real secrets or serve
production traffic. The standalone `gato server` binds to `localhost` by default
and performs no authentication - do not expose it to untrusted networks.
