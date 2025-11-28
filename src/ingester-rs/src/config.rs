use clap::Parser;
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

#[derive(Parser, Debug, Clone)]
#[command(author, version, about, long_about = None)]
pub struct CliArgs {
    #[arg(long, env = "INGESTER_CONFIG", default_value = "configs/ingester.yaml")]
    pub config: PathBuf,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConfigFile {
    pub ingester: Config,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Config {
    #[serde(default = "default_host")]
    pub host: String,

    #[serde(default = "default_udp_port")]
    pub udp_port: u16,

    #[serde(default = "default_tcp_port")]
    pub tcp_port: u16,

    #[serde(default = "default_bucket_dir")]
    pub bucket_dir: PathBuf,

    #[serde(default = "default_max_bucket_minutes")]
    pub max_bucket_minutes: u64,

    #[serde(default = "default_bloom_error_rate")]
    pub bloom_error_rate: f64,

    #[serde(default = "default_reservoir_size")]
    pub reservoir_size: usize,

    #[serde(default)]
    pub forward_to_host: Option<String>,

    #[serde(default)]
    pub forward_to_port: Option<u16>,
    
    #[serde(default = "default_timezone")]
    pub timezone: String,
}

// Default value functions
fn default_host() -> String { "0.0.0.0".to_string() }
fn default_udp_port() -> u16 { 5514 }
fn default_tcp_port() -> u16 { 5614 }
fn default_bucket_dir() -> PathBuf { PathBuf::from("./data/buckets") }
fn default_max_bucket_minutes() -> u64 { 1 }
fn default_bloom_error_rate() -> f64 { 0.0001 }
fn default_reservoir_size() -> usize { 200 }
fn default_timezone() -> String { "UTC".to_string() }

impl Config {
    pub fn from_file(path: &PathBuf) -> anyhow::Result<Self> {
        let contents = std::fs::read_to_string(path)?;
        let config_file: ConfigFile = serde_yaml::from_str(&contents)?;
        Ok(config_file.ingester)
    }
    
    pub fn load() -> anyhow::Result<Self> {
        let cli = CliArgs::parse();
        Self::from_file(&cli.config)
    }
}
