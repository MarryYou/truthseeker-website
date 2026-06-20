from backend.pipeline.graph import _resolve_verification_level, _route_after_extract

def test_resolve_verification_level_static_override():
    # 静态覆盖有最高优先级
    state = {
        "control": {"speed": "research_pipeline"},
        "runtime": {
            "pipeline": {
                "dedup_intensity": "strict",
                "strategy_overrides": {"verification_level": "strict"}
            }
        }
    }
    assert _resolve_verification_level(state) == "strict"

def test_resolve_verification_level_relaxed_upgrade():
    # relaxed 模式下，如果默认是 standard，自适应升级为 strict
    state = {
        "control": {"speed": "expert_search"},
        "runtime": {
            "pipeline": {
                "dedup_intensity": "relaxed",
                "strategy_overrides": {}
            }
        }
    }
    assert _resolve_verification_level(state) == "strict"

def test_resolve_verification_level_strict_downgrade():
    # strict 模式（常识科普）下，核验自适应降级为 skip
    state = {
        "control": {"speed": "research_pipeline"},
        "runtime": {
            "pipeline": {
                "dedup_intensity": "strict",
                "strategy_overrides": {}
            }
        }
    }
    assert _resolve_verification_level(state) == "skip"

def test_resolve_verification_level_standard_fallback():
    # standard 模式下，维持默认值
    state = {
        "control": {"speed": "expert_search"},
        "runtime": {
            "pipeline": {
                "dedup_intensity": "standard",
                "strategy_overrides": {}
            }
        }
    }
    assert _resolve_verification_level(state) == "standard"

def test_route_after_extract_skip():
    # 验证当 level 被映射为 skip 时，路由直接跳过验证，返回 report
    state = {
        "control": {"speed": "research_pipeline"},
        "runtime": {
            "pipeline": {
                "dedup_intensity": "strict",
                "strategy_overrides": {}
            }
        }
    }
    assert _route_after_extract(state) == "report"

def test_route_after_extract_verify():
    # 验证当 level 不为 skip 时，路由进入 verify
    state = {
        "control": {"speed": "research_pipeline"},
        "runtime": {
            "pipeline": {
                "dedup_intensity": "relaxed",
                "strategy_overrides": {}
            }
        }
    }
    assert _route_after_extract(state) == "verify"
