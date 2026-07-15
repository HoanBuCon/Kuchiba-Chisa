# Architecture Freeze

The current architecture is considered stable.

No additional interfaces, wrappers, service layers or dependency abstractions should be introduced unless one of the following conditions is met:

- a new Infrastructure boundary appears
- multiple implementations become necessary
- testing cannot be reasonably achieved otherwise
- a documented architecture review approves the change

Future refactoring should prioritize simplicity over theoretical flexibility.