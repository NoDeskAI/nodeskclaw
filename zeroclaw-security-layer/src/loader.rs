use std::path::Path;

use tracing::{error, info, warn};

use crate::plugins::policy_gate::PolicyGatePlugin;
use crate::types::{SecurityConfig, SecurityPlugin};

const DEFAULT_CONFIG_PATHS: &[&str] = &[
    "/opt/zeroclaw/config/security-policy.json",
];

pub fn load_security_config() -> SecurityConfig {
    let config_path = std::env::var("SECURITY_POLICY_PATH").ok().or_else(|| {
        DEFAULT_CONFIG_PATHS
            .iter()
            .find(|p| Path::new(p).is_file())
            .map(|p| p.to_string())
    });

    let Some(path) = config_path else {
        warn!("No security config found, pipeline will have no plugins");
        return SecurityConfig {
            plugins: Vec::new(),
        };
    };

    match std::fs::read_to_string(&path) {
        Ok(content) => match serde_json::from_str::<SecurityConfig>(&content) {
            Ok(config) => {
                info!(
                    "Loaded security config from {} ({} plugin entries)",
                    path,
                    config.plugins.len()
                );
                config
            }
            Err(e) => {
                error!("Failed to parse security config at {}: {}", path, e);
                SecurityConfig {
                    plugins: Vec::new(),
                }
            }
        },
        Err(e) => {
            error!("Failed to read security config at {}: {}", path, e);
            SecurityConfig {
                plugins: Vec::new(),
            }
        }
    }
}

pub async fn create_plugins(
    config: &SecurityConfig,
) -> Vec<Box<dyn SecurityPlugin>> {
    let mut plugins: Vec<Box<dyn SecurityPlugin>> = Vec::new();

    for entry in &config.plugins {
        if !entry.enabled {
            continue;
        }

        let mut plugin: Box<dyn SecurityPlugin> = match entry.id.as_str() {
            "policy-gate" => Box::new(PolicyGatePlugin::new(entry.priority)),
            unknown => {
                warn!("Unknown plugin '{}', skipping", unknown);
                continue;
            }
        };

        match plugin.initialize(entry.config.clone()).await {
            Ok(()) => {
                info!(
                    "Plugin '{}' initialized (priority={})",
                    entry.id, entry.priority
                );
                plugins.push(plugin);
            }
            Err(e) => {
                error!("Failed to initialize plugin '{}': {}", entry.id, e);
            }
        }
    }

    plugins
}
