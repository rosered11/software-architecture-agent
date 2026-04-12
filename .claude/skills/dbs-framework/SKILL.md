---
name: dbs-framework
description: "Use this skill whenever the user wants to create a new skill, build an automation, set up a new workflow, or asks how to structure a skill. Also trigger when the user says 'new skill', 'build a skill', 'create an automation', 'DBS', 'direction blueprints solutions', or mentions wanting to automate a repeating task. This skill provides the DBS framework (Direction, Blueprints, Solutions) for structuring any skill properly. Use it alongside the skill-creator skill when available for the best results."
---

# DBS Framework — Skill Architecture Guide

This skill teaches Claude how to build well-structured skills using the DBS framework. When a user wants to create a new skill, use this framework to guide the architecture decisions before writing any files.

If the skill-creator skill is available, use it for the actual file generation and testing. This skill handles the architectural thinking and structural decisions that come before writing code.

## What DBS Is

DBS stands for Direction, Blueprints, and Solutions. These are three layers that determine how a skill folder is structured. Every skill uses at least one layer. Most use two. Production-level skills use all three.

```
skill-name/
├── SKILL.md              ← DIRECTION (required)
├── references/            ← BLUEPRINTS (optional)
│   ├── [topic].md
│   ├── [topic].md
│   └── examples/
│       └── [example].md
└── scripts/               ← SOLUTIONS (optional)
    ├── [action].py
    └── [action].sh
```

## The Three Layers

### Direction (SKILL.md)
The workflow file. This is the only file that loads when the skill activates. Everything else loads on demand.

Direction contains:
- YAML frontmatter with name and description (description determines when the skill triggers)
- A short overview of what the skill does (2-3 sentences)
- The step-by-step workflow Claude follows to complete the task
- Pointers to specific Blueprints files at the steps that need them
- Pointers to Solutions scripts at the steps that need them
- Hard rules and constraints for the output

Direction should stay under 500 lines. If it's longer, reference material has been included that belongs in Blueprints.

### Blueprints (references/)
The knowledge layer. Business-specific expertise that Claude doesn't have on its own.

Each topic gets its own file inside the references/ folder:
- Voice guides (how the output should sound)
- Pricing documents (what to quote and how to frame it)
- Deliverable structures (exact section-by-section layouts)
- Frameworks and methodologies (proprietary processes)
- Case studies and examples (what good output looks like)
- ICP profiles (who the output is for)
- Style guides (visual or written standards)

Claude only loads the specific Blueprints file needed for the current step. A skill can have 50 pages of Blueprints and Claude only reads the 2 pages relevant to what it's doing right now. This is called progressive disclosure.

### Solutions (scripts/)
The precision layer. Executable code for outputs that must be identical every time.

Use Solutions for:
- Formatted document generation (.docx, .pdf)
- API calls to external services
- Data validation and calculations
- Template rendering
- File format conversion
- Image or visual generation via APIs

Claude handles the thinking and writing using Direction and Blueprints. Solutions scripts handle the precise formatting and output.

## Workflow for Building a New Skill

When the user wants to create a new skill, walk through these steps in order. Present your thinking at each step and get confirmation before moving on.

### Step 1: Define the Task
Ask the user:
- What specific task should this skill automate?
- How often do they do this task?
- What does the input look like? (What information do they provide to start the task?)
- What does the output look like? (What should the finished result be?)
- Is there a command they want to use to trigger it?

Summarize the task in one sentence: "This skill [does what] when [triggered by what] and produces [what output]."

### Step 2: Determine the Layers
Based on what you learned in Step 1, recommend which DBS layers are needed:

**Direction only** — Use when:
- Claude can do the task with just a workflow and its built-in knowledge
- The output is text in the chat, not a formatted file
- No business-specific voice, pricing, or structure is required
- Examples: research briefs, brainstorming sessions, schedule planning, email triage summaries

