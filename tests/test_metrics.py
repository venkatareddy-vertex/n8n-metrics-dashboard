import json

from n8n_metrics import analyze_workflows, format_html_report, format_summary_report


WORKFLOWS = [
    {
        "name": "WF-101",
        "createdByTeam": "Data Platform",
        "usedByTeams": ["Data Platform", "Payments", "Support"],
    },
    {
        "name": "WF-102",
        "createdByTeam": "Payments",
        "usedByTeams": ["Payments", "Support"],
    },
    {
        "name": "WF-103",
        "createdByTeam": "Support",
        "usedByTeams": ["Support"],
    },
    {
        "name": "WF-104",
        "createdByTeam": "Data Platform",
        "usedByTeams": ["Data Platform"],
    },
]


def test_analyze_workflows_counts_creations_and_usage():
    result = analyze_workflows(WORKFLOWS)

    assert result["total_workflows"] == 4
    assert result["created_by_team"] == {
        "Data Platform": 2,
        "Payments": 1,
        "Support": 1,
    }
    assert result["used_by_team"] == {
        "Data Platform": 2,
        "Payments": 2,
        "Support": 3,
    }


def test_analyze_workflows_accepts_json_file_input(tmp_path):
    file_path = tmp_path / "workflows.json"
    file_path.write_text(json.dumps(WORKFLOWS), encoding="utf-8")

    with open(file_path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)

    result = analyze_workflows(payload)

    assert result["total_workflows"] == 4
    assert result["created_by_team"]["Payments"] == 1


def test_analyze_workflows_accepts_csv_file_input(tmp_path):
    file_path = tmp_path / "workflows.csv"
    file_path.write_text(
        "name,createdByTeam,usedByTeams\n"
        "WF-201,Data Platform,Data Platform|Payments\n"
        "WF-202,Payments,Payments|Support\n",
        encoding="utf-8",
    )

    result = analyze_workflows(file_path)

    assert result["total_workflows"] == 2
    assert result["created_by_team"]["Data Platform"] == 1
    assert result["used_by_team"]["Support"] == 1


def test_format_summary_report_renders_readable_table():
    result = analyze_workflows(WORKFLOWS)
    report = format_summary_report(result)

    assert "N8N Usage Summary" in report
    assert "Created by Team" in report
    assert "Used by Team" in report
    assert "Data Platform" in report


def test_format_html_report_renders_dashboard():
    result = analyze_workflows(WORKFLOWS)
    report = format_html_report(result)

    assert "<html" in report.lower()
    assert "N8N Usage Summary" in report
    assert "Created by Team" in report
    assert "Used by Team" in report


def test_analyze_workflows_includes_full_vertex_team_roster():
    result = analyze_workflows(
        WORKFLOWS,
        all_teams=["Data Platform", "Payments", "Support", "Engineering", "Finance"],
    )

    assert result["created_by_team"]["Engineering"] == 0
    assert result["used_by_team"]["Finance"] == 0
    assert result["created_by_team"]["Support"] == 1

def test_analyze_workflows_tracks_inventory_and_production_gaps():
    workflows = [
        {
            "name": "Deploy production",
            "createdByTeam": "Platform",
            "usedByTeams": ["Platform", "Payments"],
            "users": ["alice", "bob"],
            "environment": "production",
            "purpose": "Deployment",
            "criticality": "High",
            "monitoring": True,
            "deploymentManaged": True,
        },
        {
            "name": "Untracked production job",
            "createdByTeam": "Payments",
            "users": 3,
            "environment": "Production",
            "purpose": "Operations",
            "monitoring": False,
        },
    ]

    result = analyze_workflows(workflows)

    assert result["total_users"] == 5
    assert result["deployment_workflows"] == 1
    assert result["production_workflows"] == 2
    assert result["production_without_monitoring"] == 1
    assert result["production_without_criticality"] == 1
    assert result["criticality"] == {"High": 1, "Unknown": 1}
    assert result["monitoring"] == {"Monitored": 1, "Not monitored": 1}
