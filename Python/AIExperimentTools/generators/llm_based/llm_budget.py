"""Conservative, persistent request reservations for a shared Grok pilot budget."""

import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from threading import Lock


_LOCK = Lock()
INPUT_USD_PER_MILLION = 4
OUTPUT_USD_PER_MILLION = 12


def estimate_cost_usd(usage):
    """Conservative estimate using this budget's rates, not an invoice total."""
    values = [usage.get("input_tokens"), usage.get("output_tokens")]
    if any(type(value) is not int or value < 0 for value in values):
        return None
    return (values[0] * INPUT_USD_PER_MILLION + values[1] * OUTPUT_USD_PER_MILLION) / 1_000_000


class LLMBudgetExceeded(RuntimeError):
    """No provider call was made because the shared budget cannot admit it."""


def reserve_request(settings, model, base_url, request, run_id=None):
    path_value = settings.get("llm_budget_path")
    if path_value is None:
        if "llm_budget_usd" in settings or "llm_max_requests" in settings:
            raise ValueError("llm_budget_path is required when a budget is configured")
        return None

    if model != "grok-4.5" or base_url.rstrip("/") != "https://api.x.ai/v1":
        raise ValueError("The pilot budget rates cover only grok-4.5 at api.x.ai")
    output_limit = request.get("max_output_tokens")
    if type(output_limit) is not int or output_limit <= 0:
        raise ValueError("Budgeted requests require positive max_output_tokens")
    limit = Decimal(str(settings.get("llm_budget_usd", "5.50")))
    if not limit.is_finite() or limit <= 0 or limit > Decimal("5.50"):
        raise ValueError("llm_budget_usd must be positive and at most 5.50")
    limit_micro_usd = int(limit * 1_000_000)
    max_requests = settings.get("llm_max_requests", 36)
    if type(max_requests) is not int or not 1 <= max_requests <= 36:
        raise ValueError("llm_max_requests must be an integer from 1 to 36")

    # Byte count conservatively overestimates text tokens; reserve additional
    # space for message framing and provider schema handling. No tools or media.
    payload = {
        "input": request["input"],
        "schema": request["text_format"].model_json_schema() if request.get("text_format") else None,
    }
    input_bound = len(json.dumps(payload, ensure_ascii=True).encode("utf-8")) + 4096
    # Long-context grok-4.5 rates: $4/M input and $12/M output (including reasoning).
    # https://docs.x.ai/developers/models/grok-4.5
    reserve_micro_usd = input_bound * INPUT_USD_PER_MILLION + output_limit * OUTPUT_USD_PER_MILLION
    path = Path(path_value).expanduser().resolve()

    with _locked_ledger(path):
        if path.exists():
            ledger = json.loads(path.read_text(encoding="utf-8"))
            if (ledger["limit_micro_usd"], ledger["max_requests"]) != (
                limit_micro_usd, max_requests
            ):
                raise ValueError("Shared LLM budget settings must match the existing ledger")
        else:
            ledger = {
                "limit_micro_usd": limit_micro_usd,
                "max_requests": max_requests,
                "requests": [],
            }
        reservations = ledger["requests"]
        reserved = sum(entry["reserved_micro_usd"] for entry in reservations)
        if ledger.get("blocked"):
            raise LLMBudgetExceeded("LLM ledger is blocked: provider usage exceeded its reservation")
        if len(reservations) >= max_requests or reserved + reserve_micro_usd > limit_micro_usd:
            raise LLMBudgetExceeded(
                f"LLM budget exhausted: {len(reservations)}/{max_requests} requests, "
                f"${reserved / 1_000_000:.4f}/${limit_micro_usd / 1_000_000:.2f} reserved; "
                f"next request needs ${reserve_micro_usd / 1_000_000:.4f}"
            )
        index = len(reservations)
        reservations.append({
            "request_number": index + 1,
            "run_id": run_id,
            "reserved_at": datetime.now(timezone.utc).isoformat(),
            "reserved_micro_usd": reserve_micro_usd,
            "input_token_bound": input_bound,
            "max_output_tokens": output_limit,
            "status": "reserved",
        })
        _write_ledger(path, ledger)
    return path, index


def finish_request(reservation, *, usage=None, error=None):
    if reservation is None:
        return
    path, index = reservation
    with _locked_ledger(path):
        ledger = json.loads(path.read_text(encoding="utf-8"))
        entry = ledger["requests"][index]
        entry["status"] = "error" if error else "response_received"
        if error:
            entry["error_type"] = error
        if usage is not None:
            entry["usage"] = usage
            if (
                usage.get("input_tokens", 0) > entry["input_token_bound"]
                or usage.get("output_tokens", 0) > entry["max_output_tokens"]
            ):
                ledger["blocked"] = True
                _write_ledger(path, ledger)
                raise RuntimeError("Provider usage exceeded its reservation; further LLM calls blocked")
        # Never release reservations: failed, timed-out and unparsed requests can
        # still have been billed, and crash recovery must not restart the budget.
        _write_ledger(path, ledger)


@contextmanager
def _locked_ledger(path):
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = path.with_suffix(path.suffix + ".lock")
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise RuntimeError("LLM budget ledger is locked; no request was sent") from exc
        os.close(descriptor)
        try:
            yield
        finally:
            lock_path.unlink()


def _write_ledger(path, ledger):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(ledger, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
