# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""view command — serve experiment results in the browser."""
from __future__ import annotations

import json
import os
import sys

import click

from ..utils.output import echo, echo_error, has_rich, get_console, show_results_table


def _display_result_summary(summary_path: str) -> None:
    """Load and display a summary.json file."""
    _console = get_console()
    _HAS_RICH = has_rich()

    try:
        with open(summary_path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        echo_error(f"Failed to read '{summary_path}': {e}")
        sys.exit(1)

    if _HAS_RICH:
        from rich.syntax import Syntax
        _console.print(Syntax(json.dumps(data, indent=2), "json", theme="monokai", line_numbers=False))
    else:
        click.echo(json.dumps(data, indent=2))

    # Also display as a results table if the data has the right shape
    if "aggregated_evaluators" in data or "aggregated_metrics" in data or "total_records" in data:
        show_results_table(data)


@click.command()
@click.option("--port", "-p", "port", default=8765, help="Port to serve on (default: 8765)")
@click.option("--no-browser", is_flag=True, help="Don't automatically open browser")
@click.help_option("--help", "-h")
def view(port, no_browser):
    """View experiment results in your browser.

    Opens an interactive results viewer showing metrics across all targets.

    Examples:
        ev view
        ev view --port 9090
    """
    import http.server
    import signal
    import socketserver
    import threading
    import webbrowser
    from pathlib import Path

    _console = get_console()
    _HAS_RICH = has_rich()

    # Resolve output directory: try config, then default locations.
    output_dir = None
    for cfg_candidate in ("config.yaml", "evals.yaml", "experiment/config.yaml"):
        if os.path.exists(cfg_candidate):
            try:
                from ..utils.discovery import load_config_safe
                cfg = load_config_safe(cfg_candidate)
                if cfg:
                    output_dir = getattr(cfg.experiment, "output_path", None)
            except Exception:
                pass
            break
    if not output_dir:
        if os.path.isdir("output"):
            output_dir = "output"
        elif os.path.isdir("experiment/output"):
            output_dir = "experiment/output"
        else:
            output_dir = "output"

    def _find_experiments(base_dir):
        base = Path(base_dir)
        if not base.is_dir():
            return []
        experiments = []
        for child in sorted(base.iterdir(), reverse=True):
            if not child.is_dir():
                continue
            if list(child.glob("*_results.jsonl")) or list(child.glob("*_summary.json")):
                experiments.append(child)
        return experiments

    def _load_results(exp_path):
        """Load results from an experiment directory into ViewResultsData format."""
        exp_path = Path(exp_path)
        models = []
        all_records = []
        all_evaluators = {}

        def _find_primary_score(evaluator_name, values_dict):
            """Find the primary score from an evaluator's aggregated dict.

            Heuristic (matches Foundry portal behavior — one score per evaluator):
            1. {evaluator_name}_mean  (e.g. coherence → coherence_mean)
            2. {evaluator_name}       (exact key)
            3. Key containing 'score' AND ending in '_mean'
            4. First key ending in '_mean'
            5. Key named 'score'
            6. First numeric value
            """
            name = evaluator_name.lower()
            # 1. evaluator_name + _mean
            if f"{name}_mean" in values_dict:
                return values_dict[f"{name}_mean"]
            # 2. exact evaluator name as key
            if name in values_dict and isinstance(values_dict[name], (int, float)):
                return values_dict[name]
            # 3. key with 'score' and '_mean'
            for k, v in values_dict.items():
                if isinstance(v, (int, float)) and "score" in k and k.endswith("_mean"):
                    return v
            # 4. first key ending in _mean
            for k, v in values_dict.items():
                if isinstance(v, (int, float)) and k.endswith("_mean"):
                    return v
            # 5. key named 'score'
            if "score" in values_dict and isinstance(values_dict["score"], (int, float)):
                return values_dict["score"]
            # 6. first numeric value
            for v in values_dict.values():
                if isinstance(v, (int, float)):
                    return v
            return None

        def _flatten_agg(agg):
            """Extract one primary score per evaluator for the comparison view.

            Matches Foundry portal behavior: one score per evaluator (e.g.
            coherence: 4.0, response_completeness: 0.976) instead of hoisting
            all sub-keys to top level.
            """
            flat = {}
            for evaluator_name, evaluator_val in agg.items():
                if isinstance(evaluator_val, dict):
                    primary = _find_primary_score(evaluator_name, evaluator_val)
                    if primary is not None:
                        flat[evaluator_name] = primary
                elif isinstance(evaluator_val, (int, float)):
                    flat[evaluator_name] = evaluator_val
            return flat

        for summary_file in sorted(exp_path.glob("*_summary.json")):
            model_name = summary_file.stem.replace("_summary", "")
            results_file = exp_path / f"{model_name}_results.jsonl"

            with open(summary_file) as f:
                summary_data = json.load(f)

            records = []
            if results_file.exists():
                with open(results_file) as f:
                    for line in f:
                        if line.strip():
                            records.append(json.loads(line))

            agg = _flatten_agg(summary_data.get("aggregated_evaluators", summary_data.get("aggregated_metrics", {})))
            # Add standard overview
            agg["number_of_records"] = summary_data.get("total_records", len(records))
            # Compute average response time from records
            times = [r.get("system_evaluators", r.get("system_metrics", {})).get("response_time", {}).get("response_time_ms", 0) for r in records]
            if times:
                agg["average_response_time_ms"] = sum(times) / len(times)

            all_evaluators.update(agg)

            # Build tags from first record's args
            base_name = model_name.split("__")[0] if "__" in model_name else model_name
            display_name = model_name.split("__", 1)[1] if "__" in model_name else model_name
            tags = {"model_name": base_name}
            if records:
                tags.update({k: v for k, v in records[0].get("args", {}).items()})

            models.append({
                "model_name": model_name,
                "model_display_name": display_name,
                "summary": {
                    "run_id": model_name,
                    "aggregated_evaluators": agg,
                    "tags": tags,
                },
                "records": records,
                "files": {
                    "summary": str(summary_file),
                    "records": str(results_file) if results_file.exists() else None,
                },
            })
            all_records.extend(records)

        return {
            "summary": {
                "run_id": exp_path.name,
                "aggregated_evaluators": all_evaluators,
                "tags": {},
            },
            "records": all_records,
            "output_path": str(exp_path),
            "models": models,
        }

    # Resolve output directory
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    experiments = _find_experiments(output_dir)
    if not experiments:
        # No experiments yet — launch UI with empty data to show empty state
        results_data = {
            "experiment_name": "",
            "output_path": "",
            "models": [],
            "summary": {},
            "records": [],
        }
        output_path = output_dir
    else:
        output_path = str(experiments[0])

    if experiments:
        try:
            results_data = _load_results(output_path)
        except Exception as e:
            echo_error(f"Failed to load results: {e}")
            sys.exit(1)

    # Load the viewer HTML template
    viewer_html_path = Path(__file__).parent.parent.parent / "ui" / "results_viewer.html"
    if not viewer_html_path.exists():
        echo_error("Results viewer UI not found. The UI component may not be installed.")
        sys.exit(1)

    html_template = viewer_html_path.read_text()

    def _build_html():
        """Re-read data from disk and inject into HTML on every request."""
        current_experiments = _find_experiments(output_dir)
        if current_experiments:
            try:
                current_data = _load_results(str(current_experiments[0]))
            except Exception:
                current_data = {"experiment_name": "", "output_path": "", "models": [], "summary": {}, "records": []}
        else:
            current_data = {"experiment_name": "", "output_path": "", "models": [], "summary": {}, "records": []}

        safe_json = json.dumps(current_data).replace("</", "<\\/")
        safe_dir = json.dumps(output_dir).replace("</", "<\\/")
        inject_script = (
            "<script>\n"
            f"        window.__EVEE_RESULTS_DATA__ = {safe_json};\n"
            f"        window.__EVEE_OUTPUT_DIR__ = {safe_dir};\n"
            "    </script>"
        )
        return html_template.replace("</head>", f"{inject_script}</head>")

    class _ViewerHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(_build_html().encode())
            elif self.path == "/api/experiments":
                experiments = _find_experiments(output_dir)
                data = []
                for e in experiments:
                    info = {"name": e.name, "path": str(e)}
                    # Gather summary metadata for the overview page
                    summaries = sorted(e.glob("*_summary.json"))
                    info["num_runs"] = len(summaries)
                    info["created"] = e.stat().st_mtime
                    # Collect metric names and status from first summary
                    evaluator_names = []
                    if summaries:
                        try:
                            with open(summaries[0]) as sf:
                                first_summary = json.load(sf)
                            agg = first_summary.get("aggregated_evaluators", first_summary.get("aggregated_metrics", {}))
                            for k, v in agg.items():
                                if isinstance(v, dict):
                                    evaluator_names.extend(v.keys())
                                else:
                                    evaluator_names.append(k)
                        except Exception:
                            pass
                    info["metrics"] = [m for m in evaluator_names if "fail" not in m.lower()
                                       and m not in ("number_of_records", "average_response_time_ms")]
                    info["status"] = "Completed"
                    data.append(info)
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(data).encode())
            elif self.path.startswith("/api/results/"):
                exp_name = self.path[len("/api/results/"):].strip("/")
                if not exp_name or "/" in exp_name or ".." in exp_name:
                    self.send_response(400)
                    self.end_headers()
                    return
                experiments = _find_experiments(output_dir)
                matched = next((e for e in experiments if e.name == exp_name), None)
                if matched is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                try:
                    data = _load_results(str(matched))
                    self.send_response(200)
                    self.send_header("Content-type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(data).encode())
                except Exception as e:
                    self.send_response(500)
                    self.send_header("Content-type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}).encode())
            else:
                self.send_error(404)

        def log_message(self, format, *args):
            pass  # Suppress request logs

    try:
        socketserver.TCPServer.allow_reuse_address = True
        with socketserver.TCPServer(("127.0.0.1", port), _ViewerHandler) as httpd:
            url = f"http://localhost:{port}"
            if _HAS_RICH:
                _console.print(f"\n[green]✓[/green] Results viewer running at: [cyan]{url}[/cyan]")
                _console.print("[dim]Press Ctrl+C to stop[/dim]\n")
            else:
                click.echo(f"\n✓ Results viewer running at: {url}")
                click.echo("Press Ctrl+C to stop\n")

            if not no_browser:
                threading.Timer(0.5, lambda: webbrowser.open(url)).start()

            def _shutdown(_sig, _frame):
                if _HAS_RICH:
                    _console.print("\n[yellow]Stopping server...[/yellow]")
                else:
                    click.echo("\nStopping server...")
                # shutdown() must run on a separate thread since serve_forever()
                # is blocking the main thread — it polls an internal flag that
                # shutdown() sets, but it can't poll while the signal handler
                # is executing on the same thread.
                threading.Thread(target=httpd.shutdown, daemon=True).start()

            signal.signal(signal.SIGINT, _shutdown)
            signal.signal(signal.SIGTERM, _shutdown)
            httpd.serve_forever()
            httpd.server_close()
    except OSError as e:
        if "Address already in use" in str(e):
            echo_error(f"Port {port} is already in use. Try: ev view --port {port + 1}")
            sys.exit(1)
        raise
