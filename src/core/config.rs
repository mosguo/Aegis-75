use anyhow::{anyhow, Result};
use serde::Serialize;
use url::Url;

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum Role {
    ControlPlane,
    ExecutionCore,
    TradingUnit,
    Hybrid,
}

impl std::fmt::Display for Role {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let s = match self {
            Role::ControlPlane => "control-plane",
            Role::ExecutionCore => "execution-core",
            Role::TradingUnit => "trading-unit",
            Role::Hybrid => "hybrid",
        };
        write!(f, "{s}")
    }
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum ExecutionMode {
    Paper,
    Live,
}

impl std::fmt::Display for ExecutionMode {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let s = match self {
            ExecutionMode::Paper => "paper",
            ExecutionMode::Live => "live",
        };
        write!(f, "{s}")
    }
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum HostClass {
    Cloud,
    Byoh,
}

impl std::fmt::Display for HostClass {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let s = match self {
            HostClass::Cloud => "cloud",
            HostClass::Byoh => "byoh",
        };
        write!(f, "{s}")
    }
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum HubMode {
    Edge,
    DataExecutionHub,
}

impl std::fmt::Display for HubMode {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let s = match self {
            HubMode::Edge => "edge",
            HubMode::DataExecutionHub => "data-execution-hub",
        };
        write!(f, "{s}")
    }
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum SigningMode {
    Disabled,
    LocalEnv,
    Hsm,
}

impl std::fmt::Display for SigningMode {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let s = match self {
            SigningMode::Disabled => "disabled",
            SigningMode::LocalEnv => "local-env",
            SigningMode::Hsm => "hsm",
        };
        write!(f, "{s}")
    }
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum DeploymentTarget {
    Zeabur,
    Byoh,
    Generic,
}

impl std::fmt::Display for DeploymentTarget {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let s = match self {
            DeploymentTarget::Zeabur => "zeabur",
            DeploymentTarget::Byoh => "byoh",
            DeploymentTarget::Generic => "generic",
        };
        write!(f, "{s}")
    }
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum IdentitySource {
    Environment,
    Static,
}

