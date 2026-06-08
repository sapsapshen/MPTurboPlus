import os
import random
import threading
from typing import List
from urllib.parse import urlencode

import requests
from loguru import logger
from moviepy.video.io.VideoFileClip import VideoFileClip

from app.config import config
from app.models.schema import MaterialInfo, VideoAspect, VideoConcatMode
from app.services import llm as llm_service
from app.utils import utils

# Thread-safe counter for API key rotation
_api_key_counter = 0
_api_key_lock = threading.Lock()


def _get_tls_verify() -> bool:
    # 默认开启 TLS 证书校验，防止素材搜索和下载过程被中间人篡改。
    # 仅在企业代理、自签证书等明确需要的场景下，允许用户通过
    # `config.toml` 显式设置 `tls_verify = false` 临时关闭。
    tls_verify = config.app.get("tls_verify", True)
    if isinstance(tls_verify, str):
        tls_verify = tls_verify.strip().lower() not in ("0", "false", "no", "off")

    if not tls_verify:
        logger.warning(
            "TLS certificate verification is disabled by config.app.tls_verify=false. "
            "Only use this in trusted proxy environments."
        )

    return bool(tls_verify)


def get_api_key(cfg_key: str):
    api_keys = config.app.get(cfg_key)
    if not api_keys:
        raise ValueError(
            f"\n\n##### {cfg_key} is not set #####\n\nPlease set it in the config.toml file: {config.config_file}\n\n"
            f"{utils.to_json(config.app)}"
        )

    # if only one key is provided, return it
    if isinstance(api_keys, str):
        return api_keys

    global _api_key_counter
    with _api_key_lock:
        _api_key_counter += 1
        return api_keys[_api_key_counter % len(api_keys)]


def search_videos_pexels(
    search_term: str,
    minimum_duration: int,
    video_aspect: VideoAspect = VideoAspect.portrait,
) -> List[MaterialInfo]:
    aspect = VideoAspect(video_aspect)
    video_orientation = aspect.name
    video_width, video_height = aspect.to_resolution()
    api_key = get_api_key("pexels_api_keys")
    headers = {
        "Authorization": api_key,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    }
    # Build URL
    params = {"query": search_term, "per_page": 20, "orientation": video_orientation}
    query_url = f"https://api.pexels.com/videos/search?{urlencode(params)}"
    logger.info(f"searching videos: {query_url}, with proxies: {config.proxy}")

    try:
        r = requests.get(
            query_url,
            headers=headers,
            proxies=config.proxy,
            verify=_get_tls_verify(),
            timeout=(30, 60),
        )
        response = r.json()
        video_items = []
        if "videos" not in response:
            logger.error(f"search videos failed: {response}")
            return video_items
        videos = response["videos"]
        # loop through each video in the result
        for v in videos:
            duration = v["duration"]
            # check if video has desired minimum duration
            if duration < minimum_duration:
                continue
            video_files = v["video_files"]
            # loop through each url to determine the best quality
            for video in video_files:
                w = int(video["width"])
                h = int(video["height"])
                if w == video_width and h == video_height:
                    item = MaterialInfo()
                    item.provider = "pexels"
                    item.url = video["link"]
                    item.duration = duration
                    video_items.append(item)
                    break
        return video_items
    except Exception as e:
        logger.error(f"search videos failed: {str(e)}")

    return []


def search_videos_pixabay(
    search_term: str,
    minimum_duration: int,
    video_aspect: VideoAspect = VideoAspect.portrait,
) -> List[MaterialInfo]:
    aspect = VideoAspect(video_aspect)

    video_width, video_height = aspect.to_resolution()

    api_key = get_api_key("pixabay_api_keys")
    # Build URL
    params = {
        "q": search_term,
        "video_type": "all",  # Accepted values: "all", "film", "animation"
        "per_page": 50,
        "key": api_key,
    }
    query_url = f"https://pixabay.com/api/videos/?{urlencode(params)}"
    logger.info(f"searching videos: {query_url}, with proxies: {config.proxy}")

    try:
        r = requests.get(
            query_url, proxies=config.proxy, verify=_get_tls_verify(), timeout=(30, 60)
        )
        response = r.json()
        video_items = []
        if "hits" not in response:
            logger.error(f"search videos failed: {response}")
            return video_items
        videos = response["hits"]
        # loop through each video in the result
        for v in videos:
            duration = v["duration"]
            # check if video has desired minimum duration
            if duration < minimum_duration:
                continue
            video_files = v["videos"]
            # loop through each url to determine the best quality
            for video_type in video_files:
                video = video_files[video_type]
                w = int(video["width"])
                # h = int(video["height"])
                if w >= video_width:
                    item = MaterialInfo()
                    item.provider = "pixabay"
                    item.url = video["url"]
                    item.duration = duration
                    video_items.append(item)
                    break
        return video_items
    except Exception as e:
        logger.error(f"search videos failed: {str(e)}")

    return []


