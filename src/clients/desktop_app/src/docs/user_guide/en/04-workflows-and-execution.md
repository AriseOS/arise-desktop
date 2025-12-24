## 4. Workflows and Execution

### 4.1 Workflows List

The **Workflows** area shows all workflows you have created:

- Each entry includes a name, status, and last run time.
- You can open a workflow to view details or run it.

### 4.2 Workflow Details

In a workflow detail view you can typically:

- Inspect the steps and logic of the workflow.
- Adjust input parameters where supported.
- Start a new run of the workflow.

### 4.3 Monitoring a Run

When you start a run you can open the **live execution** or **monitor** view:

- Watch step-by-step progress.
- See which step is currently running.
- Stop or cancel a run if necessary.

### 4.4 Viewing Results

After a run finishes you can open the **execution result**:

- See whether the run succeeded or failed.
- Inspect logs and outputs.
- Jump back to the workflow for adjustments.

### 4.5 AI Changes and Script Generation Time

When you ask Ami to modify a workflow or generate one from a recording, the app may need time to:

- Call AI models to reshape or optimize the workflow definition.
- Generate helper scripts, such as scraper agents that interact with web pages.

You might see loading indicators or a "preparing" state before the workflow is ready to run. The time required depends on:

- The length and complexity of your recording or existing workflow.
- How many times you have asked the AI to refine the workflow.

Similarly, when starting a run, Ami may spend a short period preparing or updating scripts before visible steps begin to execute. This is expected; you can watch progress from the monitor or live execution views.

### 4.6 Using AI to Modify an Existing Workflow

In addition to generating workflows from recordings or descriptions, you can ask AI to help **inspect and fix** an existing workflow.

The typical pattern is:

1. **Open the workflow detail view.**
2. Open the AI-assisted editing or conversation panel for this workflow (if available in your version).
3. Start a short conversation where you:
   - Ask what the current workflow does: for example, "Explain the steps in this workflow".
   - Describe the expected result vs. the actual behavior: for example, "Step 2 only saves price, but I also need stock".
   - Point out where it ran incorrectly: for example, "On some pages this step fails with a missing element error".
4. Let the system propose changes. AI may:
   - Adjust one or more steps (for example, update a scraper step to capture extra fields).
   - Update data requirements, conditions, or error handling.
   - Suggest that you re-run or single-step test the updated workflow.

You can iterate in this conversational loop:

- Run or test the workflow.
- If something is still wrong, tell AI what happened and what you expected instead.
- Accept or reject the suggested edits based on your needs.

