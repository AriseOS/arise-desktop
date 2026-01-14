import React, { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
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
function GenerationPage({ session, onNavigate, showStatus, params = {}, version }) {
  const { t } = useTranslation();
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

  // Ref to track current stage for callback (avoids closure stale value issue)
  const currentStageRef = useRef(currentStage);
  currentStageRef.current = currentStage;

  // Ref to prevent double invocation (React Strict Mode calls effects twice)
  const generationStartedRef = useRef(false);

  // Auto-start generation if we have a recordingId
  React.useEffect(() => {
    if (recordingId && !generationStartedRef.current) {
      generationStartedRef.current = true;
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

  // Ref to track detailed simulation state
  const simulationStateRef = useRef({
    stage: 'analyzing',
    stepIndex: 0,
    active: false
  });

  const microSteps = {
    analyzing: [
      "Connecting to neural synthesis engine...",
      "Allocating context window for task analysis...",
      "Parsing natural language intent to extracting semantic markers...",
      "Identifying key operational parameters from input...",
      "Accessing global knowledge graph for context relevance...",
      "Analyzing DOM structure patterns for target validation...",
      "Cross-referencing intent with available tool definitions...",
      "Detecting ambiguous instructions and resolving scope...",
      "Evaluating potential execution paths for efficiency...",
      "Calibrating selector reliability indices...",
      "Loading historical interaction models for optimization...",
      "Synthesizing initial execution strategy...",
      "Verifying structural integrity of the request...",
      "Mapping dependency graph for operation sequences...",
      "Analyzing potential permission boundaries...",
      "Calculating computational interactions complexity...",
      "Optimizing token usage for downstream generation...",
      "Finalizing intent extraction layer...",
      "Preparing context handshake for generation phase..."
    ],
    understanding: [
      "Initiating deep semantic understanding protocol...",
      "Decomposing complex instructions into atomic units...",
      "Mapping user intent to concrete browser actions...",
      "Validating action feasibility against current DOM state...",
      "Constructing logical flow dependency matrix...",
      "Identifying potential dynamic content loading states...",
      "Analyzing pagination and infinite scroll patterns...",
      "Detecting data extraction fields and attribute types...",
      "Resolving conditional logic branches from description...",
      "Understanding error handling requirements...",
      "Mapping form input fields to data sources...",
      "Identifying navigation breakpoints and triggers...",
      "Correlating visual elements with semantic purpose...",
      "Building internal representation of user goal...",
      "Verifying instruction completeness against heuristics...",
      "Transitioning conceptual model to executable logic..."
    ],
    generating: [
      "Bootstrapping workflow architecture...",
      "Compiling abstract syntax tree for workflow engine...",
      "Generating robust CSS selectors for target elements...",
      "Implementing loop structures for list processing...",
      "Injecting wait conditions for dynamic stability...",
      "Configuring exception handling wrappers...",
      "Optimizing navigation sequence for minimal latency...",
      "Linking data flow between extraction steps...",
      "Adding auto-recovery hooks for network jitters...",
      "Implementing scroll monitoring logic...",
      "Generating JavaScript bridging code for complex interactions...",
      "Configuring viewport emulation parameters...",
      "Setting up data structure definitions for output...",
      "Validating step connectivity and data typing...",
      "Refining control flow for conditional operations...",
      "Finalizing node configuration for execution engine..."
    ],
    validating: [
      "Initializing virtual sandbox for logic verification...",
      "Running static analysis on generated control flow...",
      "Simulating execution path against shadow DOM...",
      "Checking for cyclic dependencies in graph...",
      "Validating selector specificity and robustness...",
      "Verifying data transformation pipeline integrity...",
      "Testing error propagation simulation...",
      "Checking resource consumption estimates...",
      "Ensuring compliance with security sandboxing...",
      "Final structural validation of workflow schema...",
      "Packing executable binary representation...",
      "Signing workflow integrity checksum...",
      "Finalizing output serialization...",
      "Ready for deployment."
    ]
  };

  // Helper to run a fast-forward sequence for a specific stage
  const fastForwardStage = async (stage) => {
    return new Promise((resolve) => {
      const steps = microSteps[stage] || [];
      const currentIdx = simulationStateRef.current.stage === stage
        ? simulationStateRef.current.stepIndex
        : 0;

      if (currentIdx >= steps.length) {
        resolve();
        return;
      }

      let i = currentIdx;

      const next = () => {
        if (i >= steps.length) {
          resolve();
          return;
        }

        // Fast log addition
        addLog(Math.random() > 0.5 ? 'thinking' : 'analyzing', steps[i]);
        i++;

        // Very fast timeout for "Matrix" effect
        setTimeout(next, 50);
      };

      next();
    });
  };

  // Helper to "finish up" everything from current state to the end
  const runFastForwardCompletion = async () => {
    // 1. Finish current stage
    const currentStage = simulationStateRef.current.stage;
    await fastForwardStage(currentStage);
    updateStage(currentStage, 'completed');

    // 2. Run any remaining stages
    const stages = ['analyzing', 'understanding', 'generating', 'validating'];
    const startIdx = stages.indexOf(currentStage) + 1;

    for (let i = startIdx; i < stages.length; i++) {
      const stage = stages[i];
      setCurrentStage(stage);
      updateStage(stage, 'active');

      // Flash through this stage
      await fastForwardStage(stage);

      updateStage(stage, 'completed');
    }
  };


  const startSimulation = (stage) => {
    // Stop any existing normal simulation
    if (simulatedIntervalRef.current) clearInterval(simulatedIntervalRef.current);

    // Reset index if entering new stage
    if (simulationStateRef.current.stage !== stage) {
      simulationStateRef.current = {
        stage: stage,
        stepIndex: 0,
        active: true
      };
    } else {
      simulationStateRef.current.active = true;
    }

    const steps = microSteps[stage] || [];

    const runStep = () => {
      // If we're done with this stage's messages, just sit there and wait for backend
      // or loop the last message 'waiting...'
      if (simulationStateRef.current.stepIndex >= steps.length) {
        if (simulatedIntervalRef.current) clearInterval(simulatedIntervalRef.current);
        return;
      }

      // Add log
      const msg = steps[simulationStateRef.current.stepIndex];
      const type = Math.random() > 0.5 ? 'thinking' : 'analyzing';
      addLog(type, msg);

      simulationStateRef.current.stepIndex++;

      // Schedule next - SLOWER now (3s - 6s) to fill time
      const nextDelay = 3000 + Math.random() * 3000;
      simulatedIntervalRef.current = setTimeout(runStep, nextDelay);
    };

    // Kick off
    runStep();
  };

  const stopSimulation = () => {
    if (simulatedIntervalRef.current) {
      clearTimeout(simulatedIntervalRef.current);
      simulatedIntervalRef.current = null;
    }
    simulationStateRef.current.active = false;
  };


  // --- Main Action ---

  const handleGenerateWorkflow = async () => {
    if (!recordingId && !taskDescription.trim()) {
      showStatus(t('generation.hints.enterDescription'), "error");
      return;
    }

    // Local flag to prevent race conditions/double completion
    let isGenerationComplete = false;

    try {
      setIsGenerating(true);
      setCurrentStage('analyzing');
      setStageStatuses({ analyzing: { status: 'active' } });
      setGenerationLogs([]); // Clear logs
      setGenerationError(null);
      setWorkflowResult(null);

      // Reset Ref
      simulationStateRef.current = { stage: 'analyzing', stepIndex: 0, active: true };

      // Initial Logs
      addLog('info', t('generation.hints.initEngine'));
      if (recordingId) addLog('info', t('generation.hints.loadedRecording', { name: recordingName }));
      addLog('analyzing', t('generation.hints.startAnalysis'));

      // Start Simulation for first stage
      startSimulation('analyzing');

      // Use streaming API
      // We will interact with result via "complete" event or final return
      const result = await api.generateWorkflowStream(
        {
          userId: userId,
          taskDescription: taskDescription || `Auto-generated workflow from recording: ${recordingName}`,
          recordingId: recordingId,
          userQuery: userQuery || null,
          enableDialogue: true,
          enableSemanticValidation: true
        },
        async (event) => {
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

            // If completely failed, stop everything
            if (event.status === 'failed') {
              stopSimulation();
              setGenerationError(event.message || t('generation.stages.failed'));
              updateStage(simulationStateRef.current.stage, 'failed');
              addLog('error', `${t('generation.stages.failed')}: ${event.message}`);
              return;
            }

            // Backend says it's done -> Trigger Fast Forward Completion
            if (event.status === 'completed') {
              if (isGenerationComplete) return;
              isGenerationComplete = true;

              // Stop the "slow" simulation
              stopSimulation();

              // Run the matrix effect
              await runFastForwardCompletion();

              addLog('success', t('generation.hints.genSuccess'));
              return;
            }

            // Normal stage transition (Backend moved faster than simulation)
            // e.g. we were 'analyzing' but backend says 'generating'
            // We should fast-forward the current stage, then start the new one.
            if (mappedStageId !== simulationStateRef.current.stage && mappedStageId !== 'complete') {
              stopSimulation();

              // Fast forward the PREVIOUS stage to completion visual
              await fastForwardStage(simulationStateRef.current.stage);
              updateStage(simulationStateRef.current.stage, 'completed');

              // Start the NEW stage
              setCurrentStage(mappedStageId);
              updateStage(mappedStageId, 'active');
              startSimulation(mappedStageId);
            }

            // Backend Message Logging (Real info from backend)
            const msg = event.details || event.message;
            if (msg && !msg.includes('progress')) {
              addLog('info', `[Backend] ${msg}`);
            }
          }
        }
      );

      // --- FINISHED ---

      // Just in case stream didn't trigger 'completed' event logic above
      stopSimulation();

      // Ensure we are visually at the end
      if (!isGenerationComplete) {
        isGenerationComplete = true;
        await runFastForwardCompletion();
      }

      updateStage('complete', 'completed');
      addLog('success', t('generation.hints.genFinalized'));

      setWorkflowResult(result);
      showStatus(t('generation.hints.genSuccess'), "success");

      // Navigate
      setTimeout(() => {
        if (result && result.workflow_id) {
          onNavigate('workflow-detail', {
            workflowId: result.workflow_id,
            sessionId: result.session_id
          });
        } else {
          console.error("No workflow result returned", result);
          showStatus(t('generation.hints.genFailed', { error: 'No workflow ID returned' }), "error");
        }
      }, 1000); // Give a moment to see the 'Ready' state

    } catch (error) {
      console.error("Generate Workflow error:", error);
      stopSimulation();
      setCurrentStage('failed');
      setGenerationError(error.message);
      updateStage(currentStage, 'failed');
      addLog('error', error.message);
      showStatus(t('generation.hints.genFailed', { error: error.message }), "error");
    }
  };

  const handleCancelGeneration = () => {
    stopSimulation();
    setIsGenerating(false);
    setCurrentStage('analyzing');
    setStageStatuses({});
    setGenerationLogs([]);
    setGenerationError(null);
    showStatus(t('generation.hints.cancelled'), "info");
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
        <div className="page-title"><Icon icon="cpu" size={28} /> {t('generation.title')}</div>
      </div>

      <div className="generation-content">
        <div className="generation-step">
          <div className="step-header">
            <div className="step-number">1</div>
            <h3>{t('generation.describeTask')}</h3>
          </div>

          <div className="step-content">
            <div className="input-group">
              <label>{t('generation.whatToDo')}</label>
              <textarea
                value={taskDescription}
                onChange={(e) => setTaskDescription(e.target.value)}
                placeholder={t('generation.placeholder')}
                rows={6}
              />
            </div>

            <button
              className="btn btn-primary"
              onClick={handleGenerateWorkflow}
              disabled={!taskDescription.trim()}
            >
              <Icon icon="zap" size={16} />
              <span>{t('generation.generateBtn')}</span>
            </button>

            <p className="step-description">
              {t('generation.stepDescription')}
            </p>
          </div>
        </div>

        <div className="generation-tips">
          <h4><Icon icon="info" size={16} /> {t('generation.tips.title')}</h4>
          <ul>
            <li>{t('generation.tips.tip1')}</li>
            <li>{t('generation.tips.tip2')}</li>
            <li>{t('generation.tips.tip3')}</li>
            <li>{t('generation.tips.tip4')}</li>
          </ul>
        </div>
      </div>

      <div className="footer">
        <p>Ami v{version || '1.0.0'} • {session?.username && `Logged in as ${session.username}`}</p>
      </div>
    </div>
  );
}

export default GenerationPage;