impl std::fmt::Display for IdentitySource {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let s = match self {
            IdentitySource::Environment => "environment",
            IdentitySource::Static => "static",
        };
        write!(f, "{s}")
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct RuntimeTuning {
    pub zero_copy_requested: bool,
    pub hugepages_requested: bool,
    pub cpu_affinity_requested: bool,
    pub cpu_affinity_cores: Vec<usize>,
}

#[derive(Debug, Clone, Serialize)]
pub struct DeploymentProfile {
    pub active_target: DeploymentTarget,
    pub future_target: DeploymentTarget,
    pub migration_stage: String,
    pub zeabur_compatible: bool,
    pub byoh_cutover_ready: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct HostIdentity {
    pub source: IdentitySource,
    pub logical_host_id: String,
    pub runtime_host_id: String,
    pub logical_site: String,
    pub physical_host_planned: bool,
    pub physical_host_id: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ByohProfile {
    pub enabled: bool,
    pub host_class: HostClass,
    pub hub_mode: HubMode,
    pub physical_site: String,
    pub low_latency_gateway_enabled: bool,
    pub analytics_archive_enabled: bool,
    pub signing_mode: SigningMode,
    pub market_data_ws_enabled: bool,
    pub fixed_ip_expected: bool,
    pub data_lake_path: String,
    pub telemetry_label: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct LoggingProfile {
    pub level: String,
    pub heartbeat_enabled: bool,
    pub heartbeat_interval_secs: u64,
}

#[derive(Debug, Clone, Serialize)]
pub struct StartupCheckReport {
    pub warnings: Vec<String>,
    pub architecture_errors: Vec<String>,
}

impl StartupCheckReport {
    pub fn passed(&self) -> bool {
        self.architecture_errors.is_empty()
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct Config {
    pub role: Role,
    pub node_id: String,
    pub region: String,
    pub cluster: String,
    pub bind_addr: String,
    pub public_base: Option<String>,
    pub execution_mode: ExecutionMode,
    pub market_scope: String,
    pub exchanges: Vec<String>,
    pub dex_networks: Vec<String>,
    pub zeroclaw_enabled: bool,
    pub zeroclaw_gateway_url: Option<Url>,
    pub zeroclaw_api_key: Option<String>,
    pub zeroclaw_channel: String,
    pub zeroclaw_model: String,
    pub deployment: DeploymentProfile,
    pub identity: HostIdentity,
    pub byoh: ByohProfile,
    pub tuning: RuntimeTuning,
    pub logging: LoggingProfile,
}

impl Config {
    pub fn from_env() -> Result<Self> {
        let byoh_enabled = parse_bool(&env_or("AEGIS_BYOH_ENABLED", "false"));
        let node_id = env_or("AEGIS_NODE_ID", "unknown-node");
        let logical_site = env_or("AEGIS_LOGICAL_SITE", "unassigned-logical-site");
        let deployment_active = parse_deployment_target(&env_or(
            "AEGIS_DEPLOYMENT_TARGET",
            default_deployment_target(),
        ))?;
        let deployment_future = parse_deployment_target(&env_or(
            "AEGIS_FUTURE_DEPLOYMENT_TARGET",
            default_future_deployment_target(byoh_enabled),
        ))?;

        Ok(Self {
            role: parse_role(&env_or("AEGIS_ROLE", "control-plane"))?,
            node_id,
            region: env_or("AEGIS_REGION", "global-sim"),
            cluster: env_or("AEGIS_CLUSTER", "aegis-75"),
            bind_addr: env_or("AEGIS_BIND_ADDR", "0.0.0.0:8080"),
            public_base: std::env::var("AEGIS_PUBLIC_BASE").ok(),
            execution_mode: parse_execution_mode(&env_or("AEGIS_EXECUTION_MODE", "paper"))?,
            market_scope: env_or("AEGIS_MARKET_SCOPE", "cex+dex-75"),
            exchanges: split_csv(&env_or(
                "AEGIS_EXCHANGES",
                "binance,okx,bybit,coinbase,kraken,gate",
            )),
            dex_networks: split_csv(&env_or(
                "AEGIS_DEX_NETWORKS",
                "ethereum,arbitrum,base,bnb-chain,solana",
            )),
            zeroclaw_enabled: parse_bool(&env_or("ZEROCLAW_ENABLED", "false")),
            zeroclaw_gateway_url: std::env::var("ZEROCLAW_GATEWAY_URL")
                .ok()
                .map(|v| Url::parse(&v))
                .transpose()?,
            zeroclaw_api_key: std::env::var("ZEROCLAW_API_KEY").ok(),
            zeroclaw_channel: env_or("ZEROCLAW_CHANNEL", "ops-default"),
            zeroclaw_model: env_or("ZEROCLAW_MODEL", "gpt-5.4-mini"),
            deployment: DeploymentProfile {
                active_target: deployment_active,
                future_target: deployment_future,
                migration_stage: env_or(
                    "AEGIS_MIGRATION_STAGE",
                    default_migration_stage(byoh_enabled),
                ),
                zeabur_compatible: parse_bool(&env_or("AEGIS_ZEABUR_COMPATIBLE", "true")),
                byoh_cutover_ready: parse_bool(&env_or(
                    "AEGIS_BYOH_CUTOVER_READY",
                    bool_str(byoh_enabled),
                )),
            },
            identity: HostIdentity {
                source: parse_identity_source(&env_or(
                    "AEGIS_IDENTITY_SOURCE",
                    "environment",
                ))?,
                logical_host_id: env_or("AEGIS_LOGICAL_HOST_ID", "aegis-node-logical-01"),
                runtime_host_id: env_or("AEGIS_RUNTIME_HOST_ID", "aegis-node-runtime-01"),
                logical_site,
                physical_host_planned: parse_bool(&env_or(
                    "AEGIS_PHYSICAL_HOST_PLANNED",
                    bool_str(byoh_enabled),
                )),
                physical_host_id: std::env::var("AEGIS_PHYSICAL_HOST_ID").ok(),
            },
            byoh: ByohProfile {
                enabled: byoh_enabled,
                host_class: parse_host_class(&env_or(
                    "AEGIS_HOST_CLASS",
                    default_host_class(byoh_enabled),
                ))?,
                hub_mode: parse_hub_mode(&env_or(
                    "AEGIS_HUB_MODE",
                    default_hub_mode(byoh_enabled),
                ))?,
                physical_site: env_or("AEGIS_PHYSICAL_SITE", "cht-lab-planned-site"),
                low_latency_gateway_enabled: parse_bool(&env_or(
                    "AEGIS_LOW_LATENCY_GATEWAY",
                    bool_str(byoh_enabled),
                )),
                analytics_archive_enabled: parse_bool(&env_or(
                    "AEGIS_ANALYTICS_ARCHIVE",
                    bool_str(byoh_enabled),
                )),
                signing_mode: parse_signing_mode(&env_or(
                    "AEGIS_SIGNING_MODE",
                    if byoh_enabled { "local-env" } else { "disabled" },
                ))?,
                market_data_ws_enabled: parse_bool(&env_or(
                    "AEGIS_MARKET_DATA_WS",
                    bool_str(byoh_enabled),
                )),
                fixed_ip_expected: parse_bool(&env_or("AEGIS_FIXED_IP_EXPECTED", "true")),
                data_lake_path: env_or("AEGIS_DATA_LAKE_PATH", "/var/lib/aegis-75/data-lake"),
                telemetry_label: env_or("AEGIS_TELEMETRY_LABEL", "standard"),
            },
            tuning: RuntimeTuning {
                zero_copy_requested: parse_bool(&env_or("AEGIS_ZERO_COPY", "true")),
                hugepages_requested: parse_bool(&env_or("AEGIS_HUGEPAGES", "false")),
                cpu_affinity_requested: parse_bool(&env_or("AEGIS_CPU_AFFINITY", "false")),
                cpu_affinity_cores: split_csv(&env_or("AEGIS_CPU_CORES", ""))
                    .into_iter()
                    .filter_map(|v| v.parse::<usize>().ok())
                    .collect(),
            },
            logging: LoggingProfile {
                level: env_or("AEGIS_LOG_LEVEL", "info"),
                heartbeat_enabled: parse_bool(&env_or("AEGIS_HEARTBEAT_ENABLED", "true")),
                heartbeat_interval_secs: env_or("AEGIS_HEARTBEAT_INTERVAL_SECS", "30")
                    .parse::<u64>()
                    .unwrap_or(30),
            },
        })
    }

    pub fn startup_checks(&self) -> StartupCheckReport {
        let mut warnings = Vec::new();
        let mut architecture_errors = Vec::new();

        if self.byoh.enabled && !matches!(self.byoh.host_class, HostClass::Byoh) {
            architecture_errors.push(
                "conflicting_config host_class=cloud but byoh_enabled=true".to_string(),
            );
        }

        if matches!(self.byoh.host_class, HostClass::Cloud)
            && matches!(self.byoh.hub_mode, HubMode::DataExecutionHub)
        {
            architecture_errors.push(
                "conflicting_config host_class=cloud but hub_mode=data-execution-hub".to_string(),
            );
        }

        if matches!(self.byoh.signing_mode, SigningMode::Hsm)
            && std::env::var("AEGIS_HSM_PROVIDER").is_err()
        {
            architecture_errors.push(
                "signing_mode=hsm but hsm_not_available (missing AEGIS_HSM_PROVIDER)".to_string(),
            );
        }

        if matches!(self.role, Role::ExecutionCore | Role::TradingUnit)
            && matches!(self.byoh.signing_mode, SigningMode::Disabled)
        {
            warnings.push("execution role without signing enabled".to_string());
        }

        if self.byoh.enabled && matches!(self.deployment.active_target, DeploymentTarget::Zeabur) {
            warnings.push("byoh_enabled=true but running on zeabur (simulation mode)".to_string());
        }

        if self.byoh.data_lake_path.trim().is_empty() {
            warnings.push("data_lake_path not set".to_string());
        }

        if self.tuning.cpu_affinity_requested && self.tuning.cpu_affinity_cores.is_empty() {
            warnings.push("cpu_affinity requested but cpu cores list is empty".to_string());
        }

        if self.zeroclaw_enabled && self.zeroclaw_gateway_url.is_none() {
            architecture_errors.push(
                "zeroclaw enabled but ZEROCLAW_GATEWAY_URL is missing".to_string(),
            );
        }

        StartupCheckReport {
            warnings,
            architecture_errors,
        }
    }
}

fn default_deployment_target() -> &'static str {
    "zeabur"
}

fn default_future_deployment_target(byoh_enabled: bool) -> &'static str {
    if byoh_enabled {
        "byoh"
    } else {
        "zeabur"
    }
}

fn default_migration_stage(byoh_enabled: bool) -> &'static str {
    if byoh_enabled {
        "zeabur-validation-before-byoh-cutover"
    } else {
        "cloud-only"
    }
}

fn default_host_class(byoh_enabled: bool) -> &'static str {
    if byoh_enabled {
        "byoh"
    } else {
        "cloud"
    }
}

fn default_hub_mode(byoh_enabled: bool) -> &'static str {
    if byoh_enabled {
        "data-execution-hub"
    } else {
        "edge"
    }
}

fn bool_str(v: bool) -> &'static str {
    if v {
        "true"
    } else {
        "false"
    }
}