**Direction + Blueprints** — Use when:
- The output needs to sound like the user (voice guide needed)
- The task requires business-specific knowledge Claude doesn't have (pricing, frameworks, ICP criteria)
- The deliverable follows a specific structure the user has refined (proposal layouts, report formats)
- Consistency of style matters across multiple runs
- Examples: client deliverables, branded content, personalized outreach, structured reports

**Direction + Blueprints + Solutions** — Use when:
- The output needs to be a formatted file (.docx, .pdf, images)
- An external API needs to be called (image generation, data services)
- Calculations or data validation must be precise every time
- The formatting and layout must be identical across runs
- Examples: proposal generators, carousel image creators, invoice builders, data processors

Present your recommendation and explain why. Get confirmation before proceeding.

### Step 3: Plan the Blueprints (if applicable)
If Blueprints are needed, identify what knowledge files are required:
- What does Claude need to know about the user's business that it doesn't already know?
- Does the output need to match a specific voice or tone? → voice guide file
- Does the output follow a specific structure? → structure file
- Does the task involve pricing or packages? → pricing file
- Are there examples of what good output looks like? → examples file
- Does the task serve a specific audience? → ICP profile file

List each proposed Blueprints file with its filename and a one-sentence description of what it contains. Get confirmation.

### Step 4: Plan the Solutions (if applicable)
If Solutions are needed, identify what scripts are required:
- What part of the output needs to be identical every time?
- Is there an external API that needs to be called?
- Is file generation required? What format?
- Are there calculations that must be precise?

List each proposed Solutions script with its filename and what it does. Get confirmation.

### Step 5: Build the Skill
Now build the skill files. If the skill-creator skill is available, hand off to it for the actual file generation, testing, and evaluation. Provide it with all the architectural decisions made in Steps 1-4.

If the skill-creator skill is not available, build the files directly:

1. Create the skill folder with the correct name (kebab-case, lowercase, hyphens only)
2. Write the SKILL.md (Direction) with frontmatter, overview, workflow, reference pointers, and rules
3. Create the references/ folder and write each Blueprints file
4. Create the scripts/ folder and write each Solutions script
5. Present the complete folder structure to the user for review

### Step 6: Test and Refine
Run the skill with 2-3 realistic test prompts. Not "test my skill" but the actual kind of request the user would make in real life.

After each test:
- Does the workflow run in the right order?
- Are the Blueprints loading at the right steps?
- Does the output match what the user expected?
- Are the Solutions producing consistent output?

Adjust based on feedback and test again.

## Naming Rules
- Folder name: kebab-case (lowercase, hyphens only, no spaces, no underscores)
- Skill file: Exactly SKILL.md (case-sensitive)
- No README.md inside the skill folder
- No "claude" or "anthropic" in the skill name
- Description: max 1024 characters, no XML angle brackets
- SKILL.md: under 500 lines

## Description Writing Guide
The description in the YAML frontmatter determines whether Claude activates the skill. It must answer two questions: what does this skill do, and when should Claude use it?

Write descriptions slightly pushy because Claude tends to under-trigger skills. Include:
- What the skill does in plain language
- Specific trigger phrases the user might say
- File types or output formats if relevant
- Contexts where the skill applies

Example: "Generates a structured discovery call prep sheet with research, talking points, and tailored questions. Use when the user mentions 'call prep', 'meeting prep', 'prep for a call', 'discovery call', or asks to prepare for a meeting with a specific person."

## Key Principles
- One skill per task. If a skill handles multiple unrelated jobs, split it into separate skills.
- Direction is the map. It should tell Claude what to do, not teach Claude domain knowledge. Domain knowledge goes in Blueprints.
- Blueprints are modular. One topic per file. If a file covers two unrelated topics, split it.
- Solutions are for precision. Only use scripts for output that must be identical every run. Don't add scripts for things Claude can handle through normal generation.
- Test with real prompts. "Test my skill" is not a test. Use the actual phrasing you'd use on a normal workday.
