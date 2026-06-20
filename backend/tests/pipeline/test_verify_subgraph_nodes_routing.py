from backend.pipeline.subgraphs.verify.graph import _route_verify_start, _route_after_profile
from backend.pipeline.subgraphs.verify.arbitrate import _compute_dim_confidence

def test_route_verify_start():
    # strict 模式下流向 atomize
    state_strict = {"verification_level": "strict"}
    assert _route_verify_start(state_strict) == "atomize"

    # standard 模式下也流向 atomize
    state_std = {"verification_level": "standard"}
    assert _route_verify_start(state_std) == "atomize"

    # skip 模式下跳过 atomize，直接流向 profile
    state_skip = {"verification_level": "skip"}
    assert _route_verify_start(state_skip) == "profile"

def test_route_after_profile():
    # strict 模式下流向 tripartite
    state_strict = {"verification_level": "strict"}
    assert _route_after_profile(state_strict) == "tripartite"

    # standard 模式下也流向 tripartite
    state_std = {"verification_level": "standard"}
    assert _route_after_profile(state_std) == "tripartite"

    # skip 模式下跳过 tripartite，直接流向 arbitrate
    state_skip = {"verification_level": "skip"}
    assert _route_after_profile(state_skip) == "arbitrate"

def test_compute_dim_confidence_no_claims_standard():
    # 在 standard 模式下，当 dim_claims 为空，应该基于该维度的信源的 credibility 计算均值
    dim_sources = [
        {"url": "https://gov.cn/news1", "dimension": "维度A"},
        {"url": "https://zhihu.com/question1", "dimension": "维度A"}
    ]
    source_profiles = {
        "https://gov.cn/news1": {"credibility": 1.0, "source_type": "official"},
        "https://zhihu.com/question1": {"credibility": 0.7, "source_type": "community"}
    }
    
    score = _compute_dim_confidence(
        dim="维度A",
        dim_claims=[],
        is_conflict=False,
        is_insufficient=False,
        has_data=True,
        dim_sources=dim_sources,
        source_profiles=source_profiles
    )
    
    # 均值应为 (1.0 + 0.7) / 2 = 0.85
    assert score == 0.85

def test_compute_dim_confidence_no_claims_no_sources():
    # 如果既没有 claims 也没有 sources，应该兜底为 _DIM_CONF_INSUFFICIENT (0.5)
    score = _compute_dim_confidence(
        dim="维度A",
        dim_claims=[],
        is_conflict=False,
        is_insufficient=False,
        has_data=True,
        dim_sources=[],
        source_profiles={}
    )
    assert score == 0.5
