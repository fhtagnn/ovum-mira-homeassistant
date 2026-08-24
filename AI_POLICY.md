# AI-assisted development policy

This project permits AI-assisted software development.

AI tools may be used to help with implementation, refactoring, tests,
documentation, issue analysis, and code review. The project has used OpenAI
ChatGPT during its initial development.

AI output is treated as an untrusted contribution until it has been reviewed by
a human maintainer. In particular:

- a human maintainer is responsible for every release;
- changes that write to the heat-pump controller require human review and tests;
- protocol behavior should be traceable to public documentation, maintainer
  observations, or reproducible device tests;
- generated code must satisfy the same licensing, security, testing, and review
  requirements as human-written code;
- private user data, credentials, serial numbers, and diagnostic exports must
  not be submitted to third-party AI systems without the user's permission.

AI tools are not project maintainers, code owners, or support contacts and must
not be listed as authors of commits unless a human contributor intentionally
chooses to do so under the rules of the hosting platform.
