"""Worker handlers for multimodal resource generation.

Handles PPTX, Code ZIP, and Interactive resource generation tasks.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

import structlog
from pptx import Presentation
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.datetime import utc_now
from app.models.task import BackgroundTask
from app.models.unit import LearningResource
from app.services.code_generator import CodeZIPGenerator
from app.services.interactive_generator import InteractiveGenerator
from app.services.narrated_video import generate_narrated_video
from app.services.pptx_generator import PPTXGenerator
from app.services.resource_quality import evaluate_resource_quality
from app.services.resources import ResourceService
from app.services.storage import ObjectStorage, get_object_storage
from app.workers.task_runtime import record_agent_step

logger = structlog.get_logger()


async def execute_resource_generation(
    db: AsyncSession,
    task: BackgroundTask,
) -> dict[str, Any]:
    """Execute multimodal resource generation.

    Supported resource types:
    - pptx: PowerPoint presentation (deterministic from unit content)
    - code_zip: Code project ZIP archive (with security checks)
    - interactive_cards: AI-grounded active-recall cards
    - walkthrough: AI-grounded continuous case study
    - narrated_video: SiliconFlow TTS + deterministic slides + captions

    Args:
        db: Database session
        task: Background task with metadata:
            - path_id: Learning path ID
            - resource_id: Learning resource ID
            - resource_type: Type of resource to generate

    Returns:
        Dict with generation result
    """
    metadata = task.target_metadata or {}
    path_id = metadata.get("path_id")
    resource_id = metadata.get("resource_id")
    resource_type = metadata.get("resource_type")
    user_id = task.user_id

    if not isinstance(path_id, str) or not path_id:
        raise ValueError("Missing required metadata: path_id")
    if not isinstance(resource_id, str) or not resource_id:
        raise ValueError("Missing required metadata: resource_id")
    if not isinstance(resource_type, str) or not resource_type:
        raise ValueError("Missing required metadata: resource_type")
    if not user_id:
        raise ValueError("Missing required task user_id")

    resource_service = ResourceService(db)
    storage = get_object_storage()

    # Get node_id from resource
    result = await db.execute(select(LearningResource).where(LearningResource.id == resource_id))
    resource = result.scalar_one_or_none()
    if not resource:
        raise ValueError(f"Resource not found: {resource_id}")
    node_id = resource.node_id

    # Get unit content for generation
    unit_content = await resource_service.get_unit_content_for_node(path_id, node_id, user_id)
    if not unit_content:
        error_msg = f"Unit content not found for node {node_id}"
        await resource_service.update_resource_failed(resource_id, "UNIT_CONTENT_NOT_FOUND", error_msg)
        raise ValueError(error_msg)

    labels = {
        "pptx": "PPT 课件生成智能体",
        "code_zip": "代码项目生成智能体",
        "interactive_cards": "学习卡片生成智能体",
        "walkthrough": "案例推演生成智能体",
        "narrated_video": "语音课件视频生成智能体",
    }
    record_agent_step(
        task,
        agent_key="resource_context",
        label="资源上下文分析器",
        status="completed",
        summary="已读取个性化课程内容、学习目标和实践任务。",
        artifact_type="资源生成上下文",
    )
    record_agent_step(
        task,
        agent_key=f"resource_{resource_type}",
        label=labels.get(resource_type, "多模态资源生成智能体"),
        status="running",
        summary=f"正在把课程内容转换为 {resource_type} 学习资源。",
        artifact_type=resource_type,
    )

    try:
        # Route to appropriate generator based on resource_type
        if resource_type == "pptx":
            result_data = await _generate_pptx(resource_id, node_id, user_id, unit_content, storage, resource_service)
        elif resource_type == "code_zip":
            result_data = await _generate_code_zip(
                resource_id, node_id, user_id, unit_content, storage, resource_service
            )
        elif resource_type == "interactive_cards":
            result_data = await _generate_interactive_cards(
                resource_id, node_id, user_id, unit_content, resource_service
            )
        elif resource_type == "walkthrough":
            result_data = await _generate_walkthrough(resource_id, node_id, user_id, unit_content, resource_service)
        elif resource_type == "narrated_video":
            result_data = await _generate_narrated_video(
                resource_id,
                node_id,
                user_id,
                unit_content,
                storage,
                resource_service,
            )
        else:
            error_msg = f"Unsupported resource type: {resource_type}"
            await resource_service.update_resource_failed(resource_id, "UNSUPPORTED_TYPE", error_msg)
            raise ValueError(error_msg)

        logger.info(
            "resource_generation_completed",
            resource_id=resource_id,
            resource_type=resource_type,
            node_id=node_id,
        )
        record_agent_step(
            task,
            agent_key=f"resource_{resource_type}",
            label=labels.get(resource_type, "多模态资源生成智能体"),
            status="completed",
            summary=f"{resource_type} 资源已生成并通过格式检查。",
            artifact_type=resource_type,
        )
        quality = result_data.get("quality", {})
        quality_score = quality.get("score", 0)
        quality_passed = quality.get("passed", False)
        record_agent_step(
            task,
            agent_key="resource_quality_reviewer",
            label="资源质量审查智能体",
            status="completed" if quality_passed else "needs_revision",
            summary=(
                f"资源质量评分 {quality_score}/100，"
                f"{'已达到交付门槛' if quality_passed else '建议人工复核或重新生成'}。"
            ),
            artifact_type="资源质量报告",
        )
        return result_data

    except Exception as e:
        error_msg = f"Resource generation failed: {str(e)}"
        logger.error(
            "resource_generation_failed",
            resource_id=resource_id,
            resource_type=resource_type,
            error=str(e),
        )
        await resource_service.update_resource_failed(resource_id, "GENERATION_ERROR", error_msg)
        raise


async def _generate_pptx(
    resource_id: str,
    node_id: str,
    user_id: str,
    unit_content: dict[str, Any],
    storage: ObjectStorage,
    resource_service: ResourceService,
) -> dict[str, Any]:
    """Generate PPTX and upload to storage."""
    pptx_bytes = PPTXGenerator.generate_pptx_bytes(unit_content)
    if not pptx_bytes:
        raise RuntimeError("PPTX generation returned empty bytes")

    # Upload to storage
    storage_key = f"resources/{user_id}/{node_id}/presentation.pptx"
    await storage.put(
        storage_key,
        pptx_bytes,
        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )

    # Count slides
    try:
        prs = Presentation(BytesIO(pptx_bytes))
        slide_count = len(prs.slides)
    except Exception:
        slide_count = 0

    content_metadata = {
        "slide_count": slide_count,
        "title": unit_content.get("introduction", "").split("\n")[0][:100],
        "generated_at": utc_now().isoformat(),
    }
    content_metadata["quality"] = evaluate_resource_quality("pptx", unit_content, content_metadata)

    await resource_service.update_resource_ready(
        resource_id,
        content=content_metadata,
        storage_key=storage_key,
        storage_provider="minio",
    )

    return {
        "resource_id": resource_id,
        "storage_key": storage_key,
        "slide_count": slide_count,
        "quality": content_metadata["quality"],
    }


async def _generate_code_zip(
    resource_id: str,
    node_id: str,
    user_id: str,
    unit_content: dict[str, Any],
    storage: ObjectStorage,
    resource_service: ResourceService,
) -> dict[str, Any]:
    """Generate code ZIP and upload to storage."""
    zip_bytes, file_list = CodeZIPGenerator.generate_zip_bytes(unit_content)
    if not zip_bytes:
        raise RuntimeError("Code ZIP generation returned empty bytes")

    # Upload to storage
    storage_key = f"resources/{user_id}/{node_id}/code-project.zip"
    await storage.put(storage_key, zip_bytes, content_type="application/zip")

    content_metadata = {
        "file_count": len(file_list),
        "files": file_list,
        "title": unit_content.get("introduction", "").split("\n")[0][:100],
    }
    content_metadata["quality"] = evaluate_resource_quality("code_zip", unit_content, content_metadata)

    await resource_service.update_resource_ready(
        resource_id,
        content=content_metadata,
        storage_key=storage_key,
        storage_provider="minio",
    )

    return {
        "resource_id": resource_id,
        "storage_key": storage_key,
        "file_count": len(file_list),
        "quality": content_metadata["quality"],
    }


async def _generate_interactive_cards(
    resource_id: str,
    node_id: str,
    user_id: str,
    unit_content: dict[str, Any],
    resource_service: ResourceService,
) -> dict[str, Any]:
    """Generate interactive cards (stored as JSON, no file upload)."""
    cards_data = await InteractiveGenerator.generate_cards_ai(unit_content)

    content_metadata = {
        "title": cards_data["title"],
        "interactive_type": "cards",
        "description": cards_data["description"],
        "items": cards_data["items"],
        "knowledge_points": cards_data["knowledge_points"],
        "estimated_minutes": cards_data["estimated_minutes"],
        "card_count": len(cards_data["items"]),
        "generation_method": cards_data["generation_method"],
    }
    content_metadata["quality"] = evaluate_resource_quality("interactive_cards", unit_content, content_metadata)

    await resource_service.update_resource_ready(resource_id, content=content_metadata)

    return {
        "resource_id": resource_id,
        "card_count": len(cards_data["items"]),
        "quality": content_metadata["quality"],
    }


async def _generate_walkthrough(
    resource_id: str,
    node_id: str,
    user_id: str,
    unit_content: dict[str, Any],
    resource_service: ResourceService,
) -> dict[str, Any]:
    """Generate walkthrough (step-by-step case study)."""
    walkthrough_data = await InteractiveGenerator.generate_walkthrough_ai(unit_content)

    content_metadata = {
        "title": walkthrough_data["title"],
        "interactive_type": "walkthrough",
        "description": walkthrough_data["description"],
        "items": walkthrough_data["items"],
        "step_count": len(walkthrough_data["items"]),
        "generation_method": walkthrough_data["generation_method"],
    }
    content_metadata["quality"] = evaluate_resource_quality("walkthrough", unit_content, content_metadata)

    await resource_service.update_resource_ready(resource_id, content=content_metadata)

    return {
        "resource_id": resource_id,
        "step_count": len(walkthrough_data["items"]),
        "quality": content_metadata["quality"],
    }


async def _generate_narrated_video(
    resource_id: str,
    node_id: str,
    user_id: str,
    unit_content: dict[str, Any],
    storage: ObjectStorage,
    resource_service: ResourceService,
) -> dict[str, Any]:
    """Generate one narrated MP4 using a single SiliconFlow TTS request."""
    video = await generate_narrated_video(unit_content)
    base_key = f"resources/{user_id}/{node_id}/narrated-video"
    video_key = f"{base_key}/course.mp4"
    audio_key = f"{base_key}/narration.mp3"
    captions_key = f"{base_key}/captions.vtt"

    await storage.put(video_key, video.video, content_type="video/mp4")
    await storage.put(audio_key, video.tts.audio, content_type=video.tts.content_type)
    await storage.put(
        captions_key,
        video.captions_vtt.encode("utf-8"),
        content_type="text/vtt; charset=utf-8",
    )

    content_metadata: dict[str, Any] = {
        "title": f"{video.manifest['title']} — 语音讲解视频",
        "description": "课件画面、语音和同步字幕合成的个性化微课。",
        "duration_seconds": video.duration_seconds,
        "slide_count": len(video.manifest["slides"]),
        "resolution": video.manifest["resolution"],
        "captions_vtt": video.captions_vtt,
        "captions_storage_key": captions_key,
        "audio_storage_key": audio_key,
        "tts_model": video.tts.model,
        "tts_voice": video.tts.voice,
        "tts_trace_id": video.tts.trace_id,
        "manifest": video.manifest,
        "generated_at": utc_now().isoformat(),
    }
    content_metadata["quality"] = evaluate_resource_quality("narrated_video", unit_content, content_metadata)
    await resource_service.update_resource_ready(
        resource_id,
        content=content_metadata,
        storage_key=video_key,
        storage_provider="minio",
    )
    return {
        "resource_id": resource_id,
        "storage_key": video_key,
        "duration_seconds": video.duration_seconds,
        "slide_count": len(video.manifest["slides"]),
        "quality": content_metadata["quality"],
    }
