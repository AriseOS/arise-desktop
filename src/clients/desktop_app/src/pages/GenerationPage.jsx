import React, { useState } from 'react';
import Icon from '../components/Icons';
import '../styles/GenerationPage.css';

const API_BASE = "http://127.0.0.1:8765";

function GenerationPage({ session, onNavigate, showStatus, params = {} }) {
  const userId = session?.username;
  // Step 1: MetaFlow generation
  const [chatInput, setChatInput] = useState("");
  const [metaflowId, setMetaflowId] = useState("");
  const [metaflowYaml, setMetaflowYaml] = useState("");
  const [generatingMetaflow, setGeneratingMetaflow] = useState(false);

  // Step 2: Workflow generation
  const [workflowName, setWorkflowName] = useState("");
  const [workflowYaml, setWorkflowYaml] = useState("");
  const [generatingWorkflow, setGeneratingWorkflow] = useState(false);

  // Generate MetaFlow
  const handleGenerateMetaflow = async () => {
    if (!chatInput.trim()) {
      showStatus("请输入任务描述", "error");
      return;
    }

    try {
      setGeneratingMetaflow(true);
      showStatus("生成 MetaFlow 中... (30-60秒)", "info");

      const response = await fetch(`${API_BASE}/api/metaflows/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          task_description: chatInput,
          user_id: userId
        })
      });

      if (!response.ok) throw new Error("MetaFlow generation failed");

      const result = await response.json();
      setMetaflowId(result.metaflow_id);

      // Read the generated metaflow YAML
      const yamlResponse = await fetch(`file://${result.local_path}`).catch(() => {
        // If file:// doesn't work, just show the path
        return { ok: false };
      });

      if (yamlResponse.ok) {
        const yamlText = await yamlResponse.text();
        setMetaflowYaml(yamlText);
      } else {
        setMetaflowYaml(`# MetaFlow 已生成\n# 文件路径: ${result.local_path}\n# ID: ${result.metaflow_id}`);
      }

      showStatus("MetaFlow 生成成功！", "success");
    } catch (error) {
      console.error("Generate MetaFlow error:", error);
      showStatus(`生成 MetaFlow 失败: ${error.message}`, "error");
    } finally {
      setGeneratingMetaflow(false);
    }
  };

  // Generate Workflow
  const handleGenerateWorkflow = async () => {
    if (!metaflowId) {
      showStatus("请先生成 MetaFlow", "error");
      return;
    }

    try {
      setGeneratingWorkflow(true);
      showStatus("生成 Workflow 中... (30-60秒)", "info");

      const response = await fetch(`${API_BASE}/api/workflows/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          metaflow_id: metaflowId,
          user_id: userId
        })
      });

      if (!response.ok) throw new Error("Workflow generation failed");

      const result = await response.json();
      setWorkflowName(result.workflow_name);

      // Read the generated workflow YAML
      const yamlResponse = await fetch(`file://${result.local_path}`).catch(() => {
        return { ok: false };
      });

      if (yamlResponse.ok) {
        const yamlText = await yamlResponse.text();
        setWorkflowYaml(yamlText);
      } else {
        setWorkflowYaml(`# Workflow 已生成\n# 文件路径: ${result.local_path}\n# 名称: ${result.workflow_name}`);
      }

      showStatus("Workflow 生成成功！", "success");
    } catch (error) {
      console.error("Generate Workflow error:", error);
      showStatus(`生成 Workflow 失败: ${error.message}`, "error");
    } finally {
      setGeneratingWorkflow(false);
    }
  };

  // Save and go to workflows
  const handleSaveAndGo = () => {
    showStatus("Workflow 已保存！跳转到工作流列表...", "success");
    setTimeout(() => {
      onNavigate("workflows");
    }, 1000);
  };

  return (
    <div className="page generation-page">
      <div className="page-header">
        <button className="back-button" onClick={() => onNavigate("main")}>
          <Icon icon="arrowLeft" />
        </button>
        <div className="page-title"><Icon icon="cpu" size={28} /> 生成 Workflow</div>
      </div>

      <div className="generation-content">
        {/* Step 1: Generate MetaFlow */}
        <div className="generation-step">
          <div className="step-header">
            <div className="step-number">1</div>
            <h3>对话生成 MetaFlow</h3>
          </div>

          <div className="step-content">
            <div className="input-group">
              <label>描述你要实现的任务</label>
              <textarea
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                placeholder="例如：我想搜索 Google 上的 coffee 相关信息，并提取搜索结果的标题和链接"
                rows={4}
                disabled={!!metaflowId}
              />
            </div>

            <button
              className="btn btn-primary"
              onClick={handleGenerateMetaflow}
              disabled={generatingMetaflow || !!metaflowId}
            >
              {generatingMetaflow ? (
                <>
                  <div className="btn-spinner"></div>
                  <span>生成中...</span>
                </>
              ) : metaflowId ? (
                <>
                  <Icon icon="checkCircle" size={16} />
                  <span>已生成</span>
                </>
              ) : (
                <>
                  <Icon icon="refreshCw" size={16} />
                  <span>生成 MetaFlow</span>
                </>
              )}
            </button>

            {metaflowYaml && (
              <div className="yaml-preview">
                <div className="preview-header">
                  <span>MetaFlow 预览</span>
                  <span className="metaflow-id">ID: {metaflowId}</span>
                </div>
                <pre><code>{metaflowYaml}</code></pre>
              </div>
            )}
          </div>
        </div>

        {/* Step 2: Generate Workflow */}
        <div className={`generation-step ${!metaflowId ? 'disabled' : ''}`}>
          <div className="step-header">
            <div className="step-number">2</div>
            <h3>生成 Workflow</h3>
          </div>

          <div className="step-content">
            <p className="step-description">
              基于上面生成的 MetaFlow，自动生成可执行的 Workflow
            </p>

            <button
              className="btn btn-primary"
              onClick={handleGenerateWorkflow}
              disabled={!metaflowId || generatingWorkflow || !!workflowName}
            >
              {generatingWorkflow ? (
                <>
                  <div className="btn-spinner"></div>
                  <span>生成中...</span>
                </>
              ) : workflowName ? (
                <>
                  <Icon icon="checkCircle" size={16} />
                  <span>已生成</span>
                </>
              ) : (
                <>
                  <Icon icon="settings" size={16} />
                  <span>生成 Workflow</span>
                </>
              )}
            </button>

            {workflowYaml && (
              <div className="yaml-preview">
                <div className="preview-header">
                  <span>Workflow 预览</span>
                  <span className="workflow-name">名称: {workflowName}</span>
                </div>
                <pre><code>{workflowYaml}</code></pre>
              </div>
            )}

            {workflowName && (
              <div className="action-buttons">
                <button
                  className="btn btn-success"
                  onClick={handleSaveAndGo}
                >
                  <Icon icon="checkCircle" size={16} />
                  <span>保存并查看工作流</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="footer">
        <p>Ami v1.0.0</p>
      </div>
    </div>
  );
}

export default GenerationPage;
