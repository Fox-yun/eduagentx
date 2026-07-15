from app.services.resource_quality import evaluate_resource_quality


def _unit_content() -> dict:
    return {
        "introduction": "Python 变量与对象引用",
        "objectives": ["解释变量绑定", "验证共享引用"],
        "sections": [
            {"title": "变量名", "content": "变量名绑定对象。"},
            {"title": "共享引用", "content": "两个名称可以指向同一对象。"},
            {"title": "重新绑定", "content": "赋值可以改变名称指向。"},
        ],
        "practice_tasks": [{"description": "修改列表并比较 id"}],
        "summary": "对象有类型，变量名保存对象引用。",
    }


def test_pptx_quality_passes_with_complete_course_structure() -> None:
    result = evaluate_resource_quality(
        "pptx",
        _unit_content(),
        {"title": "变量与对象引用", "slide_count": 7},
    )

    assert result["score"] == 95
    assert result["passed"] is True
    assert result["grade"] == "excellent"
    assert result["rubric_version"] == "1.1"
    assert len(result["dimensions"]) == 5


def test_code_quality_checks_project_structure_and_safety() -> None:
    result = evaluate_resource_quality(
        "code_zip",
        _unit_content(),
        {
            "title": "对象引用实操",
            "file_count": 3,
            "files": ["README.md", "main.py", "test_example.py"],
        },
    )

    assert result["score"] == 95
    assert result["passed"] is True
    safety = next(item for item in result["dimensions"] if item["key"] == "safety")
    assert safety["score"] == 10


def test_incomplete_resource_is_flagged_for_review() -> None:
    result = evaluate_resource_quality("pptx", {}, {"slide_count": 0})

    assert result["score"] == 10
    assert result["passed"] is False
    assert result["grade"] == "needs_review"
    assert result["warnings"]


def test_narrated_video_quality_checks_voice_captions_and_slides() -> None:
    result = evaluate_resource_quality(
        "narrated_video",
        _unit_content(),
        {
            "title": "对象引用语音微课",
            "description": "课件、语音和字幕合成视频。",
            "slide_count": 6,
            "captions_vtt": "WEBVTT\n\n00:00:00.000 --> 00:00:03.000\n对象引用",
            "tts_model": "FunAudioLLM/CosyVoice2-0.5B",
            "tts_voice": "FunAudioLLM/CosyVoice2-0.5B:anna",
        },
    )

    assert result["score"] == 100
    assert result["passed"] is True
    design = next(item for item in result["dimensions"] if item["key"] == "learning_design")
    assert "字幕与语音配置：True/True" in design["summary"]


def test_unsafe_code_extension_fails_safety_dimension() -> None:
    result = evaluate_resource_quality(
        "code_zip",
        _unit_content(),
        {
            "title": "不安全项目",
            "file_count": 4,
            "files": ["README.md", "main.py", "test_main.py", "run.ps1"],
        },
    )

    safety = next(item for item in result["dimensions"] if item["key"] == "safety")
    assert safety["score"] == 0
    assert "run.ps1" in safety["summary"]
