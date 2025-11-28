use clap::Parser;
use std::path::PathBuf;

#[derive(Parser, Debug, Clone)]
#[command(author, version, about, long_about = None)]
pub struct Config {
    #[arg(long, env = "INGEST_HOST", default_value = "0.0.0.0")]
    pub host: String,

    #[arg(long, env = "INGEST_UDP_PORT", default_value_t = 5514)]
    pub udp_port: u16,

    #[arg(long, env = "INGEST_TCP_PORT", default_value_t = 5614)]
    pub tcp_port: u16,

    #[arg(long, env = "INGEST_BUCKET_DIR", default_value = "./data/buckets")]
    pub bucket_dir: PathBuf,

    #[arg(long, env = "INGEST_MAX_BUCKET_MINUTES", default_value_t = 1)]
    pub max_bucket_minutes: u64,

    #[arg(long, env = "INGEST_BLOOM_ERROR_RATE", default_value_t = 0.0001)]
    pub bloom_error_rate: f64,

    #[arg(long, env = "INGEST_RESERVOIR_SIZE", default_value_t = 200)]
    pub reservoir_size: usize,

    #[arg(long, env = "INGEST_FORWARD_TO_HOST")]
    pub forward_to_host: Option<String>,

    #[arg(long, env = "INGEST_FORWARD_TO_PORT")]
    pub forward_to_port: Option<u16>,
    
    #[arg(long, env = "TIMEZONE", default_value = "UTC")]
    pub timezone: String,
}
