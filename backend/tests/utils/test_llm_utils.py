from backend.utils.llm_utils import extract_llm_content, parse_llm_json

def test_extract_llm_content_stripping():
    """测试提取并剥离 LLM 内容中的 markdown 块"""
    # 1. 包含 json 代码块
    raw_1 = "这是分析结果：\n```json\n{\"a\": 1}\n```\n祝好。"
    assert extract_llm_content(raw_1) == "{\"a\": 1}"
    
    # 2. 包含 think 标签
    raw_2 = "<think>思考过程...</think>直接回答内容"
    assert extract_llm_content(raw_2) == "直接回答内容"
    
    # 3. 混合情况
    raw_3 = "<think>...</think>\n```json\n[1, 2]\n```"
    assert extract_llm_content(raw_3) == "[1, 2]"

def test_parse_llm_json_robustness():
    """测试 JSON 解析的鲁棒性"""
    # 1. 正常解析
    assert parse_llm_json("{\"key\": \"val\"}") == {"key": "val"}
    
    # 2. 包含非法 NUL 字节
    assert parse_llm_json("{\"a\": \"b\\u0000\"}") == {"a": "b"}
    
    # 3. 非法 JSON 报错
    import pytest
    import json
    with pytest.raises(json.JSONDecodeError):
        parse_llm_json("invalid json")
