"""LLM chat service with tool-use against scheduler agent capabilities."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import timedelta
from typing import AsyncGenerator, Dict, List

from openai import AsyncOpenAI

from app.config import get_openai_settings
from app.services.excel_io import fetch_backlog
from app.services.gains_service import load_gains, save_gains, validate_gains
from app.services.hints_service import load_hints, save_hints, validate_hint
from app.services.optimizer import (
    DAYS,
    DEFAULT_OBJECTIVE_GAINS,
    apply_custom_preferences,
    optimize_schedule,
)
from app.services.preferences_service import (
    load_preferences,
    save_preferences,
    validate_rule,
)
from app.utils.date_utils import get_next_monday


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an AI scheduling assistant embedded in an Industrial Maintenance Scheduler.

You help the user understand and improve their weekly work-order schedule by reading
and modifying optimizer settings, then re-running the optimizer to show results.

The user sees work orders, trades, and days on a calendar. They do NOT know about
internal concepts like hints, gains, or preferences. When they say things like
"clear Tuesday for Electrical" or "move WO-1234 to Friday", they are describing
what they want the **schedule** to look like — translate their intent into the
appropriate tool calls. Never ask the user to speak in terms of hints or gains.

Internal concepts (the user does not need to know these names):
- **Gains** control how the optimizer weighs objectives (priority, safety, etc.).
- **Hints** are soft nudges: `scheduled: true` suggests placement on a day/trade,
  `scheduled: false` discourages it. To remove work from a day, create
  `scheduled: false` hints for the relevant work orders on that day.
- **Preferences** are regex rules that remap work-order fields before optimization.
- **Schedule** runs the CP-SAT optimizer and returns the weekly assignment.
- **Current Schedule** reads the current optimizer output so you can see which work
  orders are on which shift/resource row. Use this when the user asks about load,
  balancing, or moving work between shifts.
- **Place** directly positions work orders on the calendar without re-optimizing.
  Accepts one or many placements. Trade defaults to the work order's own trade;
  pass a different trade to reassign (like double-click edit).  This is best when
  it is undesireable to run the optimizer, which, for example, will schedule unhinted 
  work orders in any vacant slots.

Trade vs. Resource: The calendar has rows for each **shift** (resource). Preference
rules may remap a work order's raw trade to a different shift name (e.g. E/I PMs
may map to "NC-E/I PM" even though the backlog trade is "NC-E/I"). Both
`get_backlog` and `get_current_schedule` reflect these remapped trades, so when the
user refers to a calendar row name like "NC-E/I PM", search by that name.

Before creating hints or placing work orders, **always call `get_backlog`** first
(unless the backlog is already in context from an earlier tool call). Use the exact
`id` values from the result. When results are truncated, `all_ids` contains the
complete list of matching `{id, trade}` pairs — use those for batch operations.
When the user refers to a group (e.g. "all electrical work", "the pump jobs"),
search and act on all matches — do not ask for individual confirmation. Only ask
for clarification when a single-WO request genuinely matches multiple unrelated
work orders.

When the user asks about the current schedule, load balance, or moving work orders
between shifts, call `get_current_schedule` to see the actual assignments. Do not
rely solely on the backlog context — the schedule shows where work orders actually
landed after optimization and preference remapping.

When the user asks you to change something, use the available tools. Always confirm
what you changed and summarize the effect. Keep responses concise and actionable.
When presenting schedule data, use brief summaries rather than dumping raw JSON.\
"""


# ---------------------------------------------------------------------------
# Tool schemas (OpenAI function-calling format)
# ---------------------------------------------------------------------------

