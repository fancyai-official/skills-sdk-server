# Global Interaction Protocol — AskUserQuestion

This document defines mandatory interaction rules that apply to **ALL skills and workflows**. Every skill MUST follow these rules without exception.

## Core Rule

**When you need user input, choices, confirmations, or decisions — ALWAYS use the `AskUserQuestion` tool.** Never present options as plain text lists, numbered choices, or bullet points that the user has to manually type a response to. The user should be able to **click** to respond.

---

## Hard Constraints (Tool Limits)

**Each question supports a maximum of 4 options.** This is a hard technical limit of the `AskUserQuestion` tool — providing 5+ options will cause an error.

When you have more than 4 choices, use one of these strategies (**prefer Strategy B**):
- **Strategy B (preferred)**: Split into two sequential `AskUserQuestion` calls — first ask a broad category (≤4 groups), then ask the specific item within the selected group (≤4 items). This preserves all options as clickable buttons without losing any.
- **Strategy A**: Pick the top 3-4 most relevant options + add one `{ "label": "Other", "value": "other", "type": "custom_input" }` option so the user can type an unlisted choice. Use when options don't group naturally.
- **Strategy C**: Group similar choices under a single label with a description that lists the variants (e.g., label: "European cities", description: "Milan, Paris, Florence — specify in next step"). Use as a last resort.

**Do NOT attempt to pass 5+ options in a single question — it will fail.**

---

## Mandatory Interaction Points

You MUST call `AskUserQuestion` in the following scenarios. No exceptions.

### Pattern 1: Multiple Choice (selecting from options)

When presenting 2+ options for the user to choose from (e.g., style, city, color, direction, treatment, plan variant).

```
AskUserQuestion:
  questions:
    - question: "Which [category] do you prefer?"
      header: "[Category Name]"
      options:
        - label: "Option A", description: "Brief explanation of option A"
        - label: "Option B", description: "Brief explanation of option B"
        - label: "Option C", description: "Brief explanation of option C"
        - label: "Other", value: "other", type: "custom_input"
```

**Rules:**
- **Maximum 4 options per question** (hard limit — see above)
- Describe each option clearly in the `description` field
- Keep labels short (1-5 words), put details in description
- If the user might want something not listed, add a custom input option: `{ "label": "Other", "value": "other", "type": "custom_input" }`
- Present all related choices in ONE `AskUserQuestion` call with multiple questions when possible — don't force the user to answer one question at a time

### Pattern 2: Confirmation Before Execution

Before any resource-consuming action (image generation, video generation, API calls, script execution, report generation), present the plan and wait for explicit user confirmation.

```
AskUserQuestion:
  questions:
    - question: "Ready to proceed?"
      header: "Confirm"
      options:
        - label: "Go ahead", description: "Looks good, start now"
        - label: "Adjust", description: "I want to change something first"
```

**Rules:**
- HARD STOP after calling `AskUserQuestion` — do NOT proceed until the user responds
- If the user selects "Adjust", incorporate their feedback and re-confirm with `AskUserQuestion` before proceeding
- This applies to: image generation, video generation, batch processing, report uploads, any Bash execution that consumes credits or produces output

### Pattern 3: Analysis Review

After presenting analysis results, design specs, research findings, or any structured output that the user needs to verify before the next step.

```
AskUserQuestion:
  questions:
    - question: "Does this analysis look accurate?"
      header: "Review"
      options:
        - label: "Confirmed", description: "Analysis is correct, continue"
        - label: "Needs correction", description: "Something needs to be adjusted"
```

**Rules:**
- Present your analysis/findings in the conversation FIRST, then call `AskUserQuestion`
- Wait for confirmation before using the analysis as input for subsequent steps

### Pattern 4: Parameter Collection

When you need the user to provide or confirm multiple parameters before starting a workflow (e.g., season, target audience, brand, product details, style preferences).

```
AskUserQuestion:
  questions:
    - question: "Which season?"
      header: "Season"
      options:
        - label: "Spring/Summer", description: "..."
        - label: "Fall/Winter", description: "..."
    - question: "Target audience?"
      header: "Audience"
      options:
        - label: "Gen Z", description: "..."
        - label: "Millennial", description: "..."
        - label: "Other", value: "other", type: "custom_input"
```

**Rules:**
- Batch related questions into a single `AskUserQuestion` call
- Use `type: "custom_input"` for open-ended parameters
- After collecting parameters, summarize them back to the user and confirm (Pattern 2) before executing

### Pattern 5: Final Delivery Confirmation

After all outputs are generated and presented, before ending the workflow or declaring completion.