def save_video(video_url: str, save_dir: str = "") -> str:
    if not save_dir:
        save_dir = utils.storage_dir("cache_videos")

    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    url_without_query = video_url.split("?")[0]
    url_hash = utils.md5(url_without_query)
    video_id = f"vid-{url_hash}"
    video_path = f"{save_dir}/{video_id}.mp4"

    # if video already exists, return the path
    if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
        logger.info(f"video already exists: {video_path}")
        return video_path

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }

    # if video does not exist, download it
    with open(video_path, "wb") as f:
        f.write(
            requests.get(
                video_url,
                headers=headers,
                proxies=config.proxy,
                verify=_get_tls_verify(),
                timeout=(60, 240),
            ).content
        )

    if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
        clip = None
        try:
            clip = VideoFileClip(video_path)
            duration = clip.duration
            fps = clip.fps
            if duration > 0 and fps > 0:
                return video_path
        except Exception as e:
            logger.warning(f"invalid video file: {video_path} => {str(e)}")
            try:
                os.remove(video_path)
            except Exception as remove_error:
                logger.warning(
                    f"failed to remove invalid video file: {video_path}, error: {str(remove_error)}"
                )
        finally:
            if clip is not None:
                try:
                    clip.close()
                except Exception as close_error:
                    logger.warning(
                        f"failed to close video clip: {video_path}, error: {str(close_error)}"
                    )
    return ""


def download_videos(
    task_id: str,
    search_terms: List[str],
    source: str = "pexels",
    video_aspect: VideoAspect = VideoAspect.portrait,
    video_contact_mode: VideoConcatMode = VideoConcatMode.random,
    audio_duration: float = 0.0,
    max_clip_duration: int = 5,
) -> List[str]:
    valid_video_items = []
    valid_video_urls = []
    found_duration = 0.0
    search_videos = search_videos_pexels
    if source == "pixabay":
        search_videos = search_videos_pixabay

    for search_term in search_terms:
        video_items = search_videos(
            search_term=search_term,
            minimum_duration=max_clip_duration,
            video_aspect=video_aspect,
        )
        logger.info(f"found {len(video_items)} videos for '{search_term}'")

        for item in video_items:
            if item.url not in valid_video_urls:
                valid_video_items.append(item)
                valid_video_urls.append(item.url)
                found_duration += item.duration

    logger.info(
        f"found total videos: {len(valid_video_items)}, required duration: {audio_duration} seconds, found duration: {found_duration} seconds"
    )
    video_paths = []

    material_directory = config.app.get("material_directory", "").strip()
    if material_directory == "task":
        material_directory = utils.task_dir(task_id)
    elif material_directory and not os.path.isdir(material_directory):
        material_directory = ""

    concat_mode_value = getattr(video_contact_mode, "value", video_contact_mode)
    if concat_mode_value == VideoConcatMode.random.value:
        random.shuffle(valid_video_items)

    total_duration = 0.0
    for item in valid_video_items:
        try:
            logger.info(f"downloading video: {item.url}")
            saved_video_path = save_video(
                video_url=item.url, save_dir=material_directory
            )
            if saved_video_path:
                logger.info(f"video saved: {saved_video_path}")
                video_paths.append(saved_video_path)
                seconds = min(max_clip_duration, item.duration)
                total_duration += seconds
                if total_duration > audio_duration:
                    logger.info(
                        f"total duration of downloaded videos: {total_duration} seconds, skip downloading more"
                    )
                    break
        except Exception as e:
            logger.error(f"failed to download video: {utils.to_json(item)} => {str(e)}")
    logger.success(f"downloaded {len(video_paths)} videos")
    return video_paths


