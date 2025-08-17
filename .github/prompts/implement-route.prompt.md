---
mode: 'agent'
tools: ['codebase', 'usages', 'vscodeAPI', 'problems', 'changes', 'testFailure', 'terminalSelection', 'terminalLastCommand', 'openSimpleBrowser', 'fetch', 'findTestFiles', 'searchResults', 'githubRepo', 'extensions', 'runTests', 'editFiles', 'runNotebooks', 'search', 'new', 'runCommands', 'runTasks', 'copilotCodingAgent', 'activePullRequest', 'getPythonEnvironmentInfo', 'getPythonExecutableCommand', 'installPythonPackage', 'configurePythonEnvironment']
description: 'Implement or refactor FastAPI routes based on OpenAPI spec'
---
Implement or refactor a FastAPI route in app/api/routes/{file}.py to match the OpenAPI spec endpoint.

Reference: [general-coding.instructions.md](../instructions/general-coding.instructions.md)

Input: Endpoint path (e.g., /greenhouses/{id}/config/publish POST) from ${input:endpoint}.

Approach:
1. Use APIRouter with prefix="/api/v1", tags from spec (e.g., [Config]).
2. Add dependencies: get_current_user for UserJWT, get_current_device for DeviceToken.
3. Use Pydantic models for request/response (e.g., ConfigPublishResult).
4. Implement logic: For POST, handle dry_run, materialize config from DB, compute ETag.
5. Add features: ETags (If-None-Match), rate limiting (slowapi), compression (gzip).
6. Update crud/{model}.py for DB operations if needed.
7. Output: Updated route code, including imports and router mounting in api/main.py if new file.

Constraints: Align with spec responses (e.g., 201 for publish with headers); use existing deps.py.

Success: Code handles spec parameters, security, and returns matching schemas.
