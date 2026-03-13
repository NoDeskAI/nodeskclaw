use std::sync::Arc;
use std::time::Instant;

use async_trait::async_trait;
use serde_json::Value;

use crate::types::{AfterAction, BeforeAction};
use crate::ws_client::SecurityWsClient;

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

pub struct SecuredTool<T: Tool> {
    inner: T,
    client: Arc<SecurityWsClient>,
}

impl<T: Tool> SecuredTool<T> {
    pub fn new(inner: T, client: Arc<SecurityWsClient>) -> Self {
        Self { inner, client }
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
        let before = self.client.evaluate_before(self.inner.name(), &args).await;

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
            before.modified_params.unwrap_or(args.clone())
        } else {
            args.clone()
        };

        let start = Instant::now();
        let tool_result = self.inner.execute(execute_args).await;
        let duration_ms = start.elapsed().as_secs_f64() * 1000.0;

        let after = self
            .client
            .evaluate_after(
                self.inner.name(),
                &args,
                &tool_result.output,
                tool_result.error.as_deref(),
                Some(duration_ms),
            )
            .await;

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