```
AskUserQuestion:
  questions:
    - question: "Are you satisfied with the results?"
      header: "Final Review"
      options:
        - label: "Looks great!", description: "I'm happy with the results"
        - label: "Redo some", description: "Some outputs need to be regenerated"
        - label: "Start over", description: "I want to try a different direction"
```

### Pattern 6: Pre-workflow Check

At the beginning of a workflow, when you need to confirm whether previous settings/configurations are still valid or have changed.

```
AskUserQuestion:
  questions:
    - question: "Any updates to the current settings?"
      header: "Pre-check"
      options:
        - label: "No changes", description: "Continue with existing settings"
        - label: "Yes, updates", value: "updates", type: "custom_input"
```

### Pattern 7: File Upload Request

When you need the user to upload files (product images, reference photos, garment photos, documents, etc.).
Use `AskUserQuestion` with the **header starting with `[FILE_UPLOAD:accept_type]`**. The server will convert this into a file upload component on the frontend.

**Header format:** `[FILE_UPLOAD:accept_type] Display Label`

Common accept types:
- `image/*` — all image formats
- `image/png,image/jpeg` — PNG and JPG only
- `video/*` — all video formats
- `.pdf,.docx` — PDF and Word documents
- omit the accept type for no restriction: `[FILE_UPLOAD] Any Files`

```
AskUserQuestion:
  questions:
    - question: "Please upload your product images (JPG/PNG, up to 5 images)"
      header: "[FILE_UPLOAD:image/*] Product Images"
      options:
        - label: "Upload", description: "Supports JPG, PNG formats"
```

**Rules:**
- **Maximum 4 options per question** still applies (but typically only 1 "Upload" option is needed)
- The `question` field should describe what files are needed, including format and quantity requirements
- The first option's `description` is passed to the frontend as a human-readable hint
- After upload, you will receive file URLs as comma-separated strings in the answer. Use these URLs in subsequent steps (e.g., as `img_urls` for image generation, as `--images` for analysis scripts)
- This pattern works both at workflow start (initial file upload) and mid-workflow (supplementary uploads)

---

## Strictly Forbidden Behaviors

1. **NEVER present choices as plain text lists and expect the user to type their selection.** Always use `AskUserQuestion` with clickable options.

2. **NEVER proceed to the next step after saying "waiting for user confirmation" without actually calling `AskUserQuestion` and receiving a response.** The phrase "waiting for user confirmation" or "PAUSE" in your workflow means you MUST call `AskUserQuestion` and stop.

3. **NEVER skip confirmation before resource-consuming actions.** Every image generation, video generation, batch API call, or report upload MUST be preceded by an `AskUserQuestion` confirmation.

4. **NEVER combine a confirmation request with immediate execution.** Call `AskUserQuestion`, wait for the response, THEN execute.

5. **NEVER present a single "OK" button as the only option.** Always provide at least one alternative (e.g., "Adjust", "Go back", "Try different approach").

6. **NEVER ask the user to upload/provide/drop/submit files or images using only plain text.** If your response asks for files (e.g., "Drop your product images", "Please upload", "Send me the reference photos"), you MUST call `AskUserQuestion` with Pattern 7 (`[FILE_UPLOAD:accept]` header) at the end of your message. Plain text file requests without a corresponding `AskUserQuestion` call are forbidden — the user has no upload button to click otherwise.

---

## How This Works With Skill-Specific Instructions

- If a SKILL.md defines specific `AskUserQuestion` calls for particular steps (e.g., exact questions, exact options), follow those specific instructions — they take priority.
- If a SKILL.md says "wait for user confirmation" or "PAUSE" but does NOT specify an `AskUserQuestion` call, you MUST still use `AskUserQuestion` following the patterns above.
- If a workflow step naturally requires user input but neither this document nor the SKILL.md explicitly mentions it, use your judgment to apply the appropriate pattern above.

---

## Quick Reference: When to Call AskUserQuestion

| Situation | Pattern | Required? |
|-----------|---------|-----------|
| User must choose from 2+ options | Pattern 1: Multiple Choice | **YES** |
| About to generate images/videos/reports | Pattern 2: Confirmation | **YES** |
| Presenting analysis for user review | Pattern 3: Analysis Review | **YES** |
| Need multiple inputs from user | Pattern 4: Parameter Collection | **YES** |
| All outputs complete, ending workflow | Pattern 5: Final Delivery | **YES** |
| Starting workflow, checking for updates | Pattern 6: Pre-workflow Check | Recommended |
| Need user to upload files (images, videos, docs) | Pattern 7: File Upload | **YES** |
| Any text that says "PAUSE" or "waiting for user confirmation" | Pattern 2 or 3 | **YES** |
