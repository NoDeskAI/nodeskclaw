use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;

use futures_util::{SinkExt, StreamExt};
use tokio::net::TcpStream;
use tokio::sync::{Mutex, oneshot};
use tokio_tungstenite::{MaybeTlsStream, WebSocketStream, connect_async, tungstenite::Message};
use tracing::{error, info, warn};

use crate::types::{
    AfterResult, BeforeResult, WsContext, WsExecResult, WsRequest, WsResponse,
};

type WsStream = WebSocketStream<MaybeTlsStream<TcpStream>>;

static COUNTER: AtomicU64 = AtomicU64::new(0);

fn next_id() -> String {
    format!("r-{}", COUNTER.fetch_add(1, Ordering::Relaxed) + 1)
}

pub struct SecurityWsClient {
    write: Arc<Mutex<Option<futures_util::stream::SplitSink<WsStream, Message>>>>,
    pending: Arc<Mutex<HashMap<String, oneshot::Sender<serde_json::Value>>>>,
}

impl SecurityWsClient {
    pub fn new() -> Self {
        Self {
            write: Arc::new(Mutex::new(None)),
            pending: Arc::new(Mutex::new(HashMap::new())),
        }
    }

    pub async fn connect(&self) {
        let endpoint = Self::endpoint();
        info!("Connecting to {}", endpoint.split('?').next().unwrap_or(&endpoint));

        let ws = match connect_async(&endpoint).await {
            Ok((stream, _)) => stream,
            Err(e) => {
                warn!("WebSocket connection failed: {}", e);
                return;
            }
        };

        info!("WebSocket connected");

        let (sink, stream) = ws.split();
        *self.write.lock().await = Some(sink);

        let pending = Arc::clone(&self.pending);
        tokio::spawn(async move {
            Self::recv_loop(stream, pending).await;
        });
    }

    async fn recv_loop(
        mut stream: futures_util::stream::SplitStream<WsStream>,
        pending: Arc<Mutex<HashMap<String, oneshot::Sender<serde_json::Value>>>>,
    ) {
        while let Some(msg) = stream.next().await {
            let text = match msg {
                Ok(Message::Text(t)) => t,
                Ok(Message::Close(_)) => break,
                Err(e) => {
                    error!("WebSocket read error: {}", e);
                    break;
                }
                _ => continue,
            };

            let resp: WsResponse = match serde_json::from_str(&text) {
                Ok(r) => r,
                Err(_) => continue,
            };

            if resp.msg_type == "result" {
                if let Some(tx) = pending.lock().await.remove(&resp.id) {
                    let result = resp.result.unwrap_or(serde_json::json!({"action": "allow"}));
                    let _ = tx.send(result);
                }
            }
        }

        let mut map = pending.lock().await;
        for (_, tx) in map.drain() {
            let _ = tx.send(serde_json::json!({"action": "allow"}));
        }
    }

    fn endpoint() -> String {
        let base = std::env::var("SECURITY_WS_ENDPOINT")
            .or_else(|_| std::env::var("NODESKCLAW_BACKEND_URL"))
            .unwrap_or_else(|_| "ws://localhost:8000".into());
        let url = base.replace("http://", "ws://").replace("https://", "wss://");
        let token = std::env::var("NODESKCLAW_API_TOKEN").unwrap_or_default();
        format!("{}/api/v1/security/ws?token={}", url, token)
    }

    fn build_ctx(tool_name: &str, params: &serde_json::Value) -> WsContext {
        WsContext {
            tool_name: tool_name.to_string(),
            params: params.clone(),
            agent_instance_id: std::env::var("AGENT_INSTANCE_ID").unwrap_or_default(),
            workspace_id: std::env::var("WORKSPACE_ID").unwrap_or_default(),
            timestamp: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_secs_f64(),
        }
    }

    pub async fn evaluate_before(
        &self,
        tool_name: &str,
        params: &serde_json::Value,
    ) -> BeforeResult {
        let guard = self.write.lock().await;
        if guard.is_none() {
            return BeforeResult::default();
        }
        drop(guard);

        let id = next_id();
        let (tx, rx) = oneshot::channel();
        self.pending.lock().await.insert(id.clone(), tx);

        let req = WsRequest {
            msg_type: "evaluate_before".into(),
            id: id.clone(),
            ctx: Self::build_ctx(tool_name, params),
            exec_result: None,
        };

        let msg = match serde_json::to_string(&req) {
            Ok(s) => s,
            Err(_) => {
                self.pending.lock().await.remove(&id);
                return BeforeResult::default();
            }
        };

        {
            let mut guard = self.write.lock().await;
            if let Some(ref mut sink) = *guard {
                if sink.send(Message::Text(msg.into())).await.is_err() {
                    self.pending.lock().await.remove(&id);
                    return BeforeResult::default();
                }
            }
        }

        match rx.await {
            Ok(val) => serde_json::from_value(val).unwrap_or_default(),
            Err(_) => BeforeResult::default(),
        }
    }

    pub async fn evaluate_after(
        &self,
        tool_name: &str,
        params: &serde_json::Value,
        output: &str,
        exec_error: Option<&str>,
        duration_ms: Option<f64>,
    ) -> AfterResult {
        let guard = self.write.lock().await;
        if guard.is_none() {
            return AfterResult::default();
        }
        drop(guard);

        let id = next_id();
        let (tx, rx) = oneshot::channel();
        self.pending.lock().await.insert(id.clone(), tx);

        let req = WsRequest {
            msg_type: "evaluate_after".into(),
            id: id.clone(),
            ctx: Self::build_ctx(tool_name, params),
            exec_result: Some(WsExecResult {
                result: Some(output.to_string()),
                error: exec_error.map(|s| s.to_string()),
                duration_ms,
            }),
        };

        let msg = match serde_json::to_string(&req) {
            Ok(s) => s,
            Err(_) => {
                self.pending.lock().await.remove(&id);
                return AfterResult::default();
            }
        };

        {
            let mut guard = self.write.lock().await;
            if let Some(ref mut sink) = *guard {
                if sink.send(Message::Text(msg.into())).await.is_err() {
                    self.pending.lock().await.remove(&id);
                    return AfterResult::default();
                }
            }
        }

        match rx.await {
            Ok(val) => serde_json::from_value(val).unwrap_or_default(),
            Err(_) => AfterResult::default(),
        }
    }

    pub async fn disconnect(&self) {
        let mut guard = self.write.lock().await;
        if let Some(ref mut sink) = *guard {
            let _ = sink.send(Message::Close(None)).await;
        }
        *guard = None;

        let mut map = self.pending.lock().await;
        for (_, tx) in map.drain() {
            let _ = tx.send(serde_json::json!({"action": "allow"}));
        }
    }
}
