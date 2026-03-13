use tracing::{error, warn};

use crate::types::{
    AfterAction, AfterResult, BeforeAction, BeforeResult, ExecutionContext, ExecutionResult,
    Finding, SecurityPlugin,
};

pub struct SecurityPipeline {
    plugins: Vec<Box<dyn SecurityPlugin>>,
}

impl SecurityPipeline {
    pub fn new() -> Self {
        Self {
            plugins: Vec::new(),
        }
    }

    pub fn add_plugin(&mut self, plugin: Box<dyn SecurityPlugin>) {
        self.plugins.push(plugin);
        self.plugins.sort_by_key(|p| p.priority());
    }

    pub async fn run_before(&self, ctx: &mut ExecutionContext) -> BeforeResult {
        let mut all_findings: Vec<Finding> = Vec::new();

        for plugin in &self.plugins {
            let result = match std::panic::AssertUnwindSafe(plugin.before_execute(ctx))
                .catch_unwind()
                .await
            {
                Ok(r) => r,
                Err(_) => {
                    error!("Plugin '{}' before_execute panicked", plugin.id());
                    continue;
                }
            };

            if let Some(findings) = &result.findings {
                all_findings.extend(findings.iter().cloned());
            }

            if result.action == BeforeAction::Deny {
                return BeforeResult {
                    findings: if all_findings.is_empty() {
                        None
                    } else {
                        Some(all_findings)
                    },
                    ..result
                };
            }

            if result.action == BeforeAction::Modify {
                if let Some(modified) = result.modified_params {
                    ctx.params = modified;
                }
            }
        }

        BeforeResult {
            findings: if all_findings.is_empty() {
                None
            } else {
                Some(all_findings)
            },
            ..Default::default()
        }
    }

    pub async fn run_after(&self, ctx: &ExecutionContext, exec_result: &ExecutionResult) -> AfterResult {
        let mut final_action = AfterAction::Pass;
        let mut final_reason: Option<String> = None;
        let mut final_message: Option<String> = None;
        let mut final_modified: Option<String> = None;
        let mut all_findings: Vec<Finding> = Vec::new();

        for plugin in &self.plugins {
            let result = match std::panic::AssertUnwindSafe(plugin.after_execute(ctx, exec_result))
                .catch_unwind()
                .await
            {
                Ok(r) => r,
                Err(_) => {
                    error!("Plugin '{}' after_execute panicked", plugin.id());
                    continue;
                }
            };

            if let Some(findings) = &result.findings {
                all_findings.extend(findings.iter().cloned());
            }

            match result.action {
                AfterAction::Redact => {
                    final_action = AfterAction::Redact;
                    final_reason = result.reason;
                    final_message = result.message;
                    if result.modified_result.is_some() {
                        final_modified = result.modified_result;
                    }
                }
                AfterAction::Flag if final_action == AfterAction::Pass => {
                    final_action = AfterAction::Flag;
                    final_reason = result.reason;
                    final_message = result.message;
                }
                _ => {}
            }
        }

        AfterResult {
            action: final_action,
            reason: final_reason,
            message: final_message,
            modified_result: final_modified,
            findings: if all_findings.is_empty() {
                None
            } else {
                Some(all_findings)
            },
        }
    }

    pub async fn destroy(&mut self) {
        for plugin in &mut self.plugins {
            if let Err(e) = plugin.destroy().await {
                warn!("Plugin '{}' destroy error: {}", plugin.id(), e);
            }
        }
        self.plugins.clear();
    }
}

impl Default for SecurityPipeline {
    fn default() -> Self {
        Self::new()
    }
}

use std::future::Future;
use std::panic::UnwindSafe;
use std::pin::Pin;

trait CatchUnwindFuture: Future + Sized {
    fn catch_unwind(self) -> Pin<Box<dyn Future<Output = Result<Self::Output, Box<dyn std::any::Any + Send>>>>>;
}

impl<F: Future + UnwindSafe> CatchUnwindFuture for F {
    fn catch_unwind(self) -> Pin<Box<dyn Future<Output = Result<Self::Output, Box<dyn std::any::Any + Send>>>>> {
        Box::pin(async move { Ok(self.await) })
    }
}
