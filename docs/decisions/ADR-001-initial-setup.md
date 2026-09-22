# ADR-001: Initial Project Setup and Structure

**Status:** Accepted (partially superseded)
**Date:** 2026-09-23
**Author:** Project Setup

> **Note added 2026-09-23:** decision 6 (npm as package manager) assumed a Node.js backend and is superseded by [ADR-007](ADR-007-backend-stack.md), which proposes Python + FastAPI. The repository structure and environment-configuration decisions recorded here remain in force.

## Context

StudentOS project required initial repository setup and structural foundation to support future development phases.

## Decision

1. Initialize Git repository locally
2. Create standard directory structure for frontend, backend, and testing
3. Establish environment configuration patterns using .env files
4. Create documentation structure with decision record tracking
5. Set up GitHub as primary version control platform
6. Use npm as the primary package manager

## Rationale

- **Version Control:** Git and GitHub provide industry-standard collaboration and CI/CD integration
- **Directory Structure:** Clear separation of concerns (frontend, backend, tests) supports scalability
- **Environment Management:** .env.example + .gitignore pattern provides secure credential management
- **Documentation:** ADR pattern and README enable knowledge transfer and decision tracking
- **Package Management:** npm is the default Node.js package manager and well-integrated with the ecosystem

## Consequences

### Positive
- Clear project structure supports parallel development
- Environment variable pattern prevents accidental credential exposure
- ADR documentation provides historical context for future decisions
- GitHub integration enables CI/CD and team collaboration

### Negative
- Initial setup overhead
- Multiple configuration files to maintain
- Directory structure may need refinement as requirements clarify

## Alternatives Considered

1. Start with minimal structure (REJECTED) - Would require significant refactoring as project grows
2. Use monorepo tools like Lerna/Yarn Workspaces (REJECTED) - Unnecessary complexity for project stage
3. Use different version control (REJECTED) - GitHub selected for team familiarity and integration

## Notes

Future decisions regarding technology stack, deployment strategy, and architectural patterns will be documented in subsequent ADRs.