def download_videos_scene_aligned(
    task_id: str,
    search_terms_by_paragraph: List[List[str]],
    source: str = "pexels",
    video_aspect: VideoAspect = VideoAspect.portrait,
    video_contact_mode: VideoConcatMode = VideoConcatMode.random,
    audio_duration: float = 0.0,
    max_clip_duration: int = 5,
    paragraphs: List[str] = None,
) -> List[List[str]]:
    """
    逐段落下载视频素材，追踪每个段落与其素材的映射关系。

    与 download_videos() 的关键区别：
    - 输入是 List[List[str]]（每段落一组搜索词）
    - 输出是 List[List[str]]（每段落对应一组下载的素材路径）
    - 段落间的素材不会混用
    - 某段落搜索无结果时，会 fallback 到相邻段落的素材
    - 每段下载后自动审核搜索词匹配度，低分时自动重生成+重新下载

    Args:
        task_id: 任务 ID
        search_terms_by_paragraph: 逐段落的搜索词列表
        source: 素材来源 ("pexels" | "pixabay")
        video_aspect: 视频宽高比
        video_contact_mode: 拼接模式
        audio_duration: 总音频时长 (秒)
        max_clip_duration: 单个素材片段最大时长 (秒)

    Returns:
        List[List[str]]: 每个段落对应的素材路径列表
    """
    if not search_terms_by_paragraph:
        return []

    num_paragraphs = len(search_terms_by_paragraph)
    # 按段落数平均分配音频时长
    audio_per_paragraph = audio_duration / num_paragraphs if num_paragraphs > 0 else 0

    search_videos = search_videos_pexels
    if source == "pixabay":
        search_videos = search_videos_pixabay

    material_directory = config.app.get("material_directory", "").strip()
    if material_directory == "task":
        material_directory = utils.task_dir(task_id)
    elif material_directory and not os.path.isdir(material_directory):
        material_directory = ""

    concat_mode_value = getattr(video_contact_mode, "value", video_contact_mode)

    scene_video_paths: List[List[str]] = []

    for para_idx, search_terms in enumerate(search_terms_by_paragraph):
        logger.info(
            f"downloading videos for paragraph {para_idx + 1}/{num_paragraphs}: "
            f"terms={search_terms}"
        )

        para_video_paths: List[str] = []
        para_duration = 0.0
        target_duration = audio_per_paragraph * 1.2  # 多搜 20% 做缓冲

        # 为该段落的每个搜索词下载素材
        valid_items: List[MaterialInfo] = []
        seen_urls: set = set()

        for search_term in search_terms:
            video_items = search_videos(
                search_term=search_term,
                minimum_duration=max_clip_duration,
                video_aspect=video_aspect,
            )
            logger.info(
                f"paragraph {para_idx + 1} term '{search_term}': "
                f"found {len(video_items)} videos"
            )
            for item in video_items:
                if item.url not in seen_urls:
                    seen_urls.add(item.url)
                    valid_items.append(item)

        if concat_mode_value == VideoConcatMode.random.value:
            random.shuffle(valid_items)

        for item in valid_items:
            try:
                saved_video_path = save_video(
                    video_url=item.url, save_dir=material_directory
                )
                if saved_video_path:
                    para_video_paths.append(saved_video_path)
                    seconds = min(max_clip_duration, item.duration)
                    para_duration += seconds
                    if para_duration >= target_duration:
                        break
            except Exception as e:
                logger.error(
                    f"paragraph {para_idx + 1} download failed: "
                    f"{utils.to_json(item)} => {str(e)}"
                )

        # ---- 搜索词匹配度审核与重生 ----
        # 获取该段落对应的原文，用于 LLM 评估搜索词匹配度
        para_text = ""
        if paragraphs and para_idx < len(paragraphs):
            para_text = (paragraphs[para_idx] or "").strip()

        current_terms = list(search_terms)
        current_paths = list(para_video_paths)
        best_paths = list(para_video_paths)
        best_terms = list(search_terms)

        for regen_round in range(llm_service.MAX_SCENE_REGENERATION_RETRIES + 1):
            # 第一次是初始审核；后续是重生后审核
            if not current_terms or not current_paths:
                break  # 无词或无素材，跳过审核

            relevance = llm_service.evaluate_terms_relevance(
                paragraph=para_text,
                search_terms=current_terms,
            )

            if relevance >= llm_service.MIN_TERM_RELEVANCE_SCORE:
                logger.info(
                    f"paragraph {para_idx + 1}: terms relevance {relevance}/10 "
                    f">= {llm_service.MIN_TERM_RELEVANCE_SCORE}, accepted"
                )
                if current_paths != best_paths and len(current_paths) >= len(best_paths):
                    best_paths = list(current_paths)
                    best_terms = list(current_terms)
                break

            logger.warning(
                f"paragraph {para_idx + 1}: terms relevance {relevance}/10 "
                f"< {llm_service.MIN_TERM_RELEVANCE_SCORE}, "
                f"regeneration round {regen_round + 1}/{llm_service.MAX_SCENE_REGENERATION_RETRIES}"
            )

            if regen_round >= llm_service.MAX_SCENE_REGENERATION_RETRIES:
                logger.warning(
                    f"paragraph {para_idx + 1}: max regeneration reached, "
                    f"keeping best result ({len(best_paths)} videos)"
                )
                break

            # 重新生成搜索词
            refined_terms = llm_service.refine_search_terms(
                paragraph=para_text,
                video_subject=getattr(
                    search_terms_by_paragraph, "_video_subject", ""
                ) or "",
                previous_terms=current_terms,
                score=relevance,
            )

            if not refined_terms:
                logger.warning(
                    f"paragraph {para_idx + 1}: refine returned empty, "
                    f"keeping current result"
                )
                break

            logger.info(
                f"paragraph {para_idx + 1}: refined terms: {refined_terms}"
            )

            # 用新搜索词重新搜索并下载
            refined_items: List[MaterialInfo] = []
            refined_seen: set = set()
            for rt in refined_terms:
                video_items = search_videos(
                    search_term=rt,
                    minimum_duration=max_clip_duration,
                    video_aspect=video_aspect,
                )
                logger.info(
                    f"paragraph {para_idx + 1} refined term '{rt}': "
                    f"found {len(video_items)} videos"
                )
                for item in video_items:
                    if item.url not in refined_seen:
                        refined_seen.add(item.url)
                        refined_items.append(item)

            if concat_mode_value == VideoConcatMode.random.value:
                random.shuffle(refined_items)

            refined_paths: List[str] = []
            refined_dur = 0.0
            for item in refined_items:
                try:
                    saved = save_video(
                        video_url=item.url, save_dir=material_directory
                    )
                    if saved:
                        refined_paths.append(saved)
                        refined_dur += min(max_clip_duration, item.duration)
                        if refined_dur >= target_duration:
                            break
                except Exception as e:
                    logger.error(
                        f"paragraph {para_idx + 1} refined download failed: "
                        f"{str(e)}"
                    )

            if refined_paths:
                current_terms = list(refined_terms)
                current_paths = list(refined_paths)
                if len(refined_paths) >= len(best_paths):
                    best_paths = list(refined_paths)
                    best_terms = list(refined_terms)
                logger.info(
                    f"paragraph {para_idx + 1}: regeneration round "
                    f"{regen_round + 1} downloaded {len(refined_paths)} videos"
                )
            else:
                logger.warning(
                    f"paragraph {para_idx + 1}: refined terms found no videos, "
                    f"keeping current result"
                )
                break

        scene_video_paths.append(best_paths)
        logger.info(
            f"paragraph {para_idx + 1}: final {len(best_paths)} videos, "
            f"terms={best_terms}"
        )

    # Fallback: 对于完全没有素材的段落，复用相邻段落的素材
    for para_idx in range(num_paragraphs):
        if not scene_video_paths[para_idx]:
            # 优先用下一段
            borrowed = False
            for offset in range(1, num_paragraphs):
                next_idx = para_idx + offset
                prev_idx = para_idx - offset
                if next_idx < num_paragraphs and scene_video_paths[next_idx]:
                    scene_video_paths[para_idx] = list(
                        scene_video_paths[next_idx]
                    )
                    logger.warning(
                        f"paragraph {para_idx + 1}: fallback to paragraph "
                        f"{next_idx + 1} videos"
                    )
                    borrowed = True
                    break
                if prev_idx >= 0 and scene_video_paths[prev_idx]:
                    scene_video_paths[para_idx] = list(
                        scene_video_paths[prev_idx]
                    )
                    logger.warning(
                        f"paragraph {para_idx + 1}: fallback to paragraph "
                        f"{prev_idx + 1} videos"
                    )
                    borrowed = True
                    break
            if not borrowed:
                logger.warning(
                    f"paragraph {para_idx + 1}: no videos and no fallback available"
                )

    total_videos = sum(len(v) for v in scene_video_paths)
    logger.success(
        f"scene-aligned download complete: {total_videos} videos "
        f"across {num_paragraphs} paragraphs"
    )
    return scene_video_paths


if __name__ == "__main__":
    download_videos(
        "test123", ["Money Exchange Medium"], audio_duration=100, source="pixabay"
    )
