from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
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
    instances: Counter[str] = Counter()
    supportability: Counter[str] = Counter()
    workflow_details: list[dict[str, Any]] = []
    total_users = 0
    deployment_workflows = 0
    production_workflows = 0
    production_without_monitoring = 0
    production_without_criticality = 0
    production_without_owner = 0

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

        instance = _normalize_value(_workflow_value(workflow, "instance", "tier"))
        supportability_status = _normalize_value(
            _workflow_value(workflow, "supportability", "supportabilityStatus"), default="Not assessed"
        )

        criticality[workflow_criticality] += 1
        environments[environment] += 1
        purposes[purpose] += 1
        monitoring[monitoring_status] += 1
        instances[instance] += 1
        supportability[supportability_status] += 1

        is_deployment_managed = bool(
            _workflow_value(workflow, "deploymentManaged", "deployment_managed", default=False)
        )
        is_production = environment.lower() == "production"

        if is_deployment_managed:
            deployment_workflows += 1
        if is_production:
            production_workflows += 1
            if monitoring_status != "Monitored":
                production_without_monitoring += 1
            if workflow_criticality == "Unknown":
                production_without_criticality += 1
            if created_team == "Unassigned":
                production_without_owner += 1

        workflow_details.append({
            "name": _normalize_value(_workflow_value(workflow, "name"), default="(unnamed)"),
            "instance": instance,
            "environment": environment,
            "purpose": purpose,
            "owner": created_team,
            "criticality": workflow_criticality,
            "monitoring": monitoring_status,
            "supportability": supportability_status,
            "production": is_production,
            "deploymentManaged": is_deployment_managed,
        })

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
        "production_without_owner": production_without_owner,
        "criticality": dict(sorted(criticality.items())),
        "environments": dict(sorted(environments.items())),
        "purposes": dict(sorted(purposes.items())),
        "monitoring": dict(sorted(monitoring.items())),
        "instances": dict(sorted(instances.items())),
        "supportability": dict(sorted(supportability.items())),
        "workflow_details": workflow_details,
    }


