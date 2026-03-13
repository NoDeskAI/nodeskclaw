use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum BeforeAction {
    Allow,
    Deny,
    Modify,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum AfterAction {
    Pass,
    Redact,
    Flag,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Severity {
    Critical,
    High,
    Medium,
    Low,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Finding {
    pub plugin_id: String,
    pub category: String,
    pub severity: Severity,
    pub message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub detail: Option<HashMap<String, serde_json::Value>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BeforeResult {
    pub action: BeforeAction,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub modified_params: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub findings: Option<Vec<Finding>>,
}

impl Default for BeforeResult {
    fn default() -> Self {
        Self {
            action: BeforeAction::Allow,
            reason: None,
            message: None,
            modified_params: None,
            findings: None,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AfterResult {
    pub action: AfterAction,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub modified_result: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub findings: Option<Vec<Finding>>,
}

impl Default for AfterResult {
    fn default() -> Self {
        Self {
            action: AfterAction::Pass,
            reason: None,
            message: None,
            modified_result: None,
            findings: None,
        }
    }
}

#[derive(Debug, Serialize)]
pub struct WsRequest {
    #[serde(rename = "type")]
    pub msg_type: String,
    pub id: String,
    pub ctx: WsContext,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub exec_result: Option<WsExecResult>,
}

#[derive(Debug, Serialize)]
pub struct WsContext {
    pub tool_name: String,
    pub params: serde_json::Value,
    pub agent_instance_id: String,
    pub workspace_id: String,
    pub timestamp: f64,
}

#[derive(Debug, Serialize)]
pub struct WsExecResult {
    pub result: Option<String>,
    pub error: Option<String>,
    pub duration_ms: Option<f64>,
}

#[derive(Debug, Deserialize)]
pub struct WsResponse {
    #[serde(rename = "type")]
    pub msg_type: String,
    pub id: String,
    #[serde(default)]
    pub result: Option<serde_json::Value>,
}
