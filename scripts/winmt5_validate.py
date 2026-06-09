#!/usr/bin/env python3
"""WINMT5-001 runner: validate MT5 demo connectivity for XAU/USD (read-only).

This script is meant to run on the WINDOWS host where MetaTrader5 is installed.
It performs read-only connectivity validation and NEVER places orders (it does
not call order_send / order_check) and NEVER prints credential values.

Behaviour by environment:
  * MetaTrader5 importable  -> run the full read-only validation against the
    live demo terminal and write a report.
  * MetaTrader5 NOT importable (e.g. inside WSL/Linux) -> classify as an
    ENVIRONMENT ISSUE, write a report that records what was/was not provable,
    and point to the Windows runner / bridge plan. Live validation is NOT faked.

Credentials are loaded from a local .env (never committed, never printed). If
python-dotenv is unavailable, a minimal built-in parser loads KEY=VALUE lines
into the environment without echoing any value.

Output: reports/runtime/winmt5_validation.md + .json (git-ignored runtime dir).

Usage (on the Windows MT5 host):
    python scripts/winmt5_validate.py
    python scripts/winmt5_validate.py --stdout
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.broker.connectivity import CheckStatus, MT5ConnectivityValidator  # noqa: E402
from src.broker.errors import BrokerError, MissingCredentialsError  # noqa: E402
from src.broker.mt5_settings import REQUIRED_VARS, load_mt5_settings  # noqa: E402

OUT_DIR = REPO_ROOT / "reports" / "runtime"
ENV_PATH = REPO_ROOT / ".env"


# --------------------------------------------------------------------------
# Safe .env loading (no value is ever printed)
# --------------------------------------------------------------------------

def load_env_safely(dotenv_path: Path = ENV_PATH) -> str:
    """Load .env into os.environ without printing any value.

    Returns a short status string (NAMES of loaded keys are not echoed either).
    """
    if not dotenv_path.is_file():
        return "no .env file found"
    # Prefer python-dotenv if available; otherwise use a minimal parser.
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(dotenv_path, override=False)
        return "loaded via python-dotenv"
    except Exception:
        loaded = 0
        for raw in dotenv_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key and key not in os.environ:
                os.environ[key] = value.strip()
                loaded += 1
        return f"loaded via builtin parser ({loaded} keys)"


# --------------------------------------------------------------------------
# Environment classification
# --------------------------------------------------------------------------

def try_import_mt5():
    """Return (client_or_None, reason). Never raises."""
    try:
        import MetaTrader5 as mt5  # type: ignore

        return mt5, "MetaTrader5 imported"
    except Exception as exc:  # ImportError on non-Windows hosts
        return None, f"MetaTrader5 not importable: {exc.__class__.__name__}"


def classify_environment(client) -> str:
    return "AVAILABLE" if client is not None else "ENVIRONMENT_ISSUE"


# --------------------------------------------------------------------------
# Report construction
# --------------------------------------------------------------------------

def _missing_required_vars() -> List[str]:
    return [name for name in REQUIRED_VARS if not str(os.environ.get(name, "")).strip()]


def build_environment_issue_report(
    env_status: str, import_reason: str, missing_vars: List[str]
) -> Dict[str, object]:
    """Honest report for a host that cannot run MT5 (no faking)."""
    creds_status = (
        "CONFIG_INCOMPLETE" if missing_vars else "PRESENT (names only; values not shown)"
    )
    checks = [
        {"name": "terminal_path_configured", "status": "SKIPPED",
         "detail": "cannot verify without MetaTrader5 on this host"},
        {"name": "demo_credentials_loaded",
         "status": "FAIL" if missing_vars else "PASS",
         "detail": ("missing: " + ", ".join(missing_vars)) if missing_vars
                   else "required MT5_* variables present (values not shown)"},
        {"name": "mt5_initialize", "status": "ENVIRONMENT_ISSUE",
         "detail": import_reason},
        {"name": "demo_login", "status": "SKIPPED", "detail": "pending Windows MT5 host"},
        {"name": "account_is_demo", "status": "SKIPPED", "detail": "pending Windows MT5 host"},
        {"name": "symbol_detected", "status": "SKIPPED", "detail": "pending Windows MT5 host"},
        {"name": "symbol_info_read", "status": "SKIPPED", "detail": "pending Windows MT5 host"},
        {"name": "candles_fetched", "status": "SKIPPED", "detail": "pending Windows MT5 host"},
        {"name": "spread_read", "status": "SKIPPED", "detail": "pending Windows MT5 host"},
        {"name": "no_order_send", "status": "PASS",
         "detail": "structural: the runner/validator reference no trade function"},
    ]
    return {
        "task": "WINMT5-001",
        "outcome": "ENVIRONMENT_ISSUE",
        "environment": env_status,
        "import_reason": import_reason,
        "env_load": "",  # filled by caller
        "credentials": creds_status,
        "symbol": str(os.environ.get("MT5_SYMBOL", "XAUUSD")).strip() or "XAUUSD",
        "checks": checks,
        "facts": {},
        "bridge_plan": _BRIDGE_PLAN,
    }


_BRIDGE_PLAN = [
    "Run this script on the Windows host where the MT5 terminal and the demo "
    "account are installed: `python scripts/winmt5_validate.py`.",
    "Ensure MetaTrader5 is installed in that Windows Python: `pip install MetaTrader5`.",
    "Provide demo credentials in a local .env on that host (never commit it): "
    "MT5_LOGIN, MT5_PASSWORD, MT5_SERVER (+ optional MT5_PATH, MT5_SYMBOL).",
    "If the bot runs in WSL while MT5 is on Windows, use a WSL->Windows bridge: "
    "invoke the Windows python.exe from WSL, or run a small Windows-side service "
    "that exposes read-only data; never expose an order endpoint.",
    "Fallback if no live bridge is ready: export replay data from the terminal "
    "and validate the pipeline on replay (no live order path).",
]


def run_validation(client) -> Dict[str, object]:
    """Run the full read-only validation against an available MT5 client."""
    settings = load_mt5_settings()
    validator = MT5ConnectivityValidator(settings)
    report = validator.validate(client)
    payload = report.to_dict()
    payload.update({
        "task": "WINMT5-001",
        "outcome": "VALIDATED" if report.all_proven else "INCOMPLETE",
        "environment": "AVAILABLE",
    })
    return payload


# --------------------------------------------------------------------------
# Rendering / IO
# --------------------------------------------------------------------------

def render_markdown(report: Dict[str, object], *, generated_at: str) -> str:
    lines: List[str] = []
    lines.append("# MT5 Demo Connectivity Validation (WINMT5-001)")
    lines.append("")
    lines.append(f"- Generated: {generated_at}")
    lines.append(f"- Outcome: **{report.get('outcome')}**")
    lines.append(f"- Environment: {report.get('environment')}")
    lines.append(f"- Symbol: {report.get('symbol')}")
    lines.append("- Real trading: **FORBIDDEN** — no order_send is ever called")
    if report.get("import_reason"):
        lines.append(f"- Import: {report['import_reason']}")
    lines.append("")
    lines.append("## Proof checklist")
    lines.append("")
    lines.append("| # | Check | Status | Detail |")
    lines.append("|---|---|---|---|")
    for i, c in enumerate(report.get("checks", []), start=1):  # type: ignore[arg-type]
        lines.append(f"| {i} | {c['name']} | {c['status']} | {c['detail']} |")
    lines.append("")
    facts = report.get("facts") or {}
    if facts:
        lines.append("## Non-secret facts (no credentials)")
        lines.append("")
        for k, v in facts.items():  # type: ignore[union-attr]
            lines.append(f"- {k}: {v}")
        lines.append("")
    if report.get("outcome") == "ENVIRONMENT_ISSUE":
        lines.append("## Windows MT5 runner / bridge plan")
        lines.append("")
        for step in report.get("bridge_plan", []):  # type: ignore[arg-type]
            lines.append(f"- {step}")
        lines.append("")
        lines.append("This host cannot import MetaTrader5, so live validation is "
                     "NOT marked complete. Re-run on the Windows MT5 host to prove "
                     "checks 3-9.")
        lines.append("")
    return "\n".join(lines)


def write_report(report: Dict[str, object]) -> Dict[str, Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    md = render_markdown(report, generated_at=generated_at)
    payload = {"generated_at": generated_at, **report}
    md_path = OUT_DIR / "winmt5_validation.md"
    json_path = OUT_DIR / "winmt5_validation.json"
    md_path.write_text(md, encoding="utf-8")
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return {"markdown": md_path, "json": json_path}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stdout", action="store_true", help="also print markdown")
    args = parser.parse_args()

    env_load = load_env_safely()
    client, import_reason = try_import_mt5()
    env_status = classify_environment(client)

    if env_status == "ENVIRONMENT_ISSUE":
        report = build_environment_issue_report(
            env_status, import_reason, _missing_required_vars()
        )
        report["env_load"] = env_load
        exit_code = 0  # a cleanly-classified environment issue is not a crash
    else:
        try:
            report = run_validation(client)
            report["env_load"] = env_load
            # A detected real account is a safety failure.
            real_flagged = any(
                c["name"] == "account_is_demo" and c["status"] == CheckStatus.FAIL.value
                for c in report.get("checks", [])  # type: ignore[arg-type]
            )
            exit_code = 2 if real_flagged or report["outcome"] != "VALIDATED" else 0
        except MissingCredentialsError as exc:
            # Report missing variable NAMES only.
            report = build_environment_issue_report(
                "AVAILABLE", "credentials incomplete", list(exc.missing)
            )
            report["outcome"] = "CONFIG_INCOMPLETE"
            report["env_load"] = env_load
            exit_code = 2
        except BrokerError as exc:
            report = {
                "task": "WINMT5-001", "outcome": "FAIL", "environment": "AVAILABLE",
                "symbol": str(os.environ.get("MT5_SYMBOL", "XAUUSD")).strip() or "XAUUSD",
                "import_reason": import_reason, "env_load": env_load,
                "checks": [{"name": "mt5_initialize", "status": "FAIL",
                            "detail": str(exc)}],
                "facts": {},
            }
            exit_code = 2

    paths = write_report(report)
    print(f"Outcome: {report['outcome']}")
    print(f"Wrote {paths['markdown'].relative_to(REPO_ROOT)}")
    print(f"Wrote {paths['json'].relative_to(REPO_ROOT)}")
    if args.stdout:
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        print()
        print(render_markdown(report, generated_at=generated_at))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
