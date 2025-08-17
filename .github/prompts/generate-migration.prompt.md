---
mode: 'agent'
tools: ['codebase', 'usages', 'vscodeAPI', 'problems', 'changes', 'testFailure', 'terminalSelection', 'terminalLastCommand', 'openSimpleBrowser', 'fetch', 'findTestFiles', 'searchResults', 'githubRepo', 'extensions', 'runTests', 'editFiles', 'runNotebooks', 'search', 'new', 'runCommands', 'runTasks', 'copilotCodingAgent', 'activePullRequest', 'getPythonEnvironmentInfo', 'getPythonExecutableCommand', 'installPythonPackage', 'configurePythonEnvironment']
description: 'Generate Alembic migration for model changes'
---
Generate an Alembic migration script for recent model changes in app/models.py.

Reference: [general-coding.instructions.md](../instructions/general-coding.instructions.md)

Steps:
1. Assume changes from ${selection} (e.g., added fields to Greenhouse).
2. Run conceptual `alembic revision --autogenerate -m "description"` equivalent: Create upgrade/downgrade functions.
3. Handle adds (add_column), renames (alter_column), relationships (create_foreign_key with ondelete='CASCADE').
4. Place in app/alembic/versions/{new_file}.py.
5. Output the full migration file content.

Constraints: Use op from alembic.operations; no actual run—code only.

Validate: Migration applies changes without data loss; matches spec schema evolution.