def compute_adoption_report(result: dict[str, Any]) -> dict[str, Any]:
    """Derive team-adoption, developer-experience, and business-impact metrics.

    Kept separate from the operational inventory report per the requirement to
    maintain distinct reporting for adoption vs. day-to-day workflow tracking.
    """
    details = result.get("workflow_details", [])
    total = len(details) or 1

    def pct(numerator: int, denominator: int) -> float:
        return round((numerator / denominator) * 100, 1) if denominator else 0.0

    real_team_owners = {
        d["owner"] for d in details
        if d["owner"] not in ("Unassigned",) and not d["owner"].startswith("Individual:")
        and not d["owner"].startswith("Shared Automation Mailbox")
    }
    individual_owned = sum(1 for d in details if d["owner"].startswith("Individual:"))
    unassigned = sum(1 for d in details if d["owner"] == "Unassigned")
    active_instances = sorted(result.get("instances", {}).keys())

    prod = [d for d in details if d["production"]]
    prod_total = len(prod) or 1
    prod_high_crit = sum(1 for d in prod if d["criticality"] == "High")
    prod_supportable = sum(1 for d in prod if d["supportability"] == "Supportable")
    prod_monitored = sum(1 for d in prod if d["monitoring"] == "Monitored")

    deployment_managed = sum(1 for d in details if d["deploymentManaged"])
    backup_automation = sum(1 for d in details if d["purpose"] == "Backup")
    monitored_total = sum(1 for d in details if d["monitoring"] == "Monitored")
    supportable_total = sum(1 for d in details if d["supportability"] == "Supportable")

    return {
        "adoption": {
            "teams_actively_using_n8n": len(real_team_owners),
            "team_names": sorted(real_team_owners),
            "individual_owned_workflows": individual_owned,
            "unassigned_workflows": unassigned,
            "instances_in_use": active_instances,
            "instances_in_use_count": len(active_instances),
            "total_workflows": len(details),
        },
        "developer_experience": {
            "deployment_automation_workflows": deployment_managed,
            "deployment_automation_coverage_pct": pct(deployment_managed, len(details)),
            "backup_self_service_workflows": backup_automation,
            "monitoring_coverage_pct": pct(monitored_total, len(details)),
        },
        "business_impact": {
            "production_workflows": len(prod),
            "production_high_criticality_pct": pct(prod_high_crit, prod_total),
            "production_supportable_pct": pct(prod_supportable, prod_total),
            "production_monitored_pct": pct(prod_monitored, prod_total),
            "overall_supportable_pct": pct(supportable_total, len(details)),
        },
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
    lines.append(f"Report generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append(f"Total workflows: {result['total_workflows']}")
    lines.append(f"Total users: {result['total_users']}")
    lines.append(f"Deployment workflows: {result['deployment_workflows']}")
    lines.append(f"Production workflows: {result['production_workflows']}")
    lines.append(
        "Production gaps: "
        f"{result['production_without_monitoring']} without monitoring, "
        f"{result['production_without_criticality']} without criticality, "
        f"{result['production_without_owner']} without owner"
    )

    _format_breakdown(lines, "By N8N Instance", result["instances"])
    _format_breakdown(lines, "Created by Team", result["created_by_team"])
    _format_breakdown(lines, "Used by Team", result["used_by_team"])
    _format_breakdown(lines, "By Environment", result["environments"])
    _format_breakdown(lines, "By Purpose", result["purposes"])
    _format_breakdown(lines, "By Criticality", result["criticality"])
    _format_breakdown(lines, "By Monitoring Status", result["monitoring"])
    _format_breakdown(lines, "By Supportability", result["supportability"])

    adoption_report = compute_adoption_report(result)
    lines.append("")
    lines.append("=" * 40)
    lines.append("Adoption, Developer Experience & Business Impact")
    lines.append("(separate reporting lens - not part of operational inventory)")
    lines.append("=" * 40)

    a = adoption_report["adoption"]
    lines.append("")
    lines.append("Team Adoption")
    lines.append("-" * 20)
    lines.append(f"- Teams actively using N8N: {a['teams_actively_using_n8n']} ({', '.join(a['team_names']) or 'none'})")
    lines.append(f"- Individually-owned workflows (not team-assigned): {a['individual_owned_workflows']}")
    lines.append(f"- Unassigned/unowned workflows: {a['unassigned_workflows']}")
    lines.append(f"- N8N instances in active use: {a['instances_in_use_count']} ({', '.join(a['instances_in_use'])})")

    d = adoption_report["developer_experience"]
    lines.append("")
    lines.append("Developer Experience")
    lines.append("-" * 20)
    lines.append(f"- Deployment automation workflows: {d['deployment_automation_workflows']} ({d['deployment_automation_coverage_pct']}% of inventory)")
    lines.append(f"- Backup/self-service automation workflows: {d['backup_self_service_workflows']}")
    lines.append(f"- Overall monitoring coverage: {d['monitoring_coverage_pct']}%")

    b = adoption_report["business_impact"]
    lines.append("")
    lines.append("Business Impact")
    lines.append("-" * 20)
    lines.append(f"- Production workflows: {b['production_workflows']}")
    lines.append(f"- Production workflows at High criticality: {b['production_high_criticality_pct']}%")
    lines.append(f"- Production workflows rated Supportable: {b['production_supportable_pct']}%")
    lines.append(f"- Production workflows with monitoring: {b['production_monitored_pct']}%")
    lines.append(f"- Overall inventory rated Supportable: {b['overall_supportable_pct']}%")

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

    details_json = json.dumps(result.get("workflow_details", []))
    chart_data_json = json.dumps({
        "instances": result["instances"],
        "environments": result["environments"],
        "purposes": result["purposes"],
        "criticality": result["criticality"],
        "monitoring": result["monitoring"],
        "supportability": result["supportability"],
    })
    adoption_report = compute_adoption_report(result)
    ar_a = adoption_report["adoption"]
    ar_d = adoption_report["developer_experience"]
    ar_b = adoption_report["business_impact"]
    report_generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>N8N Usage Summary</title>
  <script src=\"https://cdn.jsdelivr.net/npm/chart.js@4\"></script>
  <script src=\"https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2\"></script>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: Arial, sans-serif; margin: 0; padding: 40px; background: #f5f7fb; color: #1f2937; }}
    .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 32px; border-radius: 12px; box-shadow: 0 8px 20px rgba(0,0,0,0.08); }}
    h1 {{ margin-bottom: 8px; }}
    h2 {{ font-size: 16px; }}
    .summary {{ font-size: 18px; margin-bottom: 12px; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; margin: 20px 0 28px; }}
    .card {{ background: #eef2ff; border-radius: 10px; padding: 16px; text-align: center; }}
    .card .value {{ font-size: 28px; font-weight: 700; color: #3730a3; }}
    .card .label {{ font-size: 13px; color: #4b5563; margin-top: 4px; }}
    .charts-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 24px; margin-bottom: 32px; }}
    .chart-box {{ background: #fafafa; border: 1px solid #e5e7eb; border-radius: 10px; padding: 16px; }}
    .chart-box canvas {{ max-height: 240px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 24px; margin-bottom: 32px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid #e5e7eb; text-align: left; }}
    th {{ background: #eef2ff; cursor: pointer; user-select: none; }}
    th.sortable:hover {{ background: #e0e7ff; }}
    .toolbar {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 16px 0; align-items: center; }}
    .toolbar input, .toolbar select {{ padding: 8px 10px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 14px; }}
    .toolbar input {{ flex: 1; min-width: 200px; }}
    .badge {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; font-weight: 600; }}
    .badge-high {{ background: #fee2e2; color: #991b1b; }}
    .badge-medium {{ background: #fef3c7; color: #92400e; }}
    .badge-low {{ background: #dcfce7; color: #166534; }}
    .badge-unknown {{ background: #e5e7eb; color: #374151; }}
    .badge-supportable {{ background: #dcfce7; color: #166534; }}
    .badge-needsreview {{ background: #fef3c7; color: #92400e; }}
    .badge-notsupportable {{ background: #fee2e2; color: #991b1b; }}
    .badge-notassessed {{ background: #e5e7eb; color: #374151; }}
    #resultCount {{ font-size: 13px; color: #6b7280; }}    .notice {{ background: #fffbeb; border: 1px solid #fbbf24; border-radius: 10px; padding: 16px 20px; margin: 16px 0 24px; font-size: 14px; line-height: 1.6; }}
    .notice strong {{ color: #92400e; }}
    .notice ul {{ margin: 8px 0 0; padding-left: 20px; }}  </style>
</head>
<body>
  <div class=\"container\">
    <h1>N8N Usage Summary</h1>
    <p style=\"color:#6b7280; font-size:13px; margin-top:-4px;\">Report generated: {report_generated_at}</p>
    <div class=\"summary\">
      <strong>Total workflows:</strong> {result['total_workflows']} |
      <strong>Users:</strong> {result['total_users']} |
      <strong>Deployment:</strong> {result['deployment_workflows']} |
      <strong>Production:</strong> {result['production_workflows']}
    </div>

    <div class=\"cards\">
      <div class=\"card\"><div class=\"value\">{result['total_workflows']}</div><div class=\"label\">Total Workflows</div></div>
      <div class=\"card\"><div class=\"value\">{result['production_workflows']}</div><div class=\"label\">Production</div></div>
      <div class=\"card\"><div class=\"value\">{result['production_without_monitoring']}</div><div class=\"label\">Prod without Monitoring</div></div>
      <div class=\"card\"><div class=\"value\">{result['production_without_criticality']}</div><div class=\"label\">Prod without Criticality</div></div>
      <div class=\"card\"><div class=\"value\">{result['production_without_owner']}</div><div class=\"label\">Prod without Owner</div></div>
    </div>

    <div class=\"charts-grid\">
      <div class=\"chart-box\"><h2>By N8N Instance</h2><canvas id=\"chartInstances\"></canvas></div>
      <div class=\"chart-box\"><h2>By Environment</h2><canvas id=\"chartEnvironments\"></canvas></div>
      <div class=\"chart-box\"><h2>By Purpose</h2><canvas id=\"chartPurposes\"></canvas></div>
      <div class=\"chart-box\"><h2>By Criticality</h2><canvas id=\"chartCriticality\"></canvas></div>
      <div class=\"chart-box\"><h2>By Monitoring Status</h2><canvas id=\"chartMonitoring\"></canvas></div>
      <div class=\"chart-box\"><h2>By Supportability</h2><canvas id=\"chartSupportability\"></canvas></div>
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
    </div>

    <h2>Workflow Inventory (live, searchable)</h2>
    <div class=\"toolbar\">
      <input id=\"searchBox\" type=\"text\" placeholder=\"Search by workflow name or owner...\" />
      <select id=\"filterInstance\"><option value=\"\">All Instances</option></select>
      <select id=\"filterEnvironment\"><option value=\"\">All Environments</option></select>
      <select id=\"filterCriticality\"><option value=\"\">All Criticality</option></select>
      <select id=\"filterSupportability\"><option value=\"\">All Supportability</option></select>
      <span id=\"resultCount\"></span>
    </div>
    <table id=\"inventoryTable\">
      <thead>
        <tr>
          <th class=\"sortable\" data-key=\"name\">Name</th>
          <th class=\"sortable\" data-key=\"instance\">Instance</th>
          <th class=\"sortable\" data-key=\"environment\">Environment</th>
          <th class=\"sortable\" data-key=\"purpose\">Purpose</th>
          <th class=\"sortable\" data-key=\"owner\">Owner</th>
          <th class=\"sortable\" data-key=\"criticality\">Criticality</th>
          <th class=\"sortable\" data-key=\"monitoring\">Monitoring</th>
          <th class=\"sortable\" data-key=\"supportability\">Supportability</th>
        </tr>
      </thead>
      <tbody id=\"inventoryBody\"></tbody>
    </table>
    <hr style="margin:40px 0; border:none; border-top:2px dashed #d1d5db;" />
    <h2 style="margin-bottom:4px;">Adoption, Developer Experience &amp; Business Impact</h2>
    <p style="color:#6b7280; font-size:13px; margin-top:0;">Separate reporting lens &mdash; not part of the operational workflow inventory above.</p>

    <div class="cards">
      <div class="card"><div class="value">{ar_a['teams_actively_using_n8n']}</div><div class="label">Teams Actively Using N8N</div></div>
      <div class="card"><div class="value">{ar_a['instances_in_use_count']}</div><div class="label">N8N Instances in Use</div></div>
      <div class="card"><div class="value">{ar_a['individual_owned_workflows']}</div><div class="label">Individually-Owned Workflows</div></div>
      <div class="card"><div class="value">{ar_a['unassigned_workflows']}</div><div class="label">Unowned Workflows</div></div>
    </div>

    <div class="grid">
      <div>
        <h2>Team Adoption</h2>
        <table>
          <tbody>
            <tr><td>Teams actively using N8N</td><td>{ar_a['teams_actively_using_n8n']} ({', '.join(ar_a['team_names']) or 'none'})</td></tr>
            <tr><td>Instances in active use</td><td>{', '.join(ar_a['instances_in_use'])}</td></tr>
            <tr><td>Individually-owned workflows</td><td>{ar_a['individual_owned_workflows']}</td></tr>
            <tr><td>Unassigned/unowned workflows</td><td>{ar_a['unassigned_workflows']}</td></tr>
          </tbody>
        </table>
      </div>

      <div>
        <h2>Developer Experience</h2>
        <table>
          <tbody>
            <tr><td>Deployment automation workflows</td><td>{ar_d['deployment_automation_workflows']} ({ar_d['deployment_automation_coverage_pct']}%)</td></tr>
            <tr><td>Backup/self-service automation</td><td>{ar_d['backup_self_service_workflows']}</td></tr>
            <tr><td>Overall monitoring coverage</td><td>{ar_d['monitoring_coverage_pct']}%</td></tr>
          </tbody>
        </table>
      </div>

      <div>
        <h2>Business Impact</h2>
        <table>
          <tbody>
            <tr><td>Production workflows</td><td>{ar_b['production_workflows']}</td></tr>
            <tr><td>Production at High criticality</td><td>{ar_b['production_high_criticality_pct']}%</td></tr>
            <tr><td>Production rated Supportable</td><td>{ar_b['production_supportable_pct']}%</td></tr>
            <tr><td>Production with monitoring</td><td>{ar_b['production_monitored_pct']}%</td></tr>
            <tr><td>Overall inventory Supportable</td><td>{ar_b['overall_supportable_pct']}%</td></tr>
          </tbody>
        </table>
      </div>
    </div>  </div>

  <script>
    const workflowDetails = {details_json};
    const chartData = {chart_data_json};

    function badgeClass(prefix, value) {{
      const key = String(value).toLowerCase().replace(/[^a-z]/g, '');
      return `badge badge-${{key || 'unknown'}}`;
    }}

    function renderChart(canvasId, dataObj, label) {{
      const ctx = document.getElementById(canvasId);
      if (!ctx) return;
      new Chart(ctx, {{
        type: 'bar',
        data: {{
          labels: Object.keys(dataObj),
          datasets: [{{
            label: label,
            data: Object.values(dataObj),
            backgroundColor: '#6366f1',
            borderRadius: 6,
          }}],
        }},
        plugins: [ChartDataLabels],
        options: {{
          responsive: true,
          plugins: {{
            legend: {{ display: false }},
            datalabels: {{
              anchor: 'end',
              align: 'top',
              color: '#1f2937',
              font: {{ weight: 'bold' }},
              formatter: (value) => value,
            }},
          }},
          scales: {{ y: {{ beginAtZero: true, ticks: {{ precision: 0 }} }} }},
        }},
      }});
    }}

    renderChart('chartInstances', chartData.instances, 'Workflows');
    renderChart('chartEnvironments', chartData.environments, 'Workflows');
    renderChart('chartPurposes', chartData.purposes, 'Workflows');
    renderChart('chartCriticality', chartData.criticality, 'Workflows');
    renderChart('chartMonitoring', chartData.monitoring, 'Workflows');
    renderChart('chartSupportability', chartData.supportability, 'Workflows');

    function populateFilter(selectId, key) {{
      const select = document.getElementById(selectId);
      const values = [...new Set(workflowDetails.map(w => w[key]))].sort();
      values.forEach(v => {{
        const opt = document.createElement('option');
        opt.value = v;
        opt.textContent = v;
        select.appendChild(opt);
      }});
    }}
    populateFilter('filterInstance', 'instance');
    populateFilter('filterEnvironment', 'environment');
    populateFilter('filterCriticality', 'criticality');
    populateFilter('filterSupportability', 'supportability');

    let sortKey = 'name';
    let sortAsc = true;

    function applyFilters() {{
      const search = document.getElementById('searchBox').value.toLowerCase();
      const fInstance = document.getElementById('filterInstance').value;
      const fEnvironment = document.getElementById('filterEnvironment').value;
      const fCriticality = document.getElementById('filterCriticality').value;
      const fSupportability = document.getElementById('filterSupportability').value;

      let filtered = workflowDetails.filter(w => {{
        const matchesSearch = !search ||
          w.name.toLowerCase().includes(search) ||
          w.owner.toLowerCase().includes(search);
        return matchesSearch &&
          (!fInstance || w.instance === fInstance) &&
          (!fEnvironment || w.environment === fEnvironment) &&
          (!fCriticality || w.criticality === fCriticality) &&
          (!fSupportability || w.supportability === fSupportability);
      }});

      filtered.sort((a, b) => {{
        const av = String(a[sortKey]).toLowerCase();
        const bv = String(b[sortKey]).toLowerCase();
        if (av < bv) return sortAsc ? -1 : 1;
        if (av > bv) return sortAsc ? 1 : -1;
        return 0;
      }});

      const tbody = document.getElementById('inventoryBody');
      tbody.innerHTML = filtered.map(w => `
        <tr>
          <td>${{w.name}}</td>
          <td>${{w.instance}}</td>
          <td>${{w.environment}}</td>
          <td>${{w.purpose}}</td>
          <td>${{w.owner}}</td>
          <td><span class=\"${{badgeClass('crit', w.criticality)}}\">${{w.criticality}}</span></td>
          <td>${{w.monitoring}}</td>
          <td><span class=\"${{badgeClass('supp', w.supportability)}}\">${{w.supportability}}</span></td>
        </tr>
      `).join('');
      document.getElementById('resultCount').textContent = `${{filtered.length}} of ${{workflowDetails.length}} workflows`;
    }}

    document.getElementById('searchBox').addEventListener('input', applyFilters);
    document.getElementById('filterInstance').addEventListener('change', applyFilters);
    document.getElementById('filterEnvironment').addEventListener('change', applyFilters);
    document.getElementById('filterCriticality').addEventListener('change', applyFilters);
    document.getElementById('filterSupportability').addEventListener('change', applyFilters);

    document.querySelectorAll('#inventoryTable th.sortable').forEach(th => {{
      th.addEventListener('click', () => {{
        const key = th.getAttribute('data-key');
        if (sortKey === key) {{
          sortAsc = !sortAsc;
        }} else {{
          sortKey = key;
          sortAsc = true;
        }}
        applyFilters();
      }});
    }});

    applyFilters();
  </script>
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
