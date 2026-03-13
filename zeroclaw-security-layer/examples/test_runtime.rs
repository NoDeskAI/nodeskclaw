//! Container-side integration test for ZeroClaw security layer.
//!
//! Verifies:
//! 1. SecurityWsClient connects and exchanges evaluate_before / evaluate_after
//! 2. SecuredTool wrapper invokes the pipeline around a mock tool
//!
//! Run inside Docker:
//!   SECURITY_WS_ENDPOINT=ws://host.docker.internal:8000
//!   SECURITY_LAYER_ENABLED=true

use std::sync::Arc;

use async_trait::async_trait;
use serde_json::json;

use zeroclaw_security_layer::secured_tool::{SecuredTool, Tool, ToolResult};
use zeroclaw_security_layer::types::{AfterAction, BeforeAction};
use zeroclaw_security_layer::ws_client::SecurityWsClient;

struct Results {
    pass: u32,
    fail: u32,
}

impl Results {
    fn new() -> Self {
        Self { pass: 0, fail: 0 }
    }

    fn check(&mut self, name: &str, ok: bool, detail: &str) {
        if ok {
            self.pass += 1;
            println!("[PASS] {name}");
        } else {
            self.fail += 1;
            eprintln!("[FAIL] {name} — {detail}");
        }
    }
}

struct EchoTool;

#[async_trait]
impl Tool for EchoTool {
    fn name(&self) -> &str {
        "echo"
    }
    fn description(&self) -> &str {
        "echoes input"
    }
    fn parameters(&self) -> serde_json::Value {
        json!({})
    }
    async fn execute(&self, args: serde_json::Value) -> ToolResult {
        ToolResult {
            success: true,
            output: format!("echoed: {args}"),
            error: None,
        }
    }
}

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt::init();

    let endpoint =
        std::env::var("SECURITY_WS_ENDPOINT").unwrap_or_else(|_| "ws://localhost:8000".into());
    let enabled =
        std::env::var("SECURITY_LAYER_ENABLED").unwrap_or_else(|_| "true".into());
    println!("Security WS endpoint: {endpoint}");
    println!("Security layer enabled: {enabled}");

    let mut r = Results::new();

    // ── Test 1: WS client direct ────────────────────────
    println!("--- Test 1: WebSocket client direct ---");
    let client = Arc::new(SecurityWsClient::new());
    client.connect().await;
    tokio::time::sleep(std::time::Duration::from_secs(1)).await;

    let after = client
        .evaluate_after(
            "exec",
            &json!({"command": "cat creds.txt"}),
            "aws_access_key_id = AKIAIOSFODNN7EXAMPLE",
            None,
            Some(10.0),
        )
        .await;
    println!("  evaluate_after(aws key) -> action={:?}", after.action);
    r.check(
        "WS connected (via DLP flag)",
        after.action == AfterAction::Flag,
        &format!("got {:?}, expected Flag", after.action),
    );

    let before1 = client.evaluate_before("exec", &json!({"command": "ls -la"})).await;
    r.check(
        "evaluate_before(ls) -> allow",
        before1.action == BeforeAction::Allow,
        &format!("got {:?}", before1.action),
    );

    let before2 = client
        .evaluate_before("exec", &json!({"command": "sudo rm -rf /"}))
        .await;
    println!("  evaluate_before(sudo rm) -> action={:?}", before2.action);
    r.check(
        "evaluate_before(sudo rm) returns result",
        before2.action == BeforeAction::Allow || before2.action == BeforeAction::Deny,
        &format!("got {:?}", before2.action),
    );

    client.disconnect().await;
    println!("  WS disconnected");

    // ── Test 2: SecuredTool wrapper ─────────────────────
    println!("--- Test 2: SecuredTool wrapper ---");
    let client2 = Arc::new(SecurityWsClient::new());
    client2.connect().await;
    tokio::time::sleep(std::time::Duration::from_secs(1)).await;

    let secured = SecuredTool::new(EchoTool, client2.clone());
    let result = secured.execute(json!({"message": "hello"})).await;
    r.check(
        "SecuredTool execute returns result",
        result.success,
        &format!("success={}", result.success),
    );
    let truncated = &result.output[..result.output.len().min(100)];
    println!("  SecuredTool output: {truncated}");

    client2.disconnect().await;

    // ── Summary ─────────────────────────────────────────
    println!();
    println!("{}", "=".repeat(50));
    println!("Results: {} passed, {} failed", r.pass, r.fail);
    println!("{}", "=".repeat(50));

    if r.fail > 0 {
        std::process::exit(1);
    }
    println!("All tests passed.");
}
