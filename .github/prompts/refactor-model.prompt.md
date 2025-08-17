---
mode: 'agent'
tools: ['codebase', 'usages', 'vscodeAPI', 'problems', 'changes', 'testFailure', 'terminalSelection', 'terminalLastCommand', 'openSimpleBrowser', 'fetch', 'findTestFiles', 'searchResults', 'githubRepo', 'extensions', 'runTests', 'editFiles', 'runNotebooks', 'search', 'new', 'runCommands', 'runTasks', 'copilotCodingAgent', 'activePullRequest', 'getPythonEnvironmentInfo', 'getPythonExecutableCommand', 'installPythonPackage', 'configurePythonEnvironment']
description: 'Refactor SQLModel classes to match OpenAPI schemas'
---
Your goal is to refactor or add SQLModel classes in app/models.py based on the OpenAPI spec schemas.

Reference these instructions: [general-coding.instructions.md](../instructions/general-coding.instructions.md)

Steps:
1. Identify the target model (e.g., Greenhouse, Zone) from ${selection} or user input.
2. Compare current model in app/models.py to spec schema (e.g., add min_temp_c to GreenhouseBase).
3. Update Base and table classes: Add fields with Field(...), enums, relationships with back_populates and cascade.
4. Remove deprecated (e.g., direct sensor FKs in Zone; use SensorZoneMap instead).
5. Ensure UUID PK, JSON fields for dicts/lists (sa_type=JSON).
6. Output only the updated code snippet for models.py.

Example: For Greenhouse, add fields like min_vpd_kpa: float = Field(default=0.3).

Validate: Matches spec types/defaults; no breaking changes to existing relationships.
