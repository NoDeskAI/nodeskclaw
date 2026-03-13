use async_trait::async_trait;
use regex::Regex;
use serde::Deserialize;
use tracing::warn;

use crate::types::{
    AfterResult, BeforeAction, BeforeResult, ExecutionContext, ExecutionResult, Finding,
    SecurityPlugin, Severity,
};

#[derive(Debug, Deserialize)]
struct PolicyGateConfig {
    #[serde(default = "default_mode")]
    mode: String,
    #[serde(default)]
    tools: std::collections::HashMap<String, ToolRuleConfig>,
}

#[derive(Debug, Deserialize)]
struct ToolRuleConfig {
    #[serde(default = "default_allow")]
    action: String,
    #[serde(default)]
    denied_paths: Vec<String>,
    #[serde(default)]
    denied_commands: Vec<String>,
}

fn default_mode() -> String {
    "monitor".into()
}

fn default_allow() -> String {
    "allow".into()
}

struct ToolRule {
    action: String,
    denied_paths: Vec<String>,
    denied_commands: Vec<Regex>,
}

pub struct PolicyGatePlugin {
    priority: i32,
    mode: String,
    rules: std::collections::HashMap<String, ToolRule>,
}

impl PolicyGatePlugin {
    pub fn new(priority: i32) -> Self {
        Self {
            priority,
            mode: "monitor".into(),
            rules: std::collections::HashMap::new(),
        }
    }

    fn check_params(&self, tool_name: &str, params: &serde_json::Value, rule: &ToolRule) -> Option<String> {
        if tool_name == "shell" || tool_name == "exec" {
            let cmd = params
                .get("command")
                .or_else(|| params.get("cmd"))
                .and_then(|v| v.as_str())
                .unwrap_or("");
            for pattern in &rule.denied_commands {
                if pattern.is_match(cmd) {
                    return Some(format!(
                        "Command matches denied pattern: {}",
                        pattern.as_str()
                    ));
                }
            }
        }

        if matches!(tool_name, "file_read" | "file_write" | "file_edit" | "read_file" | "write_file" | "edit_file") {
            let path = params
                .get("path")
                .or_else(|| params.get("file_path"))
                .and_then(|v| v.as_str())
                .unwrap_or("");
            for pattern in &rule.denied_paths {
                if path_matches(path, pattern) {
                    return Some(format!(
                        "Path '{}' matches denied pattern: {}",
                        path, pattern
                    ));
                }
            }
        }

        None
    }

    fn make_deny(&self, tool_name: &str, reason: String) -> BeforeResult {
        let finding = Finding {
            plugin_id: self.id().to_string(),
            category: "POLICY_VIOLATION".into(),
            severity: Severity::High,
            message: reason.clone(),
            detail: None,
        };

        if self.mode == "monitor" {
            warn!("[monitor] {} -> {}", tool_name, reason);
            return BeforeResult {
                findings: Some(vec![finding]),
                ..Default::default()
            };
        }

        BeforeResult {
            action: BeforeAction::Deny,
            reason: Some(reason.clone()),
            message: Some(format!(
                "Security policy: {}. Try a different approach.",
                reason
            )),
            findings: Some(vec![finding]),
            ..Default::default()
        }
    }
}

#[async_trait]
impl SecurityPlugin for PolicyGatePlugin {
    fn id(&self) -> &str {
        "policy-gate"
    }

    fn priority(&self) -> i32 {
        self.priority
    }

    async fn initialize(&mut self, config: serde_json::Value) -> Result<(), Box<dyn std::error::Error>> {
        let cfg: PolicyGateConfig = serde_json::from_value(config)?;
        self.mode = cfg.mode;

        for (tool_name, rule_cfg) in cfg.tools {
            let denied_commands = rule_cfg
                .denied_commands
                .iter()
                .filter_map(|p| Regex::new(p).ok())
                .collect();

            self.rules.insert(
                tool_name,
                ToolRule {
                    action: rule_cfg.action,
                    denied_paths: rule_cfg.denied_paths,
                    denied_commands,
                },
            );
        }

        Ok(())
    }

    async fn destroy(&mut self) -> Result<(), Box<dyn std::error::Error>> {
        Ok(())
    }

    async fn before_execute(&self, ctx: &ExecutionContext) -> BeforeResult {
        if self.mode == "disable" {
            return BeforeResult::default();
        }

        let Some(rule) = self.rules.get(&ctx.tool_name) else {
            return BeforeResult::default();
        };

        if rule.action == "deny" {
            return self.make_deny(
                &ctx.tool_name,
                format!("Tool '{}' is denied by policy", ctx.tool_name),
            );
        }

        if let Some(violation) = self.check_params(&ctx.tool_name, &ctx.params, rule) {
            return self.make_deny(&ctx.tool_name, violation);
        }

        BeforeResult::default()
    }

    async fn after_execute(&self, _ctx: &ExecutionContext, _result: &ExecutionResult) -> AfterResult {
        AfterResult::default()
    }
}

fn path_matches(file_path: &str, pattern: &str) -> bool {
    if let Some(suffix) = pattern.strip_prefix("**/") {
        return file_path.ends_with(suffix) || file_path.contains(&format!("/{}", suffix));
    }
    if pattern.contains('*') {
        let regex_str = format!("^{}$", pattern.replace('*', ".*"));
        if let Ok(re) = Regex::new(&regex_str) {
            return re.is_match(file_path);
        }
    }
    file_path == pattern || file_path.ends_with(&format!("/{}", pattern))
}
