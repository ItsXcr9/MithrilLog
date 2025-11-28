use bloomfilter::Bloom;
use rand::Rng;
use std::collections::HashMap;
use serde_json::Value;

pub struct BloomDeduper {
    filter: Bloom<Vec<u8>>,
}

impl BloomDeduper {
    pub fn new(capacity: usize, error_rate: f64) -> Self {
        // Bloom::new_for_fp_rate(items_count, fp_rate)
        Self {
            filter: Bloom::new_for_fp_rate(capacity, error_rate),
        }
    }

    pub fn seen(&mut self, key: &[u8]) -> bool {
        // check_and_set returns true if item was already present
        self.filter.check_and_set(&key.to_vec())
    }

    pub fn reset(&mut self) {
        self.filter.clear();
    }
}

pub struct ReservoirSampler {
    size: usize,
    reservoir: HashMap<String, Vec<Value>>,
    counts: HashMap<String, usize>,
    pattern_counts: HashMap<String, usize>,
}

impl ReservoirSampler {
    pub fn new(size: usize) -> Self {
        Self {
            size,
            reservoir: HashMap::new(),
            counts: HashMap::new(),
            pattern_counts: HashMap::new(),
        }
    }

    pub fn add(&mut self, key: String, pattern: String, event: Value) {
        let count = self.counts.entry(key.clone()).or_insert(0);
        *count += 1;

        let p_count = self.pattern_counts.entry(pattern.clone()).or_insert(0);
        *p_count += 1;

        let samples = self.reservoir.entry(key).or_insert_with(Vec::new);
        
        if samples.len() < self.size {
            samples.push(event);
        } else {
            let mut rng = rand::thread_rng();
            let index = rng.gen_range(0..*count);
            if index < self.size {
                samples[index] = event;
            }
        }
    }

    pub fn register_duplicate(&mut self, pattern: String) {
        let count = self.pattern_counts.entry(pattern).or_insert(0);
        *count += 1;
    }

    pub fn totals(&self) -> HashMap<String, usize> {
        self.pattern_counts.clone()
    }

    pub fn reset(&mut self) {
        self.reservoir.clear();
        self.counts.clear();
        self.pattern_counts.clear();
    }

    pub fn snapshot(&self) -> HashMap<String, Vec<Value>> {
        self.reservoir.clone()
    }
}