fn env_or(key: &str, fallback: &str) -> String {
    std::env::var(key).unwrap_or_else(|_| fallback.to_string())
}

fn parse_bool(v: &str) -> bool {
    matches!(v.to_ascii_lowercase().as_str(), "1" | "true" | "yes" | "on")
}

fn split_csv(v: &str) -> Vec<String> {
    v.split(',')
        .map(str::trim)
        .filter(|x| !x.is_empty())
        .map(ToOwned::to_owned)
        .collect()
}

fn parse_role(value: &str) -> Result<Role> {
    match value {
        "control-plane" => Ok(Role::ControlPlane),
        "execution-core" => Ok(Role::ExecutionCore),
        "trading-unit" => Ok(Role::TradingUnit),
        "hybrid" => Ok(Role::Hybrid),
        _ => Err(anyhow!("unsupported AEGIS_ROLE: {value}")),
    }
}

fn parse_execution_mode(value: &str) -> Result<ExecutionMode> {
    match value {
        "paper" => Ok(ExecutionMode::Paper),
        "live" => Ok(ExecutionMode::Live),
        _ => Err(anyhow!("unsupported AEGIS_EXECUTION_MODE: {value}")),
    }
}

fn parse_host_class(value: &str) -> Result<HostClass> {
    match value {
        "cloud" => Ok(HostClass::Cloud),
        "byoh" => Ok(HostClass::Byoh),
        _ => Err(anyhow!("unsupported AEGIS_HOST_CLASS: {value}")),
    }
}

