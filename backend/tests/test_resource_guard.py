from crawler import resource_guard


def test_throttle_multiplier_changes_by_pressure(monkeypatch):
    monkeypatch.setattr(resource_guard.settings, "crawler_auto_throttle_enabled", True)
    monkeypatch.setattr(resource_guard.settings, "crawler_memory_pressure_warn_pct", 80.0)
    monkeypatch.setattr(resource_guard.settings, "crawler_memory_pressure_critical_pct", 90.0)
    monkeypatch.setattr(resource_guard.settings, "crawler_cpu_pressure_warn_pct", 85.0)
    monkeypatch.setattr(resource_guard.settings, "crawler_cpu_pressure_critical_pct", 95.0)
    monkeypatch.setattr(resource_guard.settings, "crawler_resource_throttle_max_factor", 3.0)

    warning_sample = resource_guard.ResourceSample(
        sampled_mono=0.0,
        host_mem_used_percent=84.0,
        host_mem_available_mb=1024.0,
        host_cpu_percent=40.0,
        process_rss_mb=300.0,
        process_cpu_percent=25.0,
    )
    critical_sample = resource_guard.ResourceSample(
        sampled_mono=0.0,
        host_mem_used_percent=93.0,
        host_mem_available_mb=512.0,
        host_cpu_percent=92.0,
        process_rss_mb=600.0,
        process_cpu_percent=40.0,
    )

    monkeypatch.setattr(resource_guard, "get_resource_sample", lambda force=False: warning_sample)
    factor, state = resource_guard.get_throttle_multiplier()
    assert state == "warning"
    assert factor > 1.0

    monkeypatch.setattr(resource_guard, "get_resource_sample", lambda force=False: critical_sample)
    factor2, state2 = resource_guard.get_throttle_multiplier()
    assert state2 == "critical"
    assert factor2 >= factor


def test_effective_worker_limit(monkeypatch):
    monkeypatch.setattr(resource_guard.settings, "crawler_dynamic_concurrency_enabled", True)

    monkeypatch.setattr(resource_guard, "get_throttle_multiplier", lambda: (1.5, "warning"))
    assert resource_guard.effective_worker_limit(4) == 3

    monkeypatch.setattr(resource_guard, "get_throttle_multiplier", lambda: (2.4, "critical"))
    assert resource_guard.effective_worker_limit(4) == 1

    monkeypatch.setattr(resource_guard.settings, "crawler_dynamic_concurrency_enabled", False)
    assert resource_guard.effective_worker_limit(4) == 4
