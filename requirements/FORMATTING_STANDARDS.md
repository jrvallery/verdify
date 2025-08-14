# Project Verdify Documentation Standards

## Markdown Formatting Guidelines

This document establishes consistent formatting standards across all Project Verdify requirements documentation.

## 1. Header Structure

```markdown
# Document Title (H1 - one per document)

## Major Section (H2)

### Subsection (H3)

#### Sub-subsection (H4)
```

## 2. Bullet Points

**Use standard markdown bullets:**

```markdown
- Primary bullet point
  - Sub-bullet point
    - Sub-sub-bullet point

- **Bold emphasis**: For important concepts
- `Code references`: For technical terms, field names, endpoints
```

**Avoid:**
- Mixed bullet styles (-, o, -, *)
- Unicode bullets (-)
- Tab-indented bullets

## 3. Code Blocks

**JSON Examples:**
```json
{
  "field_name": "value",
  "nested": {
    "sub_field": 123
  }
}
```

**HTTP Requests:**
```http
POST /api/endpoint
Content-Type: application/json

{
  "request": "data"
}
```

**Inline code:** Use `backticks` for field names, endpoints, values.

## 4. Tables

```markdown
| Column 1 | Column 2 | Column 3 |
|----------|----------|----------|
| Data 1   | Data 2   | Data 3   |
| Data 4   | Data 5   | Data 6   |
```

## 5. Sections and Organization

### Standard Document Structure:

```markdown
# Document Title

## Overview
Brief description of the document's purpose.

## Related Documentation
Links to other specification files.

## 1. Major Topic
### 1.1 Subtopic
### 1.2 Another Subtopic

## 2. Another Major Topic
### 2.1 Subtopic
```

## 6. API Documentation Format

```markdown
#### Endpoint Name
**METHOD /path** (Auth Type)

Description of what the endpoint does.

**Request:**
```json
{
  "request": "example"
}
```

**Response 200:**
```json
{
  "response": "example"
}
```

**Errors:**
- E400_BAD_REQUEST: Description
- E401_UNAUTHORIZED: Description
```

## 7. Requirements and Lists

**Use consistent formatting:**

```markdown
### Requirements

- ✅ **MUST**: Critical requirement
- ⚠️  **SHOULD**: Recommended requirement  
- ℹ️  **MAY**: Optional requirement
```

## 8. Cross-References

**Internal links:**
```markdown
See [Section 2.1](#21-subtopic) for details.
See [DATABASE.md](./DATABASE.md) for schema details.
```

## 9. Emphasis and Styling

- **Bold**: For important concepts, field names in descriptions
- *Italic*: For emphasis, first-time terminology
- `Code`: For technical terms, field names, values, endpoints
- > **Note**: For important callouts

## 10. Consistency Rules

1. **Field names**: Always use `snake_case` and backticks
2. **IDs**: Always specify format (UUIDv4, device_name pattern)
3. **Timestamps**: Always specify ISO 8601 UTC format
4. **HTTP status codes**: Always include both number and name (200 OK)
5. **Error codes**: Always use E000_NAME format with backticks

## Files to Standardize

1. ✅ OVERVIEW.md - Completed
2. 🔄 API.md - In progress  
3. 🔄 CONFIGURATION.md - In progress
4. 🔄 CONTROLLER.md - Needs formatting
5. 🔄 PLANNER.md - Needs formatting
6. 🔄 DATABASE.md - Needs formatting
7. 🔄 AUTHENTICATION.md - Needs formatting
8. 🔄 GAPS.md - Needs formatting
