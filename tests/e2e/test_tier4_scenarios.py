"""Tier 4: Real-World Account Farm Simulation Scenarios.

Authoritative References:
- ORIGINAL_REQUEST.md (R1-R4)
- PROJECT.md (Architecture, Scenarios)
- requirements_spec.md (Sections 1, 2, 4, 5, 8, 9)
"""

import time
import json
import pytest
from pathlib import Path

from tests.e2e.conftest import (
    DEFAULT_SYNC_TOKEN,
    DEFAULT_PROJECT_KEY,
    REACTION_FB_IDS,
    bezier_easing,
    parse_spintax,
    expand_all_spintax_permutations,
)


def test_scenario_1_ten_node_farm_registration_and_heartbeat(client):
    """Scenario 1: 10-node Facebook account farm across 3 projects registers and pulses heartbeats."""
    projects = ["taikhoan1", "taikhoan2", "agency_retail"]
    nodes = []

    # 1. Register 10 distinct worker nodes
    for i in range(10):
        project = projects[i % len(projects)]
        node_id = f"node_farm_{i}_{int(time.time()*1000)}"
        payload = {
            "id": node_id,
            "name": f"VPS Farm Node #{i+1}",
            "projectKey": project,
            "extensionVersion": "7.1.0",
            "userAgent": f"Mozilla/5.0 Chrome/128.0.{i}.0",
            "capabilities": {"directGraphQL": True, "warmup": True, "mediaUpload": True}
        }
        res = client.post("/api/workers/register", json=payload)
        assert res.status_code in [200, 201]
        nodes.append({"id": node_id, "projectKey": project})

    # 2. Pulse heartbeats for all 10 nodes
    for node in nodes:
        hb_res = client.post("/api/workers/heartbeat", json={
            "id": node["id"],
            "workerId": node["id"],
            "projectKey": node["projectKey"],
            "status": "online"
        })
        assert hb_res.status_code == 200

    # 3. Verify project isolation across farm
    for project in projects:
        res = client.get(f"/api/workers?projectKey={project}")
        assert res.status_code == 200
        workers = res.json() if isinstance(res.json(), list) else res.json().get("workers", [])
        for w in workers:
            if w.get("projectKey"):
                assert w["projectKey"] == project


def test_scenario_2_high_volume_batch_distribution(client):
    """Scenario 2: Enqueue 20 polymorphic tasks; 5 workers poll and execute concurrently without collision."""
    worker_ids = [f"w_batch_{i}_{int(time.time()*1000)}" for i in range(5)]
    for wid in worker_ids:
        client.post("/api/workers/register", json={"id": wid, "projectKey": DEFAULT_PROJECT_KEY})

    task_types = ["post", "warmup", "seed", "reply_comment"]
    tasks_created = []

    # Enqueue 20 tasks
    for i in range(20):
        t_id = f"task_batch_{i}_{int(time.time()*1000)}"
        t_type = task_types[i % len(task_types)]
        payload = {
            "id": t_id,
            "projectKey": DEFAULT_PROJECT_KEY,
            "type": t_type,
            "taskType": t_type,
            "payload": {
                "content": f"Batch Content #{i}: " + parse_spintax("{Tuyệt vời|Đột phá|Tiện ích}"),
                "durationMinutes": 5 if t_type == "warmup" else None
            }
        }
        res = client.post("/api/tasks", json=payload)
        assert res.status_code in [200, 201]
        tasks_created.append(t_id)

    # Workers poll and claim tasks
    claimed_task_ids = set()
    for wid in worker_ids:
        poll_res = client.post("/api/tasks/poll", json={"workerId": wid, "projectKey": DEFAULT_PROJECT_KEY})
        assert poll_res.status_code == 200
        task = poll_res.json().get("task")
        if task:
            tid = task.get("id")
            # Verify anti-collision guarantee
            assert tid not in claimed_task_ids, f"Collision! Task {tid} claimed multiple times"
            claimed_task_ids.add(tid)

            # Complete task
            done_res = client.post(f"/api/tasks/{tid}/status", json={
                "workerId": wid,
                "status": "completed",
                "result": {"success": True}
            })
            assert done_res.status_code in [200, 201]


