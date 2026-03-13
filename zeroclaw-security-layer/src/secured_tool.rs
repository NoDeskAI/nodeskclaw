/// `SecuredTool<T>` — a generic wrapper that interposes the security pipeline
/// around any type implementing ZeroClaw's `Tool` trait.
///
/// At build time, each tool in the registry is wrapped:
///   `SecuredTool::new(original_tool, pipeline_ref)`
///
/// When the agent loop calls `tool.execute(args)`:
///   1. Before plugins run (may block or modify args)
///   2. Inner tool executes (or is skipped on deny)
///   3. After plugins run (may flag or redact result)
///
/// This module defines the wrapper using a placeholder `Tool` trait
/// that mirrors ZeroClaw's interface. At integration time, replace
/// with `use zeroclaw::tools::traits::Tool;`.
use std::collections::HashMap;
use std::sync::Arc;
use std::time::Instant;

use async_trait::async_trait;
use serde_json::Value;
use tokio::sync::RwLock;

use crate::pipeline::SecurityPipeline;
use crate::types::{AfterAction, BeforeAction, ExecutionContext, ExecutionResult};

// ----- ZeroClaw Tool trait placeholder -----
// Replace with `use zeroclaw::tools::traits::{Tool, ToolResult};` at integration time.

#[derive(Debug, Clone)]
pub struct ToolResult {
    pub success: bool,
    pub output: String,
    pub error: Option<String>,
}

#[async_trait]
pub trait Tool: Send + Sync {
    fn name(&self) -> &str;
    fn description(&self) -> &str;
    fn parameters(&self) -> Value;
    async fn execute(&self, args: Value) -> ToolResult;
}

// ----- SecuredTool wrapper -----

pub struct SecuredTool<T: Tool> {
    inner: T,
    pipeline: Arc<RwLock<SecurityPipeline>>,
}

impl<T: Tool> SecuredTool<T> {
    pub fn new(inner: T, pipeline: Arc<RwLock<SecurityPipeline>>) -> Self {
        Self { inner, pipeline }
    }
}

#[async_trait]
impl<T: Tool + 'static> Tool for SecuredTool<T> {
    fn name(&self) -> &str {
        self.inner.name()
    }

    fn description(&self) -> &str {
        self.inner.description()
    }

    fn parameters(&self) -> Value {
        self.inner.parameters()
    }

    async fn execute(&self, args: Value) -> ToolResult {
        let pipeline = self.pipeline.read().await;

        let mut ctx = ExecutionContext {
            tool_name: self.inner.name().to_string(),
            params: args.clone(),
            session_id: None,
            run_id: None,
            tool_call_id: None,
            timestamp: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_secs_f64(),
            metadata: HashMap::new(),
        };

        let before = pipeline.run_before(&mut ctx).await;

        if before.action == BeforeAction::Deny {
            let msg = before
                .message
                .or(before.reason)
                .unwrap_or_else(|| "Blocked by security policy".into());
            return ToolResult {
                success: false,
                output: String::new(),
                error: Some(format!("{msg}\n[This tool call was blocked by security policy.]")),
            };
        }

        let execute_args = if before.action == BeforeAction::Modify {
            before.modified_params.unwrap_or(ctx.params.clone())
        } else {
            ctx.params.clone()
        };

        let start = Instant::now();
        let tool_result = self.inner.execute(execute_args).await;
        let duration_ms = start.elapsed().as_secs_f64() * 1000.0;

        let exec_result = ExecutionResult {
            success: tool_result.success,
            output: tool_result.output.clone(),
            error: tool_result.error.clone(),
            duration_ms: Some(duration_ms),
        };

        let after = pipeline.run_after(&ctx, &exec_result).await;

        let mut output = tool_result.output;
        if after.action == AfterAction::Redact {
            if let Some(modified) = after.modified_result {
                output = modified;
            }
        }
        if let Some(msg) = after.message {
            output = format!("{output}\n\n[Security note: {msg}]");
        }

        ToolResult {
            success: tool_result.success,
            output,
            error: tool_result.error,
        }
    }
}