TOOLS: List[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_gains",
            "description": "Read the current optimizer objective gains and their defaults.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_gains",
            "description": (
                "Update one or more optimizer objective gains. "
                "Valid keys: age, priority, safety, type, load_balance, hints, schedule_bonus. "
                "Values must be non-negative numbers. schedule_bonus must exceed load_balance."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "gains": {
                        "type": "object",
                        "description": "Partial dict of gain keys to new float values.",
                        "additionalProperties": {"type": "number"},
                    }
                },
                "required": ["gains"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_hints",
            "description": "Read current agent schedule hints.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_hints",
            "description": (
                "Set agent schedule hints. Each hint nudges a work order toward "
                "(or away from) a specific day and trade."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "hints": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "work_order_id": {"type": "string"},
                                "day": {
                                    "type": "string",
                                    "enum": DAYS,
                                },
                                "trade": {"type": "string"},
                                "scheduled": {"type": "boolean"},
                            },
                            "required": ["work_order_id", "day", "trade", "scheduled"],
                        },
                    }
                },
                "required": ["hints"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clear_hints",
            "description": "Remove ALL schedule adjustments. Only use when the user explicitly asks to start fresh or reset everything.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_preferences",
            "description": "Read current optimizer preference rules (regex-based field remapping).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_preferences",
            "description": (
                "Replace optimizer preference rules. Each rule has a 'match' dict "
                "(field -> regex) and a 'set' dict (field -> new value)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "rules": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "match": {
                                    "type": "object",
                                    "additionalProperties": {"type": "string"},
                                },
                                "set": {
                                    "type": "object",
                                    "additionalProperties": {"type": "string"},
                                },
                            },
                            "required": ["match", "set"],
                        },
                    }
                },
                "required": ["rules"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_backlog",
            "description": (
                "Search the current work-order backlog. Returns matching work orders "
                "with their id, trade, description, priority, type, duration, equipment, "
                "and dept. Fuzzy-matches across all fields (hyphens/separators ignored). "
                "When results exceed 50, the response includes an `all_ids` list with "
                "every matching {id, trade} pair. Use `all_ids` for batch placements."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "search": {
                        "type": "string",
                        "description": "Optional keyword(s) to fuzzy-match across all work order fields (case-insensitive, ignores hyphens/separators).",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_schedule",
            "description": (
                "View the current schedule: which work orders are assigned to which "
                "shift/resource row on which day. Each assignment includes the "
                "`resource` field (calendar row name, e.g. 'NC-E/I PM') which may "
                "differ from the raw backlog `trade` due to preference rules. "
                "Use this to inspect load per shift before moving work orders."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_schedule",
            "description": (
                "Run the CP-SAT optimizer with current gains, hints, and preferences. "
                "Returns a summary with assigned/unassigned counts and per-shift daily hours."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "place_work_order",
            "description": (
                "Place one or more work orders on specific days of the calendar. "
                "This immediately shows them without running the optimizer. "
                "Each placement's trade defaults to the work order's own trade "
                "from the backlog. Pass a different trade to reassign "
                "(same as a user double-clicking to edit)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "placements": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "work_order_id": {"type": "string"},
                                "day": {"type": "string", "enum": DAYS},
                                "trade": {
                                    "type": "string",
                                    "description": (
                                        "Override trade/resource. "
                                        "Omit to use the backlog trade."
                                    ),
                                },
                            },
                            "required": ["work_order_id", "day"],
                        },
                    }
                },
                "required": ["placements"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Backlog helpers
# ---------------------------------------------------------------------------

_MAX_BACKLOG_RESULTS = 50
_NORMALIZE_RE = re.compile(r"[-_/\s]+")


def _normalize(s: str) -> str:
    return _NORMALIZE_RE.sub("", s).lower()


def _fuzzy_match(wo: dict, search: str) -> bool:
    """Return True if every search token appears in at least one field value."""
    tokens = search.lower().split()
    field_values = [_normalize(str(v)) for v in wo.values()]
    return all(any(_normalize(tok) in fv for fv in field_values) for tok in tokens)


def _fetch_backlog_map() -> Dict[str, dict]:
    """Return the current backlog as {wo_id: compact_dict}.

    Applies custom preference rules so that the ``trade`` field reflects the
    effective calendar resource (e.g. "NC-E/I PM") rather than the raw EAM
    trade.  This ensures backlog searches, hints, and context summaries all
    use the same trade names the user sees on the calendar.
    """
    start_date = get_next_monday()
    work_orders = fetch_backlog(start_date=start_date)
    work_orders = apply_custom_preferences(work_orders)
    return {
        str(wo.id): {
            "id": str(wo.id),
            "trade": wo.trade,
            "description": wo.description,
            "priority": wo.priority,
            "type": wo.type,
            "duration_hours": wo.duration_hours,
            "equipment": wo.equipment,
            "dept": wo.dept,
        }
        for wo in work_orders
    }


def _build_context_summary() -> str:
    """Build a rich context string for the LLM with backlog, hints, and gains."""
    try:
        backlog = _fetch_backlog_map()
    except Exception:
        return ""

    start_date = get_next_monday()
    lines = [
        f"Schedule week: {start_date.isoformat()}",
        f"Backlog: {len(backlog)} work orders",
        "",
    ]

    ids_by_trade: Dict[str, List[str]] = defaultdict(list)
    for wo in backlog.values():
        ids_by_trade[wo["trade"]].append(wo["id"])
    for trade in sorted(ids_by_trade):
        ids = sorted(ids_by_trade[trade])
        lines.append(f"{trade} ({len(ids)}): {', '.join(ids)}")

    hints = load_hints()
    if hints:
        lines.append("")
        parts = [
            f"{wo_id} \u2192 {day}/{trade}" for wo_id, (day, trade, _) in hints.items()
        ]
        lines.append(f"Active hints: {', '.join(parts)}")

    gains = load_gains()
    overrides = {k: v for k, v in gains.items() if v != DEFAULT_OBJECTIVE_GAINS.get(k)}
    if overrides:
        parts = [f"{k}={v}" for k, v in overrides.items()]
        lines.append(f"Gain overrides: {', '.join(parts)}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------


def dispatch_tool(name: str, arguments: dict) -> str:
    """Execute a tool call and return the JSON-serialized result."""
    if name == "get_gains":
        return json.dumps(
            {"gains": load_gains(), "defaults": dict(DEFAULT_OBJECTIVE_GAINS)}
        )

    if name == "update_gains":
        gains = arguments["gains"]
        validate_gains(gains)
        merged = {**DEFAULT_OBJECTIVE_GAINS, **gains}
        save_gains(merged)
        return json.dumps({"status": "ok", "gains": merged})

    if name == "get_hints":
        hints = load_hints()
        items = [
            {"work_order_id": wo_id, "day": d, "trade": t, "scheduled": s}
            for wo_id, (d, t, s) in hints.items()
        ]
        return json.dumps({"hints": items})

    if name == "update_hints":
        backlog = _fetch_backlog_map()
        converted = {}
        for item in arguments["hints"]:
            wo_id = item["work_order_id"]
            scheduled = item["scheduled"]
            if wo_id not in backlog:
                if scheduled:
                    raise ValueError(f"Work order {wo_id!r} not found in backlog")
                continue
            trade = backlog[wo_id]["trade"]
            validate_hint(item["day"], trade, scheduled)
            converted[wo_id] = (item["day"], trade, scheduled)
        existing = load_hints()
        existing.update(converted)
        save_hints(existing)
        return json.dumps({"status": "ok", "count": len(existing)})

    if name == "clear_hints":
        save_hints({})
        return json.dumps({"status": "ok"})

    if name == "get_preferences":
        return json.dumps({"rules": load_preferences()})

    if name == "update_preferences":
        rules = arguments["rules"]
        for rule in rules:
            validate_rule(rule)
        save_preferences(rules)
        return json.dumps({"status": "ok", "count": len(rules)})

    if name == "get_current_schedule":
        return json.dumps(_run_schedule())

    if name == "get_backlog":
        backlog = _fetch_backlog_map()
        search = (arguments.get("search") or "").strip()
        if search:
            matches = [wo for wo in backlog.values() if _fuzzy_match(wo, search)]
        else:
            matches = list(backlog.values())
        truncated = len(matches) > _MAX_BACKLOG_RESULTS
        result: dict = {
            "work_orders": matches[:_MAX_BACKLOG_RESULTS],
            "total": len(matches),
            "truncated": truncated,
        }
        if truncated:
            result["all_ids"] = [
                {"id": wo["id"], "trade": wo["trade"]} for wo in matches
            ]
        return json.dumps(result)

    if name == "run_schedule":
        return json.dumps(_run_schedule())

    if name == "place_work_order":
        backlog = _fetch_backlog_map()
        converted = {}
        result_placements = []
        for item in arguments["placements"]:
            wo_id = item["work_order_id"]
            if wo_id not in backlog:
                raise ValueError(f"Work order {wo_id!r} not found in backlog")
            trade = item.get("trade") or backlog[wo_id]["trade"]
            day = item["day"]
            validate_hint(day, trade, True)
            converted[wo_id] = (day, trade, True)
            result_placements.append(
                {
                    "work_order_id": wo_id,
                    "day_offset": DAYS.index(day),
                    "resource_id": trade,
                }
            )
        existing = load_hints()
        existing.update(converted)
        save_hints(existing)
        return json.dumps(
            {
                "status": "ok",
                "count": len(result_placements),
                "placements": result_placements,
            }
        )

    return json.dumps({"error": f"Unknown tool: {name}"})


def _run_schedule() -> dict:
    """Run the optimizer and return a denormalized result dict.

    Each assigned entry includes both ``trade`` (raw backlog trade) and
    ``resource`` (the calendar shift row, which may differ after preference
    remapping).
    """
    start_date = get_next_monday()
    gains = load_gains()
    hints = load_hints()
    work_orders = fetch_backlog(start_date=start_date)
    schedule = optimize_schedule(
        work_orders=work_orders,
        start_date=start_date,
        hints=hints or None,
        objective_gains=gains,
    )

    wo_by_id = {str(wo.id): wo for wo in work_orders}
    assigned_ids: set[str] = set()
    assigned: List[dict] = []
    daily_hours: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for a in schedule.assignments:
        wo = wo_by_id.get(str(a.work_order_id))
        if wo is None:
            continue
        assigned_ids.add(str(wo.id))
        sched_date = start_date + timedelta(days=a.day_offset)
        day_name = (
            DAYS[a.day_offset] if 0 <= a.day_offset < len(DAYS) else str(a.day_offset)
        )
        daily_hours[a.resource_id][day_name] += wo.duration_hours
        assigned.append(
            {
                "work_order_id": str(wo.id),
                "date": sched_date.isoformat(),
                "day_of_week": day_name,
                "trade": wo.trade,
                "resource": a.resource_id,
                "description": wo.description,
                "priority": wo.priority,
                "duration_hours": wo.duration_hours,
                "type": wo.type,
            }
        )

    unassigned = [
        {"work_order_id": str(wo.id), "trade": wo.trade, "priority": wo.priority}
        for wo in work_orders
        if str(wo.id) not in assigned_ids
    ]

    return {
        "start_date": start_date.isoformat(),
        "gains": gains,
        "assigned": assigned,
        "unassigned": unassigned,
        "summary": {
            "total_work_orders": len(work_orders),
            "assigned_count": len(assigned),
            "unassigned_count": len(unassigned),
            "per_shift_daily_hours": {
                trade: dict(days) for trade, days in daily_hours.items()
            },
        },
    }


# ---------------------------------------------------------------------------
# Chat loop
# ---------------------------------------------------------------------------

MAX_TOOL_ROUNDS = 10
REFRESH_SENTINEL = "\x00REFRESH"
PLACE_SENTINEL = "\x00PLACE"
MUTATING_TOOLS = {
    "update_gains",
    "update_hints",
    "clear_hints",
    "update_preferences",
    "run_schedule",
}


async def run_chat(messages: List[dict]) -> AsyncGenerator[str, None]:
    """Stream an LLM response, handling tool calls in a loop.

    Yields text chunks for the client. If any mutating tool was called,
    yields REFRESH_SENTINEL as the final item so the route can emit a
    [REFRESH] SSE event.
    """
    settings = get_openai_settings()
    if not settings["api_key"]:
        yield "Chat is unavailable — OPENAI_API_KEY is not configured."
        return

    client = AsyncOpenAI(api_key=settings["api_key"])
    model = settings["model"]

    context = _build_context_summary()
    system_msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    if context:
        system_msgs.append({"role": "system", "content": context})
    conversation = system_msgs + messages
    mutated = False
    placements: list = []

    for _ in range(MAX_TOOL_ROUNDS):
        response = await client.chat.completions.create(
            model=model,
            messages=conversation,
            tools=TOOLS,
            stream=True,
        )

        tool_calls_in_progress: dict[int, dict] = {}
        assistant_content = ""
        has_tool_calls = False

        async for chunk in response:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                continue

            if delta.content:
                assistant_content += delta.content
                yield delta.content

            if delta.tool_calls:
                has_tool_calls = True
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_in_progress:
                        tool_calls_in_progress[idx] = {
                            "id": tc.id or "",
                            "name": "",
                            "arguments": "",
                        }
                    entry = tool_calls_in_progress[idx]
                    if tc.id:
                        entry["id"] = tc.id
                    if tc.function and tc.function.name:
                        entry["name"] = tc.function.name
                    if tc.function and tc.function.arguments:
                        entry["arguments"] += tc.function.arguments

        if not has_tool_calls:
            if placements:
                yield PLACE_SENTINEL + json.dumps(placements)
            elif mutated:
                yield REFRESH_SENTINEL
            return

        assistant_msg: dict = {
            "role": "assistant",
            "content": assistant_content or None,
        }
        assistant_msg["tool_calls"] = [
            {
                "id": tc["id"],
                "type": "function",
                "function": {"name": tc["name"], "arguments": tc["arguments"]},
            }
            for tc in sorted(tool_calls_in_progress.values(), key=lambda t: t["id"])
        ]
        conversation.append(assistant_msg)

        for tc in sorted(tool_calls_in_progress.values(), key=lambda t: t["id"]):
            if tc["name"] in MUTATING_TOOLS:
                mutated = True
            args = json.loads(tc["arguments"]) if tc["arguments"] else {}
            try:
                result = dispatch_tool(tc["name"], args)
            except (ValueError, KeyError, TypeError) as exc:
                result = json.dumps({"error": str(exc)})
            if tc["name"] == "place_work_order":
                try:
                    parsed = json.loads(result)
                    if "placements" in parsed:
                        placements.extend(parsed["placements"])
                except (json.JSONDecodeError, TypeError):
                    pass
            conversation.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                }
            )
