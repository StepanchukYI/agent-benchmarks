from __future__ import annotations

import time

from ab_server.leaderboard import compute_matrix
from ab_server.models import TaskResult
from sqlmodel import Session, SQLModel, create_engine


def _engine():
    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(eng)
    return eng


def test_compute_matrix_under_250ms_for_1000_rows():
    eng = _engine()
    models = [f"model-{i}" for i in range(5)]
    tiers = ["T0", "T1", "T2", "T3"]
    suites = ["L0_smoke", "L1_smoke", "L2_smoke", "L3_smoke", "L4_smoke"]

    with Session(eng) as session:
        rows: list[TaskResult] = []
        i = 0
        # 5 × 4 × 5 = 100 buckets; 10 reps per bucket -> 1000 rows.
        for m in models:
            for t in tiers:
                for s in suites:
                    for rep in range(10):
                        rows.append(
                            TaskResult(
                                task_id=f"{s}_{rep:03d}",
                                suite=s,
                                model=m,
                                tier=t,
                                tier_hash="sha256:abc",
                                status="completed",
                                score_total=0.5 + (i % 50) / 100.0,
                                cost_usd=0.001 + (i % 20) / 1000.0,
                                latency_ms=1000,
                            )
                        )
                        i += 1
        session.add_all(rows)
        session.commit()

        # warm-up
        compute_matrix(session)

        start = time.perf_counter()
        matrix = compute_matrix(session)
        elapsed_ms = (time.perf_counter() - start) * 1000.0

    assert elapsed_ms < 250.0, f"compute_matrix took {elapsed_ms:.1f}ms"
    assert len(matrix.rows) == len(models) * len(tiers)
    assert matrix.suites == sorted(suites)
