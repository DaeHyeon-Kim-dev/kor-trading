"""CLI 진입점 (typer 기반)."""

from __future__ import annotations

from datetime import date as _date
from pathlib import Path

import typer

from kor_trading.infrastructure.clock import SystemClock
from kor_trading.infrastructure.config import AppConfig, Secrets
from kor_trading.infrastructure.container import build_container
from kor_trading.infrastructure.logging import configure_logging

app = typer.Typer(name="kor-trading", help="한국 주식 트레이딩 보조 멀티 에이전트")


@app.command()
def run(
    config_path: Path = typer.Option(  # noqa: B008
        Path("config/default.yaml"), "--config", "-c", help="YAML 설정 파일"
    ),
    data_path: Path = typer.Option(  # noqa: B008
        Path("data"), "--data", "-d", help="저장 베이스 디렉토리"
    ),
    target_date: str | None = typer.Option(
        None, "--date", help="분석 기준일 YYYY-MM-DD (기본: 오늘)"
    ),
    log_level: str = typer.Option("INFO", "--log-level"),
    force: bool = typer.Option(False, "--force", help="활성 시간/요일 체크 무시"),
) -> None:
    """일일 파이프라인 1회 실행."""
    configure_logging(level=log_level)

    config = AppConfig.from_yaml(config_path)
    secrets = Secrets()  # type: ignore[call-arg]

    now_kst = SystemClock().now()
    if not force and not config.schedule.is_active(now_kst):
        typer.echo(f"OUT_OF_HOURS — skip ({now_kst:%Y-%m-%d %H:%M KST})")
        raise typer.Exit(code=0)

    as_of = _date.fromisoformat(target_date) if target_date else now_kst.date()  # pragma: no cover
    run_id = f"{as_of.isoformat()}/{now_kst:%H%M}"  # pragma: no cover

    container = build_container(config, secrets, data_base_path=data_path)  # pragma: no cover
    opts = config.to_pipeline_options()  # pragma: no cover
    result = container.pipeline.execute(  # pragma: no cover
        criteria=config.to_selection_criteria(),
        as_of=as_of,
        run_id=run_id,
        indicator_lookback_days=opts.indicator_lookback_days,
        issue_lookback_days=opts.issue_lookback_days,
        max_issues_per_ticker=opts.max_issues_per_ticker,
    )
    typer.echo(str(result.report_path))  # pragma: no cover


def main() -> None:  # pragma: no cover
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
