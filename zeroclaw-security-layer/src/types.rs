/// Unified SecurityPlugin protocol — Rust edition.
///
/// Field semantics and naming are identical to the TypeScript
/// (openclaw-security-layer) and Python (nanobot-security-layer)
/// versions for cross-runtime consistency.
use std::collections::HashMap;

use async_trait::async_trait;
use serde::{Deserialize, Serialize};

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

#[derive(Debug, Clone)]
pub struct ExecutionContext {
    pub tool_name: String,
    pub params: serde_json::Value,
    pub session_id: Option<String>,
    pub run_id: Option<String>,
    pub tool_call_id: Option<String>,
    pub timestamp: f64,
    pub metadata: HashMap<String, serde_json::Value>,
}

#[derive(Debug, Clone)]
pub struct BeforeResult {
    pub action: BeforeAction,
    pub reason: Option<String>,
    pub message: Option<String>,
    pub modified_params: Option<serde_json::Value>,
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

#[derive(Debug, Clone)]
pub struct ExecutionResult {
    pub success: bool,
    pub output: String,
    pub error: Option<String>,
    pub duration_ms: Option<f64>,
}

#[derive(Debug, Clone)]
pub struct AfterResult {
    pub action: AfterAction,
    pub reason: Option<String>,
    pub message: Option<String>,
    pub modified_result: Option<String>,
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

#[async_trait]
pub trait SecurityPlugin: Send + Sync {
    fn id(&self) -> &str;
    fn priority(&self) -> i32;

    async fn initialize(&mut self, config: serde_json::Value) -> Result<(), Box<dyn std::error::Error>>;
    async fn destroy(&mut self) -> Result<(), Box<dyn std::error::Error>>;

    async fn before_execute(&self, ctx: &ExecutionContext) -> BeforeResult;
    async fn after_execute(&self, ctx: &ExecutionContext, result: &ExecutionResult) -> AfterResult;
}

#[derive(Debug, Clone, Deserialize)]
pub struct PluginEntry {
    pub id: String,
    #[serde(default = "default_true")]
    pub enabled: bool,
    #[serde(default = "default_priority")]
    pub priority: i32,
    #[serde(default)]
    pub config: serde_json::Value,
}

#[derive(Debug, Clone, Deserialize)]
pub struct SecurityConfig {
    pub plugins: Vec<PluginEntry>,
}

fn default_true() -> bool {
    true
}

fn default_priority() -> i32 {
    100
}