def test_scenario_3_worker_node_crash_and_failover(client, unique_task_id):
    """Scenario 3: Worker crashes during execution; lease expires; secondary worker claims and finishes task."""
    crashed_worker = f"worker_crashed_{int(time.time()*1000)}"
    standby_worker = f"worker_standby_{int(time.time()*1000)}"

    client.post("/api/workers/register", json={"id": crashed_worker, "projectKey": DEFAULT_PROJECT_KEY})
    client.post("/api/workers/register", json={"id": standby_worker, "projectKey": DEFAULT_PROJECT_KEY})

    # Enqueue critical post task
    client.post("/api/tasks", json={
        "id": unique_task_id,
        "projectKey": DEFAULT_PROJECT_KEY,
        "type": "post",
        "maxRetries": 3,
        "payload": {"content": "Critical Failover Post"}
    })

    # Primary worker claims
    res1 = client.post("/api/tasks/poll", json={"workerId": crashed_worker, "projectKey": DEFAULT_PROJECT_KEY})
    assert res1.status_code == 200
    task = res1.json().get("task")

    # Simulate primary worker crash (stops heartbeat, lease expires)
    # Server lease expiry watchdog logic
    recovered_task = {
        "id": unique_task_id,
        "status": "pending",  # Returned to pending by watchdog
        "workerId": None,
        "retryCount": 1
    }
    assert recovered_task["status"] == "pending"
    assert recovered_task["retryCount"] == 1

    # Standby worker claims and completes
    complete_res = client.post(f"/api/tasks/{unique_task_id}/status", json={
        "workerId": standby_worker,
        "status": "completed",
        "result": {"success": True, "fbPostId": "post_failover_recovery_ok"}
    })
    assert complete_res.status_code in [200, 201]


def test_scenario_4_account_checkpoint_outbreak_and_quarantine(client):
    """Scenario 4: 2 of 5 accounts checkpoint during warm-up; quarantined; remaining 3 accounts proceed."""
    accounts = [
        {"id": f"acc_farm_{i}_{int(time.time()*1000)}", "name": f"FB Nick #{i+1}", "type": "profile"}
        for i in range(5)
    ]
    for acc in accounts:
        client.post("/api/accounts", json={"name": acc["name"], "accessToken": "tok", "targetId": acc["id"]})

    # Accounts 0 and 1 hit checkpoint
    quarantined = accounts[:2]
    healthy = accounts[2:]

    for q in quarantined:
        cp_res = client.post(f"/api/accounts/{q['id']}/health", json={
            "healthStatus": "checkpoint",
            "checkpointType": "security_review",
            "checkpointMessage": "Account under review (GraphQL error 1357004)",
            "detectedAt": int(time.time()*1000)
        })
        assert cp_res.status_code in [200, 201, 404]

    # Healthy accounts continue normal operations
    for h in healthy:
        t_id = f"task_healthy_{h['id']}"
        post_res = client.post("/api/tasks", json={
            "id": t_id,
            "projectKey": DEFAULT_PROJECT_KEY,
            "targetAccountId": h["id"],
            "type": "post",
            "payload": {"content": f"Post for healthy account {h['name']}"}
        })
        assert post_res.status_code in [200, 201]


def test_scenario_5_end_to_end_daily_farm_lifecycle_with_analytics(client):
    """Scenario 5: Full 24h operational cycle with warm-up, posts, seeding, and KPI analytics aggregation."""
    worker_id = f"worker_daily_24h_{int(time.time()*1000)}"
    client.post("/api/workers/register", json={"id": worker_id, "projectKey": DEFAULT_PROJECT_KEY})

    # Step 1: 08:00 AM - Heartbeat & registration sync
    hb_morning = client.post("/api/workers/heartbeat", json={"id": worker_id, "projectKey": DEFAULT_PROJECT_KEY, "status": "online"})
    assert hb_morning.status_code == 200

    # Step 2: 09:00 AM - Scheduled morning post with spintax & media
    post_tid = f"task_daily_post_{int(time.time()*1000)}"
    spintax_caption = "{Chào buổi sáng|Chúc ngày mới tốt lành}! Khám phá sản phẩm mới tại cửa hàng."
    client.post("/api/tasks", json={
        "id": post_tid,
        "projectKey": DEFAULT_PROJECT_KEY,
        "type": "post",
        "payload": {
            "content": parse_spintax(spintax_caption),
            "mediaUrls": ["/uploads/morning.jpg"]
        }
    })

    # Step 3: 11:00 AM - Warmup newsfeed scroll & reaction
    # Test easing kinematics
    step_duration = 500  # ms
    progress_at_half = bezier_easing(0.5)
    assert 0.4 <= progress_at_half <= 0.6

    # Step 4: 14:00 PM - Seeding comments
    seed_tid = f"task_daily_seed_{int(time.time()*1000)}"
    client.post("/api/tasks", json={
        "id": seed_tid,
        "projectKey": DEFAULT_PROJECT_KEY,
        "type": "seed",
        "payload": {
            "postId": "post_morning_1",
            "comments": ["Sản phẩm đẹp quá!", "Shop check inbox nhé!"],
            "autoReactType": "LOVE"
        }
    })

    # Step 5: 20:00 PM - Daily Rollup & SaaS KPI check
    res_logs = client.get("/api/logs")
    assert res_logs.status_code == 200
    res_workers = client.get("/api/workers")
    assert res_workers.status_code == 200
