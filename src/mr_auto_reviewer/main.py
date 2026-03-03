import argparse
import logging
import time

from dotenv import load_dotenv

from .ai_reviewer import AutoReviewer
from .config import AppConfig
from .feishu_client import FeishuClient
from .gitlab_client import GitLabMRClient
from .openclaw_reviewer import OpenClawReviewer
from .pipeline import MRReviewPipeline
from .sohu_client import SohuAgentClient
from .state_store import JsonStateStore
from .watch_lock import WatchProcessLock


def build_pipeline(config: AppConfig, args: argparse.Namespace) -> MRReviewPipeline:
    effective_dry_run = bool(config.dry_run or args.dry_run)

    gitlab_client = GitLabMRClient(
        gitlab_url=config.gitlab_url,
        reviewer_username=config.gitlab_reviewer_username,
        review_scope=config.gitlab_review_scope,
        username=config.gitlab_username,
        password=config.gitlab_password,
        private_token=config.gitlab_private_token,
        ssl_verify=config.gitlab_ssl_verify,
    )
    if config.review_provider == "openclaw":
        reviewer = OpenClawReviewer(
            agent_id=config.openclaw_review_agent,
            timeout_seconds=config.openclaw_review_timeout_seconds,
            local=config.openclaw_review_local,
            openclaw_bin=config.openclaw_review_bin,
        )
    else:
        reviewer = AutoReviewer(
            api_key=config.openai_api_key,
            model=config.openai_model,
            base_url=config.openai_base_url,
        )
    sohu_client = SohuAgentClient(
        webhook_url=config.sohu_agent_webhook_url,
        push_mode=config.sohu_push_mode,
        openclaw_bin=config.sohu_openclaw_bin,
        openclaw_channel=(args.channel or config.sohu_openclaw_channel),
        openclaw_account=(args.account or config.sohu_openclaw_account),
        openclaw_target=(args.target or config.sohu_openclaw_target),
        attach_report=config.sohu_attach_report,
        dry_run=effective_dry_run,
    )
    if effective_dry_run:
        feishu_client = FeishuClient(
            app_id=None,
            app_secret=None,
            receive_id=None,
            doc_folder_token=config.feishu_doc_folder_token,
            doc_url_base=config.feishu_doc_url_base,
        )
    else:
        feishu_client = FeishuClient(
            app_id=config.feishu_app_id,
            app_secret=config.feishu_app_secret,
            receive_id=config.feishu_receive_id,
            receive_id_type=config.feishu_receive_id_type,
            base_url=config.feishu_base_url,
            doc_folder_token=config.feishu_doc_folder_token,
            doc_url_base=config.feishu_doc_url_base,
        )
    state_store = JsonStateStore(config.state_file)
    return MRReviewPipeline(
        gitlab_client=gitlab_client,
        reviewer=reviewer,
        sohu_client=sohu_client,
        feishu_client=feishu_client,
        state_store=state_store,
        report_dir=config.report_dir,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GitLab MR auto reviewer")
    parser.add_argument("command", nargs="?", choices=["run-once", "watch"], default="run-once")  # noqa: S603
    parser.add_argument("--interval", type=int, default=300)
    parser.add_argument("--watch-pid-file", default="logs/mr_watch.pid")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--channel", default="")
    parser.add_argument("--account", default="")
    parser.add_argument("--target", default="")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def run_once(args: argparse.Namespace) -> int:
    try:
        config = AppConfig.from_env()
        pipeline = build_pipeline(config, args)
        results = pipeline.run_once()
    except Exception as exc:  # noqa: BLE001
        logging.error("run_once failed: %s", exc)
        return 0

    ok_count = sum(1 for item in results if item.status == "ok")
    fail_count = sum(1 for item in results if item.status == "failed")

    logging.info("processed=%s ok=%s failed=%s", len(results), ok_count, fail_count)
    for item in results:
        if item.status == "ok":
            logging.info("ok %s -> %s", item.mr_key, item.report_path)
        else:
            logging.error("failed %s -> %s", item.mr_key, item.error)
    if fail_count > 0:
        logging.warning("some MR processing failed; keep exit code 0 for scheduler compatibility")
    return 0


def watch(args: argparse.Namespace) -> int:
    lock = WatchProcessLock(args.watch_pid_file)
    if not lock.acquire():
        logging.warning("watch process already running, pid file=%s", args.watch_pid_file)
        return 0

    try:
        while True:
            code = run_once(args)
            if code != 0:
                logging.warning("run_once returned non-zero code=%s", code)
            time.sleep(args.interval)
    finally:
        lock.release()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    load_dotenv(args.env_file)

    if args.command == "run-once":
        return run_once(args)
    return watch(args)


if __name__ == "__main__":
    raise SystemExit(main())