fn parse_hub_mode(value: &str) -> Result<HubMode> {
    match value {
        "edge" => Ok(HubMode::Edge),
        "data-execution-hub" => Ok(HubMode::DataExecutionHub),
        _ => Err(anyhow!("unsupported AEGIS_HUB_MODE: {value}")),
    }
}

fn parse_signing_mode(value: &str) -> Result<SigningMode> {
    match value {
        "disabled" => Ok(SigningMode::Disabled),
        "local-env" => Ok(SigningMode::LocalEnv),
        "hsm" => Ok(SigningMode::Hsm),
        _ => Err(anyhow!("unsupported AEGIS_SIGNING_MODE: {value}")),
    }
}

fn parse_deployment_target(value: &str) -> Result<DeploymentTarget> {
    match value {
        "zeabur" => Ok(DeploymentTarget::Zeabur),
        "byoh" => Ok(DeploymentTarget::Byoh),
        "generic" => Ok(DeploymentTarget::Generic),
        _ => Err(anyhow!("unsupported AEGIS_DEPLOYMENT_TARGET: {value}")),
    }
}

fn parse_identity_source(value: &str) -> Result<IdentitySource> {
    match value {
        "environment" => Ok(IdentitySource::Environment),
        "static" => Ok(IdentitySource::Static),
        _ => Err(anyhow!("unsupported AEGIS_IDENTITY_SOURCE: {value}")),
    }
}
