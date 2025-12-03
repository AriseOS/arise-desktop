import React, { useState, useEffect } from 'react';
import Icon from '../components/Icons';
import '../styles/ConversationalGenerationPage.css';

const API_BASE = "http://127.0.0.1:8765";

function ConversationalGenerationPage({ session, onNavigate, showStatus }) {
  const userId = session?.username;
  const [taskDescription, setTaskDescription] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [showRecordingsSidebar, setShowRecordingsSidebar] = useState(true);
  const [recordings, setRecordings] = useState([]);
  const [recordingsSearch, setRecordingsSearch] = useState('');
  const [referencedRecording, setReferencedRecording] = useState(null);

  // Load recordings for sidebar
  useEffect(() => {
    fetchRecordings();
  }, []);

  const fetchRecordings = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/recordings`);

      if (response.ok) {
        const data = await response.json();
        setRecordings(data.recordings || []);
      }
    } catch (error) {
      console.error('Error fetching recordings:', error);
    }
  };

  const handleGenerateWorkflow = async () => {
    const description = taskDescription.trim();
    if (!description) {
      showStatus('Please describe the task you want to automate', 'error');
      return;
    }

    setIsGenerating(true);

    try {
      let response;
      let apiEndpoint;
      let requestBody;

      // Choose API endpoint based on whether a recording is referenced
      if (referencedRecording?.session_id) {
        // Generate MetaFlow from recording
        apiEndpoint = `${API_BASE}/api/metaflows/from-recording`;
        requestBody = {
          session_id: referencedRecording.session_id,
          task_description: description,
          user_id: userId
        };
        showStatus('Generating MetaFlow from recording...', 'info');
      } else {
        // Generate MetaFlow from text description
        apiEndpoint = `${API_BASE}/api/metaflows/generate`;
        requestBody = {
          task_description: description,
          user_id: userId
        };
        showStatus('Generating MetaFlow from your description...', 'info');
      }

      response = await fetch(apiEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody)
      });

      if (!response.ok) {
        throw new Error(`MetaFlow generation failed: ${response.status}`);
      }

      const data = await response.json();

      showStatus('MetaFlow generated! Please review.', 'success');

      // Navigate to MetaFlow preview page
      setTimeout(() => {
        onNavigate('metaflow-preview', {
          metaflowId: data.metaflow_id,
          metaflowYaml: data.metaflow_yaml
        });
      }, 500);
    } catch (error) {
      console.error('Error generating MetaFlow:', error);
      showStatus(`Failed to generate MetaFlow: ${error.message}`, 'error');
    } finally {
      setIsGenerating(false);
    }
  };

  const handleReferenceRecording = (recording) => {
    setReferencedRecording(recording);
    setShowRecordingsSidebar(false);
    showStatus(`Referenced recording: ${recording.name || recording.session_id}`, 'info');
  };

  const handleClearReference = () => {
    setReferencedRecording(null);
    showStatus('Reference cleared', 'info');
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && e.ctrlKey) {
      handleGenerateWorkflow();
    }
  };

  const filteredRecordings = recordings.filter(recording => {
    if (!recordingsSearch.trim()) return true;

    const query = recordingsSearch.toLowerCase();
    const nameMatch = recording.name?.toLowerCase().includes(query);
    const urlMatch = recording.url?.toLowerCase().includes(query);
    const sessionMatch = recording.session_id?.toLowerCase().includes(query);

    return nameMatch || urlMatch || sessionMatch;
  });

  return (
    <div className="conversational-generation-page">
      {/* Header */}
      <div className="page-header">
        <button className="back-button" onClick={() => onNavigate('main')}>
          <Icon icon="arrowLeft" />
        </button>
        <h1 className="page-title"><Icon icon="messageSquare" size={28} /> AI Workflow Generation</h1>
        <div className="header-spacer"></div>
        <button
          className="toggle-sidebar-btn"
          onClick={() => setShowRecordingsSidebar(!showRecordingsSidebar)}
          title={showRecordingsSidebar ? 'Hide recordings' : 'Show recordings'}
        >
          {showRecordingsSidebar ? (
            <Icon icon="chevronRight" />
          ) : (
            <Icon icon="chevronLeft" />
          )}
        </button>
      </div>

      {/* Main Content Area */}
      <div className={`content-area ${!showRecordingsSidebar ? 'full-width' : ''}`}>
        {/* Generation Area */}
        <div className="generation-area">
          <div className="generation-container">
            {/* Welcome Section */}
            <div className="welcome-section">
              <div className="welcome-icon"><Icon icon="cpu" size={48} /></div>
              <h2>AI Workflow Generator</h2>
              <p>Describe the task you want to automate, and AI will create a workflow for you.</p>
            </div>

            {/* Referenced Recording Badge */}
            {referencedRecording && (
              <div className="referenced-recording-badge">
                <div className="badge-content">
                  <span className="badge-icon"><Icon icon="paperclip" size={16} /></span>
                  <span className="badge-text">
                    Using recording: {referencedRecording.name || referencedRecording.session_id}
                  </span>
                  <button className="badge-clear" onClick={handleClearReference}>
                    <Icon icon="x" size={14} />
                  </button>
                </div>
              </div>
            )}

            {/* Task Description Input */}
            <div className="task-input-section">
              <label htmlFor="task-description" className="input-label">
                What do you want to automate?
              </label>
              <textarea
                id="task-description"
                className="task-input"
                placeholder="Example: I want to scrape product names and prices from an e-commerce website, then save them to an Excel file."
                value={taskDescription}
                onChange={(e) => setTaskDescription(e.target.value)}
                onKeyPress={handleKeyPress}
                rows={8}
                disabled={isGenerating}
              />
              <div className="input-hint">
                <Icon icon="info" size={14} /> Be specific about: What data to extract, from which website, and how to save it.
                <br />
                <span className="keyboard-hint">Press Ctrl+Enter to generate</span>
              </div>
            </div>

            {/* Example Prompts */}
            <div className="example-prompts-section">
              <p className="examples-label"><Icon icon="info" size={14} /> Example tasks:</p>
              <div className="examples-grid">
                <button
                  className="example-card"
                  onClick={() => setTaskDescription('Download daily sales reports from the company dashboard and save them to a local folder.')}
                  disabled={isGenerating}
                >
                  <span className="example-icon"><Icon icon="barChart" size={20} /></span>
                  <span className="example-text">Download daily sales reports from dashboard</span>
                </button>
                <button
                  className="example-card"
                  onClick={() => setTaskDescription('Scrape product names, prices, and stock levels from an e-commerce website and save to Excel.')}
                  disabled={isGenerating}
                >
                  <span className="example-icon"><Icon icon="shoppingCart" size={20} /></span>
                  <span className="example-text">Scrape product info from e-commerce site</span>
                </button>
                <button
                  className="example-card"
                  onClick={() => setTaskDescription('Automatically fill out a registration form with user data from a CSV file.')}
                  disabled={isGenerating}
                >
                  <span className="example-icon"><Icon icon="fileText" size={20} /></span>
                  <span className="example-text">Auto-fill registration forms</span>
                </button>
              </div>
            </div>

            {/* Generate Button */}
            <div className="generate-button-section">
              <button
                className="btn-generate"
                onClick={handleGenerateWorkflow}
                disabled={!taskDescription.trim() || isGenerating}
              >
                {isGenerating ? (
                  <>
                    <div className="btn-spinner"></div>
                    <span>Generating...</span>
                  </>
                ) : (
                  <>
                    <Icon icon="zap" size={20} />
                    <span>Generate Workflow</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Recordings Sidebar */}
        {showRecordingsSidebar && (
          <div className="recordings-sidebar">
            <div className="sidebar-header">
              <h3><Icon icon="video" size={18} /> Reference a Recording</h3>
              <button
                className="close-sidebar-btn"
                onClick={() => setShowRecordingsSidebar(false)}
              >
                <Icon icon="x" size={18} />
              </button>
            </div>

            <div className="sidebar-description">
              <p>Select a recording to help AI understand your task better.</p>
            </div>

            <div className="sidebar-search">
              <div className="search-icon"><Icon icon="search" size={16} /></div>
              <input
                type="text"
                placeholder="Search recordings..."
                value={recordingsSearch}
                onChange={(e) => setRecordingsSearch(e.target.value)}
              />
            </div>

            <div className="recordings-list">
              {filteredRecordings.length === 0 ? (
                <div className="empty-recordings">
                  <p>{recordings.length === 0 ? 'No recordings available' : 'No matching recordings'}</p>
                </div>
              ) : (
                filteredRecordings.map((recording) => (
                  <div
                    key={recording.session_id}
                    className={`recording-item ${referencedRecording?.session_id === recording.session_id ? 'selected' : ''}`}
                  >
                    <div className="recording-item-icon"><Icon icon="video" size={16} /></div>
                    <div className="recording-item-info">
                      <div className="recording-item-name">
                        {recording.name || `Recording ${recording.session_id.substring(0, 8)}...`}
                      </div>
                      <div className="recording-item-meta">
                        {recording.action_count || 0} ops • {recording.field_count || 0} fields
                      </div>
                    </div>
                    <button
                      className="reference-btn"
                      onClick={() => handleReferenceRecording(recording)}
                      disabled={referencedRecording?.session_id === recording.session_id}
                    >
                      {referencedRecording?.session_id === recording.session_id ? '✓ Selected' : '+ Use'}
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default ConversationalGenerationPage;
