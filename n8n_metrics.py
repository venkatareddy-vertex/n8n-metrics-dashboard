from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


def _normalize_team(value: Any) -> str:
    if value is None:
        return "Unassigned"
    cleaned = str(value).strip()
    return cleaned if cleaned else "Unassigned"


def _coerce_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = value.split("|") if "|" in value else [value]
        return [str(item).strip() for item in values if str(item).strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []

def _normalize_value(value: Any, default: str = "Unknown") -> str:
    if value is None:
        return default
    cleaned = str(value).strip()
    return cleaned if cleaned else default

def _workflow_value(workflow: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in workflow and workflow[key] not in (None, ""):
            return workflow[key]
    return default


def _load_workflows(source: Any) -> list[dict[str, Any]]:
    if isinstance(source, (str, Path)):
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Workflow file not found: {path}")
        suffix = path.suffix.lower()
        if suffix == ".json":
            with path.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
            if isinstance(payload, list):
                return payload
            if isinstance(payload, dict):
                return payload.get("workflows", [])
            raise ValueError("JSON workflow input must be a list or contain a 'workflows' key")
        if suffix == ".csv":
            rows = []
            with path.open("r", encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    if "usedByTeams" in row and row["usedByTeams"]:
                        row["usedByTeams"] = row["usedByTeams"].split("|")
                    elif "teams" in row and row["teams"]:
                        row["teams"] = row["teams"].split("|")
                    rows.append(row)
            return rows
        raise ValueError(f"Unsupported file format: {suffix}")

    if isinstance(source, list):
        return source

    if isinstance(source, dict):
        return source.get("workflows", [])

    raise TypeError("Workflows must be a list, a JSON-like dict, or a file path")


def analyze_workflows(workflows: Any, all_teams: list[str] | None = None) -> dict[str, Any]:
    items = _load_workflows(workflows)

    created_by_team: Counter[str] = Counter()
    used_by_team: Counter[str] = Counter()
    criticality: Counter[str] = Counter()
    environments: Counter[str] = Counter()
    purposes: Counter[str] = Counter()
    monitoring: Counter[str] = Counter()
    total_users = 0
    deployment_workflows = 0
    production_workflows = 0
    production_without_monitoring = 0
    production_without_criticality = 0

    roster = [
        _normalize_team(team)
        for team in (all_teams or [])
        if _normalize_team(team) != "Unassigned"
    ]

    for workflow in items:
        created_team = _normalize_team(
            workflow.get("createdByTeam") or workflow.get("created_by_team") or workflow.get("createdBy")
        )
        created_by_team[created_team] += 1

        used_teams = workflow.get("usedByTeams") or workflow.get("used_by_teams") or workflow.get("teams") or []
        if not used_teams:
            used_teams = [created_team]

        for team in _coerce_list(used_teams):
            used_by_team[_normalize_team(team)] += 1

        users = _workflow_value(workflow, "users", "userCount", "user_count", default=[])
        if isinstance(users, (int, float)):
            total_users += int(users)
        else:
            total_users += len(_coerce_list(users))

        workflow_criticality = _normalize_value(
            _workflow_value(workflow, "criticality", "criticalityLevel")
        )
        environment = _normalize_value(_workflow_value(workflow, "environment", "env"))
        purpose = _normalize_value(_workflow_value(workflow, "purpose", "useCase", "use_case"))
        monitoring_value = _workflow_value(
            workflow, "monitoring", "monitoringStatus", "monitoring_status"
        )
        monitoring_status = (
            "Monitored"
            if monitoring_value is True
            else "Not monitored"
            if monitoring_value is False
            else _normalize_value(monitoring_value)
        )

        criticality[workflow_criticality] += 1
        environments[environment] += 1
        purposes[purpose] += 1
        monitoring[monitoring_status] += 1

        if _workflow_value(workflow, "deploymentManaged", "deployment_managed", default=False):
            deployment_workflows += 1
        if environment.lower() == "production":
            production_workflows += 1
            if monitoring_status != "Monitored":
                production_without_monitoring += 1
            if workflow_criticality == "Unknown":
                production_without_criticality += 1

    if roster:
        for team in roster:
            created_by_team.setdefault(team, 0)
            used_by_team.setdefault(team, 0)

    return {
        "total_workflows": len(items),
        "n8n_usage": len(items),
        "created_by_team": dict(sorted(created_by_team.items())),
        "used_by_team": dict(sorted(used_by_team.items())),
        "total_users": total_users,
        "deployment_workflows": deployment_workflows,
        "production_workflows": production_workflows,
        "production_without_monitoring": production_without_monitoring,
        "production_without_criticality": production_without_criticality,
        "criticality": dict(sorted(criticality.items())),
        "environments": dict(sorted(environments.items())),
        "purposes": dict(sorted(purposes.items())),
        "monitoring": dict(sorted(monitoring.items())),
    }


def _format_breakdown(lines: list[str], title: str, counts: dict[str, int]) -> None:
    lines.append("")
    lines.append(title)
    lines.append("-" * 20)
    for key, count in counts.items():
        lines.append(f"- {key}: {count}")


def format_summary_report(result: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("N8N Usage Summary")
    lines.append("=" * 40)
    lines.append(f"Total workflows: {result['total_workflows']}")
    lines.append(f"Total users: {result['total_users']}")
    lines.append(f"Deployment workflows: {result['deployment_workflows']}")
    lines.append(f"Production workflows: {result['production_workflows']}")
    lines.append(
        "Production gaps: "
        f"{result['production_without_monitoring']} without monitoring, "
        f"{result['production_without_criticality']} without criticality"
    )

    _format_breakdown(lines, "Created by Team", result["created_by_team"])
    _format_breakdown(lines, "Used by Team", result["used_by_team"])
    _format_breakdown(lines, "By Environment", result["environments"])
    _format_breakdown(lines, "By Purpose", result["purposes"])
    _format_breakdown(lines, "By Criticality", result["criticality"])
    _format_breakdown(lines, "By Monitoring Status", result["monitoring"])

    return "\n".join(lines)


def format_html_report(result: dict[str, Any]) -> str:
    def rows(counts: dict[str, int]) -> str:
        html_rows = []
        for team, count in counts.items():
            html_rows.append(
                "<tr>"
                f"<td>{team}</td><td>{count}</td>"
                "</tr>"
            )
        return "\n".join(html_rows)

    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>N8N Usage Summary</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f7fb; color: #1f2937; }}
    .container {{ max-width: 900px; margin: 0 auto; background: white; padding: 32px; border-radius: 12px; box-shadow: 0 8px 20px rgba(0,0,0,0.08); }}
    h1 {{ margin-bottom: 8px; }}
    .summary {{ font-size: 18px; margin-bottom: 24px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 24px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid #e5e7eb; text-align: left; }}
    th {{ background: #eef2ff; }}
  </style>
</head>
<body>
  <div class=\"container\">
    <h1>N8N Usage Summary</h1>
    <div class=\"summary\">
      <strong>Total workflows:</strong> {result['total_workflows']} |
      <strong>Users:</strong> {result['total_users']} |
      <strong>Deployment:</strong> {result['deployment_workflows']} |
      <strong>Production:</strong> {result['production_workflows']}
    </div>
    <div class=\"summary\">
      <strong>Production gaps:</strong>
      {result['production_without_monitoring']} without monitoring,
      {result['production_without_criticality']} without criticality
    </div>

    <div class=\"grid\">
      <div>
        <h2>Created by Team</h2>
        <table>
          <thead>
            <tr><th>Team</th><th>Count</th></tr>
          </thead>
          <tbody>
            {rows(result['created_by_team'])}
          </tbody>
        </table>
      </div>

      <div>
        <h2>Used by Team</h2>
        <table>
          <thead>
            <tr><th>Team</th><th>Count</th></tr>
          </thead>
          <tbody>
            {rows(result['used_by_team'])}
          </tbody>
        </table>
      </div>

      <div>
        <h2>By Environment</h2>
        <table>
          <thead>
            <tr><th>Environment</th><th>Count</th></tr>
          </thead>
          <tbody>
            {rows(result['environments'])}
          </tbody>
        </table>
      </div>

      <div>
        <h2>By Purpose</h2>
        <table>
          <thead>
            <tr><th>Purpose</th><th>Count</th></tr>
          </thead>
          <tbody>
            {rows(result['purposes'])}
          </tbody>
        </table>
      </div>

      <div>
        <h2>By Criticality</h2>
        <table>
          <thead>
            <tr><th>Criticality</th><th>Count</th></tr>
          </thead>
          <tbody>
            {rows(result['criticality'])}
          </tbody>
        </table>
      </div>

      <div>
        <h2>By Monitoring Status</h2>
        <table>
          <thead>
            <tr><th>Status</th><th>Count</th></tr>
          </thead>
          <tbody>
            {rows(result['monitoring'])}
          </tbody>
        </table>
      </div>
    </div>
  </div>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze N8N workflow ownership and usage by team.")
    parser.add_argument("--input", required=True, help="Path to a JSON or CSV file containing workflow records")
    parser.add_argument("--output", help="Optional path for JSON output file")
    parser.add_argument("--report", action="store_true", help="Print a readable summary report instead of raw JSON")
    parser.add_argument("--html", action="store_true", help="Generate a browser-friendly HTML dashboard")
    parser.add_argument(
        "--all-teams",
        nargs="*",
        default=[],
        help="Optional list of all Vertex teams to include in the report, even with zero workflow counts",
    )
    args = parser.parse_args()

    result = analyze_workflows(args.input, all_teams=args.all_teams)

    if args.html:
        html = format_html_report(result)
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("w", encoding="utf-8") as fh:
                fh.write(html)
                fh.write("\n")
        else:
            print(html)
        return

    if args.report:
        print(format_summary_report(result))
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("w", encoding="utf-8") as fh:
                fh.write(format_summary_report(result))
                fh.write("\n")
        return

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
            fh.write("\n")
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
