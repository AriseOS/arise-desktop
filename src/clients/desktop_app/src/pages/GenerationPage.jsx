import React, { useState, useEffect, useRef } from 'react';
import Icon from '../components/Icons';
import WorkflowGenerationProgress from '../components/WorkflowGenerationProgress';
import { api } from '../utils/api';
import '../styles/GenerationPage.css';

/**
 * Generation Page - Direct Workflow generation from task description or Recording
 *
 * Uses the new WorkflowBuilder architecture to generate Workflow directly
 * without the intermediate MetaFlow step.
 */
function GenerationPage({ session, onNavigate, showStatus, params = {} }) {
  const userId = session?.username;

  // Extract params
  const recordingId = params.recordingId || null;
  const recordingName = params.recordingName || '';

  // Input state - pre-fill from params if available
  const [taskDescription, setTaskDescription] = useState(params.taskDescription || "");
  const [userQuery, setUserQuery] = useState(params.userQuery || "");

  // Generation state
  const [isGenerating, setIsGenerating] = useState(false);
  const [currentStage, setCurrentStage] = useState('analyzing');
  const [stageStatuses, setStageStatuses] = useState({});
  const [generationLogs, setGenerationLogs] = useState([]); // Detailed activity log
  const [generationError, setGenerationError] = useState(null);
  const [workflowResult, setWorkflowResult] = useState(null);

  // Simulation Refs
  const simulatedIntervalRef = useRef(null);

  // Auto-start generation if we have a recordingId
  React.useEffect(() => {
    if (recordingId && !isGenerating && !workflowResult) {
      handleGenerateWorkflow();
    }
  }, [recordingId]);

  // --- Helper Methods ---

  const addLog = (type, message) => {
    const timestamp = new Date().toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
    setGenerationLogs(prev => [...prev, { type, message, timestamp }]);
  };

  const updateStage = (stageId, status) => {
    setStageStatuses(prev => ({
      ...prev,
      [stageId]: { ...prev[stageId], status }
    }));
  };

  // --- Simulation Logic ---
  // Generates organic "micro-steps" based on the current stage
  const startSimulation = (stage) => {
    // Clear existing interval
    if (simulatedIntervalRef.current) clearInterval(simulatedIntervalRef.current);

    const microSteps = {
      analyzing: [
        "Reading the page content to understand the context...",
        "I see a list of items here, let me figure out the structure...",
        "Looking for the best way to extract this information...",
        "Identifying the interactive elements like buttons and links...",
        "Checking how the data is organized on the screen...",
        "Found some potential patterns, verifying them now..."
      ],
      understanding: [
        "I think I understand what you want to do...",
        "Mapping your request to the available actions...",
        "Double-checking if any specific filters are needed...",
        "Ensuring I capture all the relevant details for you...",
        "This looks like a data extraction task, setting up the parser..."
      ],
      generating: [
        "Designing the workflow steps now...",
        "Adding a loop to go through each item one by one...",
        "Making sure the selectors are robust against page changes...",
        "Optimizing the navigation path for efficiency...",
        "Almost there, just polishing the logic..."
      ],
      validating: [
        "Running a quick simulation to ensure it works...",
        "Verifying that the data flows correctly between steps...",
        "Checking for any potential edge cases...",
        "Everything looks good, finalizing the workflow..."
      ]
    };

    const steps = microSteps[stage] || [];
    if (steps.length === 0) return;

    let stepIndex = 0;

    const runStep = () => {
      if (stepIndex >= steps.length) {
        if (simulatedIntervalRef.current) clearInterval(simulatedIntervalRef.current);
        return;
      }

      // Add a simulated log
      const msg = steps[stepIndex];
      // 50% chance to show 'thinking' vs 'analyzing'
      const type = Math.random() > 0.5 ? 'thinking' : 'analyzing';

      // Only add if we represent the current stage roughly
      // (Actual state is controlled by backend, this is just decoration)
      addLog(type, msg);
      stepIndex++;

      // Randomize next interval for organic feel - SLOWER now (2s - 4.5s)
      const nextDelay = 2000 + Math.random() * 2500;
      simulatedIntervalRef.current = setTimeout(runStep, nextDelay);
    };

    // Start first step
    runStep();
  };

  const stopSimulation = () => {
    if (simulatedIntervalRef.current) {
      clearTimeout(simulatedIntervalRef.current);
      simulatedIntervalRef.current = null;
    }
  };


  // --- Main Action ---

  const handleGenerateWorkflow = async () => {
    if (!recordingId && !taskDescription.trim()) {
      showStatus("Please enter a task description", "error");
      return;
    }

    try {
      setIsGenerating(true);
      setCurrentStage('analyzing');
      setStageStatuses({ analyzing: { status: 'active' } });
      setGenerationLogs([]); // Clear logs
      setGenerationError(null);
      setWorkflowResult(null);

      // Initial Logs
      addLog('info', 'Initializing workflow generation engine...');
      if (recordingId) addLog('info', `Loaded recording: ${recordingName}`);
      addLog('analyzing', 'Starting deep analysis...');

      // Start Simulation for first stage
      startSimulation('analyzing');

      // Use streaming API
      const result = await api.generateWorkflowStream(
        {
          userId: userId,
          taskDescription: taskDescription || `Auto-generated workflow from recording: ${recordingName}`,
          recordingId: recordingId,
          userQuery: userQuery || null,
          enableDialogue: true,
          enableSemanticValidation: true
        },
        (event) => {
          // Status Map
          const statusToStageId = {
            'pending': 'analyzing',
            'analyzing': 'analyzing',
            'understanding': 'understanding',
            'generating': 'generating',
            'validating': 'validating',
            'completed': 'complete',
            'failed': 'failed'
          };

          if (event.status) {
            const mappedStageId = statusToStageId[event.status] || 'generating';

            // Stage Transition Logic
            if (mappedStageId !== currentStage && mappedStageId !== 'failed') {
              // Stop prev simulation and start new one
              stopSimulation();
              startSimulation(mappedStageId);

              setCurrentStage(mappedStageId);

              // Mark prev stage complete
              updateStage(currentStage, 'completed');
            }

            if (event.status === 'failed') {
              stopSimulation();
              setGenerationError(event.message || 'Generation failed');
              updateStage(currentStage, 'failed');
              addLog('error', `Generation Failed: ${event.message}`);
            } else {
              // Update active status
              updateStage(mappedStageId, 'active');

              // Backend Message Logging
              const msg = event.details || event.message;
              if (msg) {
                // Avoid duplicates if simulation happens to say same thing (rare)
                addLog('info', msg);
              }

              // Success Case
              if (event.status === 'completed') {
                stopSimulation();
                updateStage('complete', 'completed');
                addLog('success', 'Workflow generated successfully!');
              }
            }
          }
        }
      );

      // Final Success Handling (Fallbacks)
      stopSimulation();
      setCurrentStage('complete');
      updateStage('complete', 'completed');

      // Ensure we have a success log if not added yet
      addLog('success', 'Workflow generation finalized.');

      setWorkflowResult(result);
      showStatus("Workflow generated successfully!", "success");

      // Navigate
      setTimeout(() => {
        if (result && result.workflow_id) {
          onNavigate('workflow-detail', {
            workflowId: result.workflow_id,
            sessionId: result.session_id
          });
        } else {
          console.error("No workflow result returned", result);
          showStatus("Error: No workflow ID returned", "error");
        }
      }, 500);

    } catch (error) {
      console.error("Generate Workflow error:", error);
      stopSimulation();
      setCurrentStage('failed');
      setGenerationError(error.message);
      updateStage(currentStage, 'failed');
      addLog('error', error.message);
      showStatus(`Failed to generate Workflow: ${error.message}`, "error");
    }
  };

  const handleCancelGeneration = () => {
    stopSimulation();
    setIsGenerating(false);
    setCurrentStage('analyzing');
    setStageStatuses({});
    setGenerationLogs([]);
    setGenerationError(null);
    showStatus("Generation cancelled", "info");
  };

  // --- Render ---

  if (isGenerating) {
    return (
      <div className="page generation-page">
        <WorkflowGenerationProgress
          stageStatuses={stageStatuses}
          currentStage={currentStage}
          logs={generationLogs}
          onCancel={currentStage !== 'complete' && currentStage !== 'failed' ? handleCancelGeneration : null}
        />
      </div>
    );
  }

  return (
    <div className="page generation-page">
      <div className="page-header">
        <button className="back-button" onClick={() => onNavigate("main")}>
          <Icon icon="arrowLeft" />
        </button>
        <div className="page-title"><Icon icon="cpu" size={28} /> Generate Workflow</div>
      </div>

      <div className="generation-content">
        <div className="generation-step">
          <div className="step-header">
            <div className="step-number">1</div>
            <h3>Describe Your Task</h3>
          </div>

          <div className="step-content">
            <div className="input-group">
              <label>What would you like the workflow to do?</label>
              <textarea
                value={taskDescription}
                onChange={(e) => setTaskDescription(e.target.value)}
                placeholder="Example: Search Google for 'coffee', then extract the titles and links of the top 10 search results"
                rows={6}
              />
            </div>

            <button
              className="btn btn-primary"
              onClick={handleGenerateWorkflow}
              disabled={!taskDescription.trim()}
            >
              <Icon icon="zap" size={16} />
              <span>Generate Workflow</span>
            </button>

            <p className="step-description">
              The AI will analyze your task description and generate an executable Workflow.
              This typically takes 30-60 seconds.
            </p>
          </div>
        </div>

        <div className="generation-tips">
          <h4><Icon icon="info" size={16} /> Tips for better results</h4>
          <ul>
            <li>Be specific about what data you want to extract</li>
            <li>Mention the website or URL you want to work with</li>
            <li>Describe the steps in order if there are multiple</li>
            <li>You can modify the generated Workflow through dialogue later</li>
          </ul>
        </div>
      </div>

      <div className="footer">
        <p>Ami v1.0.0</p>
      </div>
    </div>
  );
}

export default GenerationPage;
