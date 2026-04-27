"""
cron-job.org 자동 등록 스크립트

트렌드 스캐너용 GitHub Actions workflow_dispatch를 호출하는
2개 cron 작업(KST 07:30, 20:00 매일)을 cron-job.org에 등록한다.

Usage:
    python scripts/register_cron.py            # 등록 (이미 있으면 skip)
    python scripts/register_cron.py --list     # 기존 작업 조회만
    python scripts/register_cron.py --force    # 기존 작업 삭제 후 재등록
    python scripts/register_cron.py --delete   # 기존 트렌드 스캐너 작업 삭제

Requires in .env:
    CRONJOB_API_KEY = cron-job.org API 키 (https://console.cron-job.org/settings)
    GITHUB_PAT      = GitHub Personal Access Token (Actions: Read and write 권한)
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import List, Optional

import requests
from dotenv import load_dotenv

# .env 로드
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

CRONJOB_API_BASE = "https://api.cron-job.org"
GITHUB_REPO = "xxonbang/stock_alarm_bot"
WORKFLOW_FILE = "trend_scan.yml"
GITHUB_DISPATCH_URL = (
    f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{WORKFLOW_FILE}/dispatches"
)

JOBS = [
    {"title": "Trend Scanner - Morning (07:30 KST)", "hour": 7, "minute": 30},
    {"title": "Trend Scanner - Evening (20:00 KST)", "hour": 20, "minute": 0},
]


def _api_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def list_jobs(api_key: str) -> List[dict]:
    resp = requests.get(
        f"{CRONJOB_API_BASE}/jobs",
        headers=_api_headers(api_key),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("jobs", [])


def delete_job(api_key: str, job_id: int) -> None:
    resp = requests.delete(
        f"{CRONJOB_API_BASE}/jobs/{job_id}",
        headers=_api_headers(api_key),
        timeout=15,
    )
    resp.raise_for_status()


def create_job(api_key: str, github_pat: str, title: str, hour: int, minute: int) -> int:
    """cron-job.org에 GitHub workflow_dispatch 호출 작업 1개 등록. job_id 반환."""
    payload = {
        "job": {
            "url": GITHUB_DISPATCH_URL,
            "enabled": True,
            "title": title,
            "saveResponses": True,
            "requestTimeout": 30,
            "requestMethod": 1,  # POST
            "schedule": {
                "timezone": "Asia/Seoul",
                "expiresAt": 0,
                "hours": [hour],
                "minutes": [minute],
                "mdays": [-1],
                "months": [-1],
                "wdays": [-1],
            },
            "extendedData": {
                "headers": {
                    "Authorization": f"Bearer {github_pat}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                "body": json.dumps({"ref": "main"}),
            },
            "notification": {
                "onFailure": True,
                "onFailureCount": 1,
                "onSuccess": False,
                "onDisable": False,
            },
        }
    }
    resp = requests.put(
        f"{CRONJOB_API_BASE}/jobs",
        headers=_api_headers(api_key),
        json=payload,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["jobId"]


def find_trend_scanner_jobs(jobs: List[dict]) -> List[dict]:
    """제목이 'Trend Scanner'로 시작하는 작업만 필터"""
    return [j for j in jobs if j.get("title", "").startswith("Trend Scanner")]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true", help="기존 작업 조회만")
    parser.add_argument("--force", action="store_true", help="기존 트렌드 스캐너 작업 삭제 후 재등록")
    parser.add_argument("--delete", action="store_true", help="기존 트렌드 스캐너 작업 삭제만")
    args = parser.parse_args()

    api_key = os.getenv("CRONJOB_API_KEY")
    github_pat = os.getenv("GITHUB_PAT")

    if not api_key:
        print("❌ .env에 CRONJOB_API_KEY가 없습니다.")
        print("   https://console.cron-job.org/settings 에서 API 키 생성 후 .env에 추가하세요.")
        return 1

    if not args.list and not args.delete and not github_pat:
        print("❌ .env에 GITHUB_PAT이 없습니다.")
        print("   GitHub Personal Access Token (Fine-grained, Actions: Read and write 권한)")
        print("   을 발급해 .env에 GITHUB_PAT=ghp_... 형태로 추가하세요.")
        print("   발급: https://github.com/settings/tokens?type=beta")
        return 1

    # 1. 기존 작업 조회
    print("[1/3] cron-job.org 기존 작업 조회...")
    try:
        all_jobs = list_jobs(api_key)
    except requests.HTTPError as e:
        print(f"❌ 조회 실패 (HTTP {e.response.status_code}): {e.response.text[:200]}")
        return 1

    existing = find_trend_scanner_jobs(all_jobs)
    print(f"  → 전체 {len(all_jobs)}개 / 트렌드 스캐너 작업 {len(existing)}개")

    for j in existing:
        print(f"    - jobId={j['jobId']}: {j['title']} (enabled={j.get('enabled')})")

    if args.list:
        return 0

    # 2. --force 또는 --delete 시 기존 작업 삭제
    if args.force or args.delete:
        if not existing:
            print("[2/3] 삭제할 트렌드 스캐너 작업 없음")
        else:
            print(f"[2/3] 기존 트렌드 스캐너 작업 {len(existing)}개 삭제...")
            for j in existing:
                try:
                    delete_job(api_key, j["jobId"])
                    print(f"  ✅ 삭제: jobId={j['jobId']} ({j['title']})")
                    time.sleep(0.3)  # rate limit 보호
                except requests.HTTPError as e:
                    print(f"  ❌ 삭제 실패 jobId={j['jobId']}: HTTP {e.response.status_code}")

        if args.delete:
            return 0
        existing = []  # force일 때 재등록을 위해 비움

    # 3. 등록 (이미 있으면 skip)
    print(f"[3/3] 트렌드 스캐너 작업 {len(JOBS)}개 등록...")
    existing_titles = {j["title"] for j in existing}
    created_count = 0
    skipped_count = 0
    failed_count = 0

    for spec in JOBS:
        if spec["title"] in existing_titles:
            print(f"  ⏭  skip (이미 존재): {spec['title']}")
            skipped_count += 1
            continue
        try:
            job_id = create_job(api_key, github_pat, spec["title"], spec["hour"], spec["minute"])
            print(f"  ✅ 등록: jobId={job_id} ({spec['title']})")
            created_count += 1
            time.sleep(1.5)  # rate limit (1 req/sec for creation)
        except requests.HTTPError as e:
            print(f"  ❌ 등록 실패 ({spec['title']}): HTTP {e.response.status_code} - {e.response.text[:200]}")
            failed_count += 1

    print()
    print(f"결과: 등록 {created_count}건, 스킵 {skipped_count}건, 실패 {failed_count}건")
    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
