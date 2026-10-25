use indicatif::ProgressBar;
use std::{thread, time::Duration};

fn main() {
    let bar = ProgressBar::new(60);
    for _ in 0..60 {
        bar.inc(1);
        thread::sleep(Duration::from_millis(80));
    }
    bar.finish();
}
