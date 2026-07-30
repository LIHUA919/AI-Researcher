from benchmark.real_smoke.one_layer_vq.summarize import summarize_verified_metrics


def test_report_computes_paired_deltas_with_metric_directions():
    verified = {
        1: {
            "vanilla": {
                "codebook_utilization": 0.2,
                "codebook_perplexity": 2.0,
                "reconstruction_mse": 0.04,
                "reconstruction_psnr_db": 14.0,
            },
            "simvq": {
                "codebook_utilization": 0.3,
                "codebook_perplexity": 3.0,
                "reconstruction_mse": 0.03,
                "reconstruction_psnr_db": 15.0,
            },
        },
        2: {
            "vanilla": {
                "codebook_utilization": 0.4,
                "codebook_perplexity": 4.0,
                "reconstruction_mse": 0.02,
                "reconstruction_psnr_db": 16.0,
            },
            "simvq": {
                "codebook_utilization": 0.3,
                "codebook_perplexity": 3.0,
                "reconstruction_mse": 0.03,
                "reconstruction_psnr_db": 15.0,
            },
        },
    }

    summary = summarize_verified_metrics(verified)

    assert summary["paired_deltas"][0]["codebook_utilization"] == 0.1
    assert summary["paired_deltas"][0]["reconstruction_mse"] == 0.01
    assert summary["paired_deltas"][1]["codebook_utilization"] == -0.1
    assert summary["paired_deltas"][1]["reconstruction_mse"] == -0.01
    assert summary["mean_paired_delta"]["codebook_utilization"] == 0.0
    assert summary["mean_paired_delta"]["reconstruction_mse"] == 0.0
