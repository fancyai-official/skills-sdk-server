"""
批量处理工具模块

提供并发批量提交、轮询、下载上传的功能。
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Callable


def batch_step1_submit_tasks(
    submit_func: Callable,
    tasks: List[Dict],
    max_workers: int = 3
) -> List[Dict]:
    """
    批量并行提交多个生图任务。

    每个任务独立提交，通过内部线程池实现并行，返回结果顺序与输入一致。
    适合同时生成 N 张图的场景（如 9 张 Campaign 图片）。

    Args:
        submit_func: 单任务提交函数（step1_submit_task）
        tasks: 任务列表，每项为包含以下字段的字典：
            task_name  (str,  可选): 任务标识名，默认 "task_{i}"
            img_urls   (list, 可选): 参考图片 URL 列表，文本生图时传 None 或省略
            prompt     (str):        生图提示词
            ratio      (str,  可选): 宽高比，默认 "1:1"
            resolution (str,  可选): 分辨率 1K/2K/4K，默认 "2K"
            provider   (str,  可选): "tencent"|"dmxapi"|"auto"，默认 "auto"
        max_workers (int): 最大并行线程数，默认 3

    Returns:
        结果列表（与 tasks 等长且顺序一致），每项包含：
            task_name (str):      任务名称
            task_id   (str|None): 提交成功的任务 ID，失败为 None
            status    (str):      "ok" | "failed"

    输出标记（供外层解析）:
        [BATCH_SUBMIT]      N tasks, M workers
        [PROGRESS]          i/N — task_name: OK/FAILED
        [BATCH_SUBMIT_DONE] ok=M/N in Xs
    """
    total = len(tasks)
    results: List[Dict] = [None] * total
    completed_count = [0]

    def _submit_one(idx: int, task: Dict):
        task_name = task.get("task_name") or f"task_{idx}"
        try:
            task_id = submit_func(
                img_urls=task.get("img_urls"),
                prompt=task.get("prompt", ""),
                ratio=task.get("ratio", "1:1"),
                resolution=task.get("resolution", "2K"),
                provider=task.get("provider", "auto"),
            )
            completed_count[0] += 1
            status = "ok" if task_id else "failed"
            print(f"[PROGRESS] {completed_count[0]}/{total} — {task_name}: {status.upper()}")
            return idx, {"task_name": task_name, "task_id": task_id, "status": status}
        except Exception as e:
            completed_count[0] += 1
            print(f"[PROGRESS] {completed_count[0]}/{total} — {task_name}: FAILED ({e})")
            return idx, {"task_name": task_name, "task_id": None, "status": "failed"}

    print(f"[BATCH_SUBMIT] {total} tasks, {max_workers} workers")
    start = time.time()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_submit_one, i, task): i for i, task in enumerate(tasks)}
        for future in as_completed(futures):
            idx, result = future.result()
            results[idx] = result

    elapsed = time.time() - start
    ok_count = sum(1 for r in results if r and r["status"] == "ok")
    print(f"[BATCH_SUBMIT_DONE] ok={ok_count}/{total} in {elapsed:.1f}s")
    return results


def batch_step2_poll_tasks(
    poll_func: Callable,
    task_infos: List[Dict],
    max_poll_time: int = 50,
    max_workers: int = 9
) -> List[Dict]:
    """
    批量并行轮询多个任务状态。

    所有有效任务同时开始轮询，共享 max_poll_time 超时窗口。
    task_id 为 None 的条目直接跳过并标记 "skipped"，不占用线程。

    Args:
        poll_func: 单任务轮询函数（step2_poll_task）
        task_infos:     任务信息列表，每项包含：
            task_name (str):      任务名称
            task_id   (str|None): 任务 ID，None 时跳过
        max_poll_time:  每个任务本次最大轮询时间（秒），默认 50
                        超时未完成则返回 "PENDING"，需再次调用本函数
        max_workers:    最大并行线程数，默认 9

    Returns:
        结果列表（与 task_infos 等长且顺序一致），每项包含：
            task_name (str):      任务名称
            task_id   (str|None): 原始任务 ID
            file_url  (str|None): 图片 URL（完成）| "PENDING"（超时）| None（失败/跳过）
            status    (str):      "ready" | "pending" | "failed" | "skipped"

    输出标记:
        [BATCH_POLL]      valid/total tasks, M workers
        [READY]           task_name
        [PENDING]         task_name
        [FAILED]          task_name
        [BATCH_POLL_DONE] ready=R pending=P failed=F skipped=S in Xs
    """
    total = len(task_infos)
    results: List[Dict] = [None] * total

    def _poll_one(idx: int, info: Dict):
        task_name = info.get("task_name") or f"task_{idx}"
        task_id = info.get("task_id")
        if not task_id:
            return idx, {"task_name": task_name, "task_id": None,
                         "file_url": None, "status": "skipped"}
        try:
            file_url = poll_func(task_id, max_poll_time=max_poll_time, provider="auto")
            if file_url and file_url != "PENDING":
                print(f"[READY] {task_name}")
                return idx, {"task_name": task_name, "task_id": task_id,
                             "file_url": file_url, "status": "ready"}
            elif file_url == "PENDING":
                print(f"[PENDING] {task_name}")
                return idx, {"task_name": task_name, "task_id": task_id,
                             "file_url": "PENDING", "status": "pending"}
            else:
                print(f"[FAILED] {task_name}")
                return idx, {"task_name": task_name, "task_id": task_id,
                             "file_url": None, "status": "failed"}
        except Exception as e:
            print(f"[FAILED] {task_name}: {e}")
            return idx, {"task_name": task_name, "task_id": task_id,
                         "file_url": None, "status": "failed"}

    valid_count = sum(1 for info in task_infos if info.get("task_id"))
    print(f"[BATCH_POLL] {valid_count}/{total} tasks, {max_workers} workers, max {max_poll_time}s each")
    start = time.time()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_poll_one, i, info): i for i, info in enumerate(task_infos)}
        for future in as_completed(futures):
            idx, result = future.result()
            results[idx] = result

    elapsed = time.time() - start
    ready   = sum(1 for r in results if r and r["status"] == "ready")
    pending = sum(1 for r in results if r and r["status"] == "pending")
    failed  = sum(1 for r in results if r and r["status"] == "failed")
    skipped = sum(1 for r in results if r and r["status"] == "skipped")
    print(f"[BATCH_POLL_DONE] ready={ready} pending={pending} failed={failed} skipped={skipped} in {elapsed:.1f}s")
    return results


def batch_step3_download_and_upload(
    download_func: Callable,
    file_infos: List[Dict],
    max_workers: int = 3
) -> List[Dict]:
    """
    批量并行下载图片并上传到 R2 CDN。

    file_url 为 None 或 "PENDING" 的条目自动跳过，不占用线程。

    Args:
        download_func: 单任务下载上传函数（step3_download_and_upload）
        file_infos:  文件信息列表，每项包含：
            task_name (str):      任务名称
            file_url  (str|None): 图片 URL，None 或 "PENDING" 时跳过
        max_workers: 最大并行线程数，默认 3

    Returns:
        结果列表（与 file_infos 等长且顺序一致），每项包含：
            task_name (str):      任务名称
            file_url  (str|None): 原始图片 URL
            image_url (str|None): R2 CDN URL（成功）| None（失败/跳过）
            status    (str):      "ok" | "failed" | "skipped"

    输出标记:
        [BATCH_DOWNLOAD]      valid/total images, M workers
        [PROGRESS]            i/valid — task_name: OK/FAILED
        [BATCH_DOWNLOAD_DONE] ok=M/valid in Xs
    """
    total = len(file_infos)
    results: List[Dict] = [None] * total
    valid_pairs = [
        (i, info) for i, info in enumerate(file_infos)
        if info.get("file_url") and info.get("file_url") != "PENDING"
    ]
    valid_count = len(valid_pairs)
    completed_count = [0]

    # 预填跳过条目，避免结果列表中出现 None
    for i, info in enumerate(file_infos):
        if not info.get("file_url") or info.get("file_url") == "PENDING":
            results[i] = {
                "task_name": info.get("task_name") or f"task_{i}",
                "file_url": info.get("file_url"),
                "image_url": None,
                "status": "skipped",
            }

    def _download_one(idx: int, info: Dict):
        task_name = info.get("task_name") or f"task_{idx}"
        file_url = info.get("file_url")
        try:
            image_url = download_func(file_url, provider="auto")
            completed_count[0] += 1
            status = "ok" if image_url else "failed"
            print(f"[PROGRESS] {completed_count[0]}/{valid_count} — {task_name}: {status.upper()}")
            return idx, {"task_name": task_name, "file_url": file_url,
                         "image_url": image_url, "status": status}
        except Exception as e:
            completed_count[0] += 1
            print(f"[PROGRESS] {completed_count[0]}/{valid_count} — {task_name}: FAILED ({e})")
            return idx, {"task_name": task_name, "file_url": file_url,
                         "image_url": None, "status": "failed"}

    print(f"[BATCH_DOWNLOAD] {valid_count}/{total} images, {max_workers} workers")
    start = time.time()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_download_one, i, info): i for i, info in valid_pairs}
        for future in as_completed(futures):
            idx, result = future.result()
            results[idx] = result

    elapsed = time.time() - start
    ok_count = sum(1 for r in results if r and r["status"] == "ok")
    print(f"[BATCH_DOWNLOAD_DONE] ok={ok_count}/{valid_count} in {elapsed:.1f}s")
    return results
