/* ============================================================
   Content: Architecture Overview & Engine Flow
   Populates #architecture and #engine-flow sections
   ============================================================ */

function initArchEngineContent() {

  // ────────────────────────────────────────────────────────────
  // SECTION 1 — Architecture Overview
  // ────────────────────────────────────────────────────────────
  var archEl = document.getElementById('architecture');
  if (archEl) {
    var archContent = [
      '<h2>Architecture Overview</h2>',
      '<p style="color:var(--text-secondary);margin-bottom:24px">',
      'A comprehensive tour of the <strong>azure-ai-evaluation</strong> engine &mdash; ',
      'directory layout, component registries, compute abstraction, and data model hierarchy.',
      '</p>',

      // ── 1.1 Directory Structure ──
      '<h3 id="dir-structure">Directory Structure</h3>',
      createInfoCard(
        'Source Root',
        'All paths below are relative to <code>azure/ai/evaluation/</code> inside the SDK package.',
        'info'
      ),

      createCodeBlock(
        'azure/ai/evaluation/_engine/\n' +
        '|\n' +
        '|-- runner.py                    # ExperimentRunner - backend selection & orchestration\n' +
        '|-- compute.py                   # ComputeBackend ABC, LocalComputeBackend\n' +
        '|-- foundry_compute.py           # FoundryComputeBackend - Azure AI Foundry remote\n' +
        '|-- datasets.py                  # JSONL / CSV dataset loaders\n' +
        '|-- dataset_factory.py           # DatasetFactory - registry-aware loader\n' +
        '|-- decorators.py                # @evaluator, @target, @dataset + registries\n' +
        '|-- discovery.py                 # AST-based component auto-discovery\n' +
        '|-- environment.py               # Virtualenv / env detection\n' +
        '|-- combination_utils.py         # Cartesian product of target args\n' +
        '|-- preflight.py                 # Pre-run validation checks\n' +
        '|-- progress_tracker.py          # Rich multi-bar progress UI\n' +
        '|\n' +
        '|-- models/\n' +
        '|   |-- config.py                # Config - YAML to Pydantic schema\n' +
        '|   |-- execution_context.py     # ExecutionContext - runtime state\n' +
        '|   |-- evaluation_output.py     # EvaluationOutput - per-record result\n' +
        '|   +-- inference_output.py      # InferenceOutput - target response\n' +
        '|\n' +
        '|-- evaluation/\n' +
        '|   |-- evaluator.py             # ModelEvaluator - main orchestrator\n' +
        '|   |-- evaluation_executor.py   # EvaluationExecutor - parallel ThreadPool\n' +
        '|   |-- evaluators_aggregator.py # EvaluatorsAggregator - score rollup\n' +
        '|   +-- output_formatter.py      # OutputFormatter - AITK / VS Code results\n' +
        '|\n' +
        '|-- targets/\n' +
        '|   |-- target_factory.py        # TargetFactory - creates + Cartesian combos\n' +
        '|   +-- target_mapping.py        # Input field mapping (dataset to target)\n' +
        '|\n' +
        '|-- logging/                     # Structured logging\n' +
        '|-- tracing/                     # OpenTelemetry integration\n' +
        '+-- cli/                         # Click CLI commands',
        'bash',
        { filePath: 'azure/ai/evaluation/_engine/', title: 'Engine Directory Tree' }
      ),

      createInfoCard(
        'Key Insight: _engine vs _evaluate',
        '<code>_engine/</code> is the <strong>new unified engine</strong> powering the <code>ev</code> CLI. ' +
        '<code>_evaluate/</code> is the legacy <code>evaluate()</code> Python API kept for backward compatibility. ' +
        'All new development happens in <code>_engine/</code>.',
        'tip'
      ),

      // ── 1.2 Component Registry Pattern ──
      '<h3 id="registry-pattern" style="margin-top:32px">Component Registry Pattern</h3>',
      '<p style="color:var(--text-secondary);margin-bottom:16px">',
      'The engine uses a <strong>decorator-based registry</strong> pattern. ',
      'Python files decorated with <code>@evaluator</code>, <code>@target</code>, or ',
      '<code>@dataset</code> are auto-discovered via AST scanning at startup, populating ',
      'three global registries. Downstream components look up entries by name.',
      '</p>',

      createFlowDiagram(
        'Component Registry -- Discovery and Lookup',
        [
          { id: 'py-files',    label: 'Project .py Files', subtitle: 'user code',      type: 'data',     col: 1, row: 0 },
          { id: 'ast-scanner', label: 'AST Scanner',       subtitle: 'discovery.py',   type: 'class',    col: 1, row: 1 },
          { id: 'dec-check',   label: 'Decorator Check',   subtitle: '@evaluator / @target / @dataset', type: 'function', col: 1, row: 2 },
          { id: 'eval-reg',    label: 'EVALUATOR_REGISTRY', subtitle: 'decorators.py', type: 'data',     col: 0, row: 3 },
          { id: 'target-reg',  label: 'TARGET_REGISTRY',   subtitle: 'decorators.py',  type: 'data',     col: 1, row: 3 },
          { id: 'dataset-reg', label: 'DATASET_REGISTRY',  subtitle: 'decorators.py',  type: 'data',     col: 2, row: 3 },
          { id: 'evaluator',   label: 'ModelEvaluator',    subtitle: 'evaluator.py',   type: 'class',    col: 1, row: 4 },
          { id: 'target-fac',  label: 'TargetFactory',     subtitle: 'target_factory.py', type: 'class',  col: 2, row: 4 }
        ],
        [
          { from: 'py-files',    to: 'ast-scanner',  label: 'scan' },
          { from: 'ast-scanner', to: 'dec-check',    label: 'parse AST' },
          { from: 'dec-check',   to: 'eval-reg',     label: '@evaluator' },
          { from: 'dec-check',   to: 'target-reg',   label: '@target' },
          { from: 'dec-check',   to: 'dataset-reg',  label: '@dataset' },
          { from: 'eval-reg',    to: 'evaluator',    label: 'lookup' },
          { from: 'target-reg',  to: 'target-fac',   label: 'lookup' },
          { from: 'target-fac',  to: 'evaluator',    label: 'provides targets' }
        ],
        { width: 680, height: 440 }
      ),

      createCodeBlock(
        'def discover_components(force: bool = False) -> None:\n' +
        '    """Discover and import all @evaluator, @target, @dataset decorated components.\n' +
        '\n' +
        '    Scans the current working directory for Python modules containing these\n' +
        '    decorators and imports them to populate the registries.\n' +
        '\n' +
        '    Args:\n' +
        '        force: If True, forces discovery even if directory was already scanned.\n' +
        '\n' +
        '    Skips: .venv, __pycache__, node_modules, .git, tests, build, dist, etc.\n' +
        '    """\n' +
        '    base_dir = Path.cwd()\n' +
        '\n' +
        '    if not force and base_dir in _DISCOVERED_DIRECTORIES:\n' +
        '        return\n' +
        '\n' +
        '    from .decorators import DATASET_REGISTRY, EVALUATOR_REGISTRY, TARGET_REGISTRY\n' +
        '\n' +
        '    _discover_in_directory(base_dir)\n' +
        '    _DISCOVERED_DIRECTORIES.add(base_dir)',
        'python',
        { filePath: '_engine/discovery.py', highlightLines: [1, 13, 15, 18, 20], title: 'AST-based Component Discovery' }
      ),

      createCodeBlock(
        'def _has_decorator_on_class(tree: ast.AST, target_decorators: Set[str]) -> bool:\n' +
        '    """Check if target decorators are applied to class definitions."""\n' +
        '    for node in ast.walk(tree):\n' +
        '        if isinstance(node, ast.ClassDef):\n' +
        '            for decorator in node.decorator_list:\n' +
        '                decorator_name = None\n' +
        '                if isinstance(decorator, ast.Name):\n' +
        '                    decorator_name = decorator.id\n' +
        '                elif isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name):\n' +
        '                    decorator_name = decorator.func.id\n' +
        '\n' +
        '                if decorator_name in target_decorators:\n' +
        '                    return True\n' +
        '    return False',
        'python',
        { filePath: '_engine/discovery.py', highlightLines: [3, 4, 7, 9, 13] }
      ),

      createInfoCard(
        'How discovery works',
        'The scanner <strong>first</strong> does a fast text search for <code>@evaluator</code> / <code>@target</code> / ' +
        '<code>@dataset</code> strings in each <code>.py</code> file. Only matching files are parsed with ' +
        '<code>ast.parse()</code>, keeping startup fast. Directories like <code>.venv</code>, <code>__pycache__</code>, ' +
        '<code>node_modules</code>, <code>.git</code> are excluded.',
        'tip'
      ),

      // ── 1.3 Compute Backend Abstraction ──
      '<h3 id="compute-backends" style="margin-top:32px">Compute Backend Abstraction</h3>',
      '<p style="color:var(--text-secondary);margin-bottom:16px">',
      'The <code>ExperimentRunner</code> selects a compute backend based on the ',
      '<code>remote_compute</code> flag and config. Both backends implement the same ',
      '<code>ComputeBackend.submit()</code> abstract interface, keeping the runner backend-agnostic.',
      '</p>',

      createFlowDiagram(
        'Compute Backend Selection',
        [
          { id: 'runner',    label: 'ExperimentRunner',     subtitle: 'runner.py',            type: 'class',    col: 1, row: 0 },
          { id: 'decision',  label: 'remote_compute?',      subtitle: 'True / False',         type: 'config',   col: 1, row: 1 },
          { id: 'local',     label: 'LocalComputeBackend',  subtitle: 'compute.py',           type: 'function', col: 0, row: 2 },
          { id: 'foundry',   label: 'FoundryComputeBackend', subtitle: 'foundry_compute.py', type: 'external', col: 2, row: 2 },
          { id: 'me',        label: 'ModelEvaluator',       subtitle: 'in-process execution', type: 'class',    col: 0, row: 3 },
          { id: 'azure',     label: 'Azure AI Foundry',     subtitle: 'cloud API',            type: 'external', col: 2, row: 3 }
        ],
        [
          { from: 'runner',   to: 'decision',  label: '_select_backend()' },
          { from: 'decision', to: 'local',     label: 'local (default)' },
          { from: 'decision', to: 'foundry',   label: 'remote + foundry_project' },
          { from: 'local',    to: 'me',        label: 'submit(context)' },
          { from: 'foundry',  to: 'azure',     label: 'submit(context)' }
        ],
        { width: 680, height: 380 }
      ),

      createCodeBlock(
        'class ComputeBackend(ABC):\n' +
        '    """Abstract base for compute backends."""\n' +
        '\n' +
        '    @abstractmethod\n' +
        '    def submit(self, context: RunContext, **kwargs: Any) -> JobInfo:\n' +
        '        """Submit an evaluation job. Returns JobInfo with status."""\n' +
        '        ...',
        'python',
        { filePath: '_engine/compute.py', highlightLines: [4, 5], title: 'ComputeBackend ABC' }
      ),

      createCodeBlock(
        'class LocalComputeBackend(ComputeBackend):\n' +
        '    """Run evaluation synchronously in the current process."""\n' +
        '\n' +
        '    def submit(self, context: RunContext, **kwargs: Any) -> JobInfo:\n' +
        '        try:\n' +
        '            from .evaluation.evaluator import ModelEvaluator\n' +
        '            evaluator = ModelEvaluator(\n' +
        '                config_path=context.config_path,\n' +
        '                model_filter=context.model_filter,\n' +
        '            )\n' +
        '            dataset = evaluator.load_dataset(dataset_path=context.dataset_path)\n' +
        '            result = evaluator.evaluate(dataset)\n' +
        '            return JobInfo(\n' +
        '                job_id="local",\n' +
        '                status=JobStatus.COMPLETED,\n' +
        '                metadata={"execution_type": "local", **result},\n' +
        '            )\n' +
        '        except Exception as e:\n' +
        '            return JobInfo(\n' +
        '                job_id="local", status=JobStatus.FAILED,\n' +
        '                metadata={"error": str(e)},\n' +
        '            )',
        'python',
        { filePath: '_engine/compute.py', highlightLines: [4, 7, 12, 13, 15], title: 'LocalComputeBackend' }
      ),

      createCodeBlock(
        'class FoundryComputeBackend(ComputeBackend):\n' +
        '    """Submit evaluation to Azure AI Foundry cloud compute."""\n' +
        '\n' +
        '    def __init__(self, project_endpoint: str) -> None:\n' +
        '        self._project_endpoint = project_endpoint\n' +
        '\n' +
        '    def submit(self, context: RunContext, **kwargs: Any) -> JobInfo:\n' +
        '        try:\n' +
        '            from .foundry_compute import run_remote_evaluation\n' +
        '            result = run_remote_evaluation(\n' +
        '                config_path=context.config_path,\n' +
        '                project_endpoint=self._project_endpoint,\n' +
        '                on_progress=kwargs.get("on_progress"),\n' +
        '            )\n' +
        '            status = JobStatus.COMPLETED if result.get("status") == "completed" else JobStatus.FAILED\n' +
        '            return JobInfo(job_id=result.get("run_id", "foundry"), status=status,\n' +
        '                           metadata={"execution_type": "foundry", **result})\n' +
        '        except Exception as e:\n' +
        '            return JobInfo(job_id="foundry", status=JobStatus.FAILED,\n' +
        '                           metadata={"error": str(e)})',
        'python',
        { filePath: '_engine/foundry_compute.py + compute.py', highlightLines: [4, 8, 11, 16], title: 'FoundryComputeBackend' }
      ),

      createTable(
        ['Backend', 'Class', 'File', 'Execution Model', 'Use Case'],
        [
          ['Local',   '<code>LocalComputeBackend</code>',   '<code>compute.py</code>',         'Synchronous, in-process',    'Development, CI/CD, local testing'],
          ['Foundry', '<code>FoundryComputeBackend</code>', '<code>compute.py</code>',  'Synchronous wait via Foundry API', 'Large-scale production evaluations']
        ]
      ),

      // ── 1.4 Data Model Hierarchy ──
      '<h3 id="data-model" style="margin-top:32px">Data Model Hierarchy</h3>',
      '<p style="color:var(--text-secondary);margin-bottom:16px">',
      'The YAML configuration is parsed into a typed Pydantic model hierarchy. ',
      'Understanding this hierarchy is key to grasping how the engine wires together targets, evaluators, and datasets.',
      '</p>',

      createCodeBlock(
        'class Config(BaseModel):\n' +
        '    """Root configuration with YAML loading support."""\n' +
        '\n' +
        '    model_config = ConfigDict(extra="allow")\n' +
        '\n' +
        '    experiment: ExperimentConfig\n' +
        '\n' +
        '    @classmethod\n' +
        '    def from_yaml(cls, path: str) -> "Config":\n' +
        '        """Load configuration from YAML with env var interpolation."""\n' +
        '        with open(path) as f:\n' +
        '            data = yaml.safe_load(f)\n' +
        '        if data is None:\n' +
        '            raise ValueError(f"Configuration file \'{path}\' is empty")\n' +
        '        data = _interpolate_env_vars(data)\n' +
        '        return cls(**data)\n' +
        '\n' +
        'class ExperimentConfig(BaseModel):\n' +
        '    """Experiment configuration."""\n' +
        '\n' +
        '    model_config = ConfigDict(extra="allow")\n' +
        '\n' +
        '    name: str\n' +
        '    version: str = "1.0"\n' +
        '    description: str = ""\n' +
        '    output_path: str = "output"\n' +
        '    max_workers: Optional[int] = None\n' +
        '    targets: List[TargetVariantConfig] = Field(default_factory=list)\n' +
        '    dataset: Optional[DatasetConfig] = None\n' +
        '    evaluators: List[EvaluatorConfig] = Field(default_factory=list)\n' +
        '    compute: Optional[ComputeConfig] = None\n' +
        '    cloud: Optional[CloudConfig] = None   # Azure AI cloud settings\n' +
        '    connections: Any = Field(default_factory=list)',
        'python',
        { filePath: '_engine/models/config.py', highlightLines: [7, 10, 16, 24, 28, 30, 33], title: 'Config Pydantic Model' }
      ),

      createCodeBlock(
        '@dataclass\n' +
        'class EvaluationOutput:\n' +
        '    """Output of a model evaluation process."""\n' +
        '\n' +
        '    run_id: str\n' +
        '    inference_output: InferenceOutput\n' +
        '    evaluators: Dict[str, Dict[str, Any]]     # evaluator_name -> scores dict\n' +
        '    system_evaluators: Dict[str, Dict[str, Any]]  # e.g. response_time\n' +
        '    model_display_name: str\n' +
        '    metadata: Dict[str, Any]\n' +
        '    results: List[EvaluatorResult] = field(default_factory=list)\n' +
        '\n' +
        '@dataclass\n' +
        'class InferenceOutput:\n' +
        '    """Output of a model inference process."""\n' +
        '\n' +
        '    output: Any                               # raw target response\n' +
        '    model_name: str\n' +
        '    record: Dict[str, Any]                    # original dataset record\n' +
        '    args: Dict[str, Any]                      # target variant args\n' +
        '    agent_trace: Any = None                   # OTel AgentTrace if available',
        'python',
        { filePath: '_engine/models/evaluation_output.py + inference_output.py', highlightLines: [1, 5, 7, 14, 17, 21] }
      ),

      createTable(
        ['Model', 'File', 'Purpose'],
        [
          ['<code>Config</code>',            '<code>models/config.py</code>',            'Root YAML config; holds ExperimentConfig (no cloud at root level)'],
          ['<code>ExperimentConfig</code>',   '<code>models/config.py</code>',            'name, version, targets, evaluators, dataset, max_workers, output_path, cloud, compute, connections'],
          ['<code>ExecutionContext</code>',    '<code>models/execution_context.py</code>', 'Frozen dataclass: connections_registry, cloud_config, experiment_name/version, experiment_dir, output_path'],
          ['<code>EvaluationOutput</code>',   '<code>models/evaluation_output.py</code>', 'Dataclass: run_id, inference_output, evaluators dict, system_evaluators, model_display_name, metadata'],
          ['<code>InferenceOutput</code>',    '<code>models/inference_output.py</code>',  'Dataclass: output (Any), model_name, record, args, agent_trace'],
          ['<code>EvaluatorResult</code>',    '<code>models/evaluation_output.py</code>', 'Dataclass: name, score, label, reason, threshold, passed, details (Foundry-compatible)']
        ]
      ),

      // ── 1.5 Data Flow Overview ──
      '<h3 id="data-flow" style="margin-top:32px">Data Flow Overview</h3>',
      '<p style="color:var(--text-secondary);margin-bottom:16px">',
      'The complete lifecycle from CLI invocation to aggregated results output. ',
      'Every actor below is a real class or module in the engine.',
      '</p>',

      createSequenceDiagram(
        'End-to-End Data Flow',
        [
          { id: 'cli',        label: 'CLI',            type: 'engine' },
          { id: 'srunner',    label: 'Runner',         type: 'engine' },
          { id: 'config',     label: 'Config',         type: 'config' },
          { id: 'discovery',  label: 'Discovery',      type: 'engine' },
          { id: 'model-eval', label: 'ModelEvaluator', type: 'engine' },
          { id: 'executor',   label: 'Executor',       type: 'engine' },
          { id: 'starget',    label: 'Target',         type: 'target' },
          { id: 'sevaluator', label: 'Evaluator',      type: 'evaluator' },
          { id: 'aggregator', label: 'Aggregator',     type: 'data' },
          { id: 'output',     label: 'Output',         type: 'data' }
        ],
        [
          { from: 'cli',        to: 'srunner',    label: 'ev run config.yaml' },
          { from: 'srunner',    to: 'config',     label: 'Config.from_yaml()' },
          { from: 'config',     to: 'srunner',    label: 'parsed Config',             type: 'return' },
          { from: 'srunner',    to: 'discovery',  label: 'discover_components()' },
          { from: 'discovery',  to: 'srunner',    label: 'registries populated',      type: 'return' },
          { from: 'srunner',    to: 'model-eval', label: 'LocalBackend.submit(ctx)' },
          { from: 'model-eval', to: 'model-eval', label: 'load_dataset()' },
          { from: 'model-eval', to: 'executor',   label: 'evaluate_all_parallel()' },
          { from: 'executor',   to: 'starget',    label: 'target.infer(record)' },
          { from: 'starget',    to: 'executor',   label: 'InferenceOutput',            type: 'return' },
          { from: 'executor',   to: 'sevaluator', label: 'evaluator.compute(record)' },
          { from: 'sevaluator', to: 'executor',   label: 'scores Dict[str, float]',    type: 'return' },
          { from: 'executor',   to: 'executor',   label: 'save JSONL line' },
          { from: 'executor',   to: 'aggregator', label: 'analyze_results(jsonl_path)' },
          { from: 'aggregator', to: 'output',     label: 'persist_aitk_sidebar_results()' },
          { from: 'output',     to: 'cli',        label: 'summary table / AITK sidebar', type: 'return' }
        ]
      ),

      createInfoCard(
        'Streaming JSONL Output',
        'Results are streamed as JSONL (one JSON object per line per record). This allows <strong>incremental progress</strong> ' +
        '-- partial results are available even if the run is interrupted. The aggregator reads the JSONL file at the end to compute final scores.',
        'info'
      ),

      createTable(
        ['Component', 'Module', 'Responsibility'],
        [
          ['<code>ExperimentRunner</code>',    '<code>runner.py</code>',                           'Top-level orchestrator; selects compute backend, loads .env, delegates'],
          ['<code>Config</code>',              '<code>models/config.py</code>',                    'Pydantic model; parses YAML into typed experiment configuration'],
          ['<code>discover_components</code>', '<code>discovery.py</code>',                        'AST scanner; finds decorated classes and populates registries'],
          ['<code>ModelEvaluator</code>',      '<code>evaluation/evaluator.py</code>',             'Main orchestrator; loads dataset, builds registries, kicks off execution'],
          ['<code>EvaluationExecutor</code>',  '<code>evaluation/evaluation_executor.py</code>',   'Parallel execution; per-target outer threads, per-record inner pool'],
          ['<code>TargetFactory</code>',       '<code>targets/target_factory.py</code>',           'Creates target instances; handles Cartesian argument expansion'],
          ['<code>EvaluatorsAggregator</code>','<code>evaluation/evaluators_aggregator.py</code>', 'Reads JSONL results, delegates to evaluator.aggregate(), produces AggregatedEvaluators'],
          ['<code>OutputFormatter</code>',     '<code>evaluation/output_formatter.py</code>',      'persist_aitk_sidebar_results() and persist_aitk_job_artifacts() for AITK + local dir'],
          ['<code>OTelTraceCapture</code>',    '<code>tracing/otel_trace_capture.py</code>',       'Captures OpenTelemetry spans during inference for tool-call extraction']
        ]
      )
    ].join('\n');

    archEl.innerHTML = archContent;
  }

  // ────────────────────────────────────────────────────────────
  // SECTION 2 — Engine Flow
  // ────────────────────────────────────────────────────────────
  var engineEl = document.getElementById('engine-flow');
  if (engineEl) {
    var engineContent = [
      '<h2>Engine Flow</h2>',
      '<p style="color:var(--text-secondary);margin-bottom:24px">',
      'Step-by-step walkthrough of the complete evaluation pipeline &mdash; ',
      'from <code>ev run</code> on the command line to aggregated metric output. ',
      'Each step shows the actual function signature and source file.',
      '</p>',

      // ── 2.1 Complete Call Trace ──
      '<h3 id="call-trace">Complete Call Trace</h3>',
      '<p style="color:var(--text-secondary);margin-bottom:16px">',
      'The full chain of function calls from CLI entrypoint to final output. ',
      'Click <strong>Expand All</strong> to see code and details for every step.',
      '</p>',

      createCallTrace(
        'ev run -- Full Execution Pipeline',
        [
          {
            module: 'cli/__init__.py',
            func: 'main()',
            file: '_engine/cli/__init__.py',
            tag: 'cli',
            detail:
              '<p>Top-level entrypoint invoked by the <code>ev</code> console script.</p>' +
              '<ul>' +
              '<li>Checks <code>--plain</code> flag to disable Rich formatting</li>' +
              '<li>Detects execution mode (direct vs. project environment delegation)</li>' +
              '<li>Delegates to project venv if needed, then calls <code>cli()</code> Click group</li>' +
              '</ul>' +
              createCodeBlock(
                'def main():\n' +
                '    """Entry point for the ``ev`` CLI."""\n' +
                '    if "--plain" in sys.argv:\n' +
                '        os.environ["EV_DISABLE_RICH_LOGGING"] = "true"\n' +
                '\n' +
                '    execution_mode = os.environ.get("EV_EXECUTION_MODE")\n' +
                '\n' +
                '    if execution_mode == "direct":\n' +
                '        cli()  # Already in project env\n' +
                '    elif _should_delegate_to_project_env():\n' +
                '        _execute_in_project_env()  # Re-exec in project venv\n' +
                '        cli()  # Fallback if delegation skipped\n' +
                '    else:\n' +
                '        cli()',
                'python', { filePath: '_engine/cli/__init__.py' }
              )
          },
          {
            module: 'cli/__init__.py',
            func: 'cli() group',
            file: '_engine/cli/__init__.py',
            tag: 'cli',
            detail:
              '<p>Click command group that dispatches to sub-commands:</p>' +
              '<ul>' +
              '<li><code>ev run</code> -- Execute an evaluation experiment</li>' +
              '<li><code>ev new</code> -- Scaffold a new project config</li>' +
              '<li><code>ev validate</code> -- Validate config against registries</li>' +
              '<li><code>ev discover</code> -- List discovered components</li>' +
              '<li><code>ev view</code> -- View evaluation results</li>' +
              '<li>Plus: <code>clear</code>, <code>cloud</code>, <code>target</code>, <code>evaluator</code>, <code>dataset</code></li>' +
              '</ul>' +
              createCodeBlock(
                '@click.group(invoke_without_command=True, cls=OrderedGroup)\n' +
                '@click.version_option(version="2.0.0a1", prog_name="ev")\n' +
                '@click.pass_context\n' +
                'def cli(ctx):\n' +
                '    """Azure AI Evaluation — local-first evaluation toolkit."""\n' +
                '    if ctx.invoked_subcommand is None:\n' +
                '        click.echo(ctx.get_help())\n' +
                '\n' +
                'cli.add_command(run)\n' +
                'cli.add_command(new)\n' +
                'cli.add_command(validate)\n' +
                'cli.add_command(discover)\n' +
                'cli.add_command(view)\n' +
                'cli.add_command(clear)\n' +
                'cli.add_command(cloud)\n' +
                'cli.add_command(target_cmd, name="target")\n' +
                'cli.add_command(evaluator)\n' +
                'cli.add_command(dataset)',
                'python', { filePath: '_engine/cli/__init__.py' }
              )
          },
          {
            module: 'cli/commands/run.py',
            func: 'run(config, env, dataset, remote, model)',
            file: '_engine/cli/commands/run.py',
            tag: 'cli',
            detail:
              '<p>The <code>ev run</code> sub-command. Parses CLI options, auto-detects ' +
              '<code>config.yaml</code> if not specified, and delegates to <code>ExperimentRunner</code>.</p>' +
              '<ul>' +
              '<li>Accepts <code>--path/-p</code>, <code>--config/-c</code>, <code>--dataset/-d</code>, <code>--env/-e</code>, <code>--remote/-r</code>, <code>--targets/-t</code></li>' +
              '<li>Also: <code>--auto-approve/-y</code>, <code>--output/-o</code>, <code>--trace/--no-trace</code>, <code>--trace-endpoint</code></li>' +
              '<li>Calls <code>import_local_components()</code> to discover user components</li>' +
              '<li>Delegates to <code>ExperimentRunner.run()</code></li>' +
              '</ul>' +
              createCodeBlock(
                '@click.command()\n' +
                '@click.option("--path", "-p", default=".", type=click.Path(exists=True))\n' +
                '@click.option("--config", "-c", default=None)\n' +
                '@click.option("--dataset", "-d", "dataset_path", default=None)\n' +
                '@click.option("--env", "-e", default=".env")\n' +
                '@click.option("--remote", "-r", is_flag=True)\n' +
                '@click.option("--targets", "-t", default=None)\n' +
                '@click.option("--auto-approve", "-y", is_flag=True)\n' +
                '@click.option("--output", "-o", default=None)\n' +
                '@click.option("--trace/--no-trace", default=None)\n' +
                'def run(path, config, dataset_path, env, remote,\n' +
                '        targets, auto_approve, output, trace, ...):\n' +
                '    runner = ExperimentRunner()\n' +
                '    job_info = runner.run(\n' +
                '        config_path=config_path,\n' +
                '        env_path=env_path,\n' +
                '        dataset_path=dataset_path,\n' +
                '        remote_compute=remote,\n' +
                '        model_filter=model_filter,\n' +
                '    )',
                'python', { filePath: '_engine/cli/commands/run.py', highlightLines: [11, 13, 14, 15] }
              )
          },
          {
            module: 'runner.py',
            func: 'ExperimentRunner.run(config_path, env_path, dataset_path, remote_compute, model_filter) -> JobInfo',
            file: '_engine/runner.py',
            tag: 'engine',
            detail:
              '<p>Top-level orchestrator. Loads config, selects compute backend, delegates execution.</p>' +
              '<ul>' +
              '<li>Loads <code>.env</code> file if provided (via <code>python-dotenv</code>)</li>' +
              '<li>Parses YAML config via <code>Config.from_yaml()</code></li>' +
              '<li>Calls <code>_select_backend()</code> to choose Local or Foundry</li>' +
              '<li>Builds <code>RunContext</code> dataclass with all run parameters</li>' +
              '<li>Calls <code>backend.submit(context)</code> and returns <code>JobInfo</code></li>' +
              '</ul>' +
              createCodeBlock(
                'class ExperimentRunner:\n' +
                '    def run(\n' +
                '        self,\n' +
                '        config_path: str,\n' +
                '        env_path: Optional[str] = None,\n' +
                '        dataset_path: Optional[str] = None,\n' +
                '        remote_compute: bool = False,\n' +
                '        model_filter: Optional[List[str]] = None,\n' +
                '        **kwargs,\n' +
                '    ) -> JobInfo:\n' +
                '        config = Config.from_yaml(config_path)\n' +
                '        backend = self._select_backend(config, remote_compute)\n' +
                '        context = RunContext(\n' +
                '            config_path=config_path,\n' +
                '            env_path=env_path,\n' +
                '            dataset_path=dataset_path,\n' +
                '            model_filter=model_filter,\n' +
                '        )\n' +
                '        return backend.submit(context)',
                'python', { filePath: '_engine/runner.py', highlightLines: [2, 10, 11, 12, 19] }
              )
          },
          {
            module: 'runner.py',
            func: '_select_backend(config, remote_compute) -> ComputeBackend',
            file: '_engine/runner.py',
            tag: 'engine',
            detail:
              '<p>Decides which backend to use based on flags and config.</p>' +
              createCodeBlock(
                'def _select_backend(self, config: Config, remote_compute: bool) -> ComputeBackend:\n' +
                '    cloud_config = getattr(config.experiment, "cloud", None)\n' +
                '\n' +
                '    if remote_compute:\n' +
                '        endpoint = None\n' +
                '        # Prefer cloud_config (new canonical location)\n' +
                '        if cloud_config and cloud_config.foundry_project:\n' +
                '            endpoint = cloud_config.foundry_project\n' +
                '        # Legacy fallback: compute block\n' +
                '        if not endpoint:\n' +
                '            compute_config = getattr(config.experiment, "compute", None)\n' +
                '            if compute_config:\n' +
                '                endpoint = compute_config.azure_ai_project\n' +
                '        if endpoint:\n' +
                '            return FoundryComputeBackend(project_endpoint=endpoint)\n' +
                '        raise ValueError("Remote compute requested but no project endpoint configured.")\n' +
                '\n' +
                '    return LocalComputeBackend()',
                'python', { filePath: '_engine/runner.py', highlightLines: [2, 4, 7, 15, 19] }
              )
          },
          {
            module: 'compute.py',
            func: 'LocalComputeBackend.submit(context) -> JobInfo',
            file: '_engine/compute.py',
            tag: 'engine',
            detail:
              '<p>Executes the evaluation synchronously in-process. This is the default path.</p>' +
              '<ul>' +
              '<li>Instantiates <code>ModelEvaluator</code> with config_path and model_filter</li>' +
              '<li>Loads the dataset via <code>evaluator.load_dataset()</code></li>' +
              '<li>Calls <code>evaluator.evaluate(dataset)</code> -- the core pipeline</li>' +
              '<li>Returns <code>JobInfo</code> with COMPLETED or FAILED status</li>' +
              '</ul>' +
              createCodeBlock(
                'class LocalComputeBackend(ComputeBackend):\n' +
                '    def submit(self, context: RunContext, **kwargs) -> JobInfo:\n' +
                '        try:\n' +
                '            evaluator = ModelEvaluator(\n' +
                '                config_path=context.config_path,\n' +
                '                model_filter=context.model_filter,\n' +
                '            )\n' +
                '            dataset = evaluator.load_dataset(dataset_path=context.dataset_path)\n' +
                '            result = evaluator.evaluate(dataset)\n' +
                '            return JobInfo(\n' +
                '                job_id="local", status=JobStatus.COMPLETED,\n' +
                '                metadata={"execution_type": "local", **result},\n' +
                '            )\n' +
                '        except Exception as e:\n' +
                '            return JobInfo(job_id="local", status=JobStatus.FAILED,\n' +
                '                           metadata={"error": str(e)})',
                'python', { filePath: '_engine/compute.py', highlightLines: [2, 4, 8, 9, 10] }
              )
          },
          {
            module: 'evaluation/evaluator.py',
            func: 'ModelEvaluator.__init__(config_path, model_filter)',
            file: '_engine/evaluation/evaluator.py',
            tag: 'evaluator',
            detail:
              '<p>Initializes the evaluation orchestrator. Performs all setup before execution.</p>' +
              '<ul>' +
              '<li>Calls <code>discover_components()</code> for AST registries (no args &mdash; uses cwd)</li>' +
              '<li>Parses config via <code>Config.from_yaml()</code></li>' +
              '<li>Sets up OTel tracing, logging, output formatter, connections</li>' +
              '<li>Registers targets via <code>self._register_targets(model_filter)</code></li>' +
              '<li>Registers evaluators via <code>self._register_evaluators()</code></li>' +
              '</ul>' +
              createCodeBlock(
                'class ModelEvaluator:\n' +
                '    def __init__(\n' +
                '        self,\n' +
                '        config_path: str = "config.yaml",\n' +
                '        load_config_only: bool = False,\n' +
                '        model_filter: Optional[List[str]] = None,\n' +
                '    ) -> None:\n' +
                '        self.model_filter = model_filter\n' +
                '        discover_components()  # no args — uses Path.cwd()\n' +
                '        self.config = Config.from_yaml(config_path)\n' +
                '        self._trace_capture = self._setup_tracing()\n' +
                '\n' +
                '        if load_config_only:\n' +
                '            return\n' +
                '\n' +
                '        self._output = self._setup_output_formatter()\n' +
                '        self.connections_registry = self._build_connections_registry()\n' +
                '        self.execution_context = self._build_execution_context()\n' +
                '        self.targets_registry = self._register_targets(model_filter)\n' +
                '        self.evaluators_registry: Dict[str, Any] = {}\n' +
                '        self._register_evaluators()',
                'python', { filePath: '_engine/evaluation/evaluator.py', highlightLines: [2, 5, 9, 10, 19, 21] }
              )
          },
          {
            module: 'evaluation/evaluator.py',
            func: 'ModelEvaluator.load_dataset(dataset_config, dataset_path) -> BaseDataset',
            file: '_engine/evaluation/evaluator.py',
            tag: 'evaluator',
            detail:
              '<p>Loads the evaluation dataset via <code>DatasetFactory</code>.</p>' +
              '<ul>' +
              '<li>If <code>dataset_path</code> is provided, uses it as override</li>' +
              '<li>Otherwise falls back to <code>config.experiment.dataset</code></li>' +
              '<li>Delegates to <code>DatasetFactory().create_from_config()</code> for registry-aware loading</li>' +
              '<li>Returns a <code>BaseDataset</code> instance (iterable)</li>' +
              '</ul>' +
              createCodeBlock(
                'def load_dataset(\n' +
                '    self,\n' +
                '    dataset_config: Optional[DatasetConfig] = None,\n' +
                '    dataset_path: Optional[str] = None,\n' +
                ') -> BaseDataset:\n' +
                '    if dataset_config is None:\n' +
                '        dataset_config = self.config.experiment.dataset\n' +
                '        if dataset_config is None:\n' +
                '            raise ValueError("Dataset configuration required")\n' +
                '\n' +
                '    factory = DatasetFactory()\n' +
                '    return factory.create_from_config(\n' +
                '        dataset_config,\n' +
                '        dataset_path_override=dataset_path,\n' +
                '        context=self.execution_context,\n' +
                '    )',
                'python', { filePath: '_engine/evaluation/evaluator.py', highlightLines: [1, 5, 11, 12] }
              )
          },
          {
            module: 'evaluation/evaluator.py',
            func: 'ModelEvaluator.evaluate(dataset) -> Dict[str, Any]',
            file: '_engine/evaluation/evaluator.py',
            tag: 'evaluator',
            detail:
              '<p>Main evaluation entry point. Orchestrates execution, aggregation, and output.</p>' +
              '<ul>' +
              '<li>Creates <code>EvaluationExecutor</code> with evaluators_registry, trace_capture, experiment_dir</li>' +
              '<li>Calls <code>_run_evaluation()</code> which dispatches to parallel or sequential paths</li>' +
              '<li>Aggregation happens inside the executor via <code>EvaluatorsAggregator</code></li>' +
              '<li>Writes output via <code>_persist_outputs()</code> (AITK sidebar + job artifacts)</li>' +
              '</ul>' +
              createCodeBlock(
                'def evaluate(self, dataset: BaseDataset) -> Dict[str, Any]:\n' +
                '    self._suppress_noisy_loggers()\n' +
                '\n' +
                '    executor = self._create_executor()\n' +
                '    # _create_executor returns EvaluationExecutor(\n' +
                '    #     evaluators_registry=self.evaluators_registry,\n' +
                '    #     trace_capture=self._trace_capture,\n' +
                '    #     experiment_dir=self._current_experiment_dir,\n' +
                '    # )\n' +
                '\n' +
                '    failed_records, first_error_msg = self._run_evaluation(executor, dataset)\n' +
                '    # Multi-target: executor.evaluate_all_parallel(targets, dataset, max_workers)\n' +
                '    # Single-target: executor.evaluate_model(dataset, name, data, path, max_workers)\n' +
                '\n' +
                '    summary = self._build_summary(dataset, failed_records, first_error_msg)\n' +
                '    self._persist_outputs(summary)  # AITK sidebar + job artifacts\n' +
                '    self._cleanup()                 # shutdown OTel\n' +
                '    return summary',
                'python', { filePath: '_engine/evaluation/evaluator.py', highlightLines: [1, 4, 11, 15, 16] }
              )
          },
          {
            module: 'evaluation/evaluation_executor.py',
            func: 'EvaluationExecutor.evaluate_all_parallel(targets_registry, dataset, max_workers) -> Tuple[int, Optional[str]]',
            file: '_engine/evaluation/evaluation_executor.py',
            tag: 'engine',
            detail:
              '<p>Parallel execution across target variants with a shared multi-bar progress display.</p>' +
              '<ul>' +
              '<li>Materializes dataset once, shares across all variants</li>' +
              '<li>Outer <code>ThreadPoolExecutor</code>: one thread per variant</li>' +
              '<li>Each thread calls <code>_execute_single_variant()</code></li>' +
              '<li>Returns <code>(total_failed, first_error_msg)</code> tuple</li>' +
              '</ul>' +
              createCodeBlock(
                'def evaluate_all_parallel(\n' +
                '    self,\n' +
                '    targets_registry: Dict[str, Any],\n' +
                '    dataset: Any,\n' +
                '    max_workers: int,\n' +
                ') -> tuple:\n' +
                '    """Evaluate all target variants in parallel.\n' +
                '    Returns (total_failed, first_error_msg) tuple.\n' +
                '    """\n' +
                '    records = list(dataset)  # materialize once\n' +
                '    variant_items = [\n' +
                '        (name, data, self._experiment_dir / f"{name}_results.jsonl")\n' +
                '        for name, data in targets_registry.items()\n' +
                '    ]\n' +
                '\n' +
                '    with ThreadPoolExecutor(max_workers=len(variant_items)) as outer_pool:\n' +
                '        futures = {\n' +
                '            outer_pool.submit(\n' +
                '                self._execute_single_variant,\n' +
                '                name, data, path, records, max_workers, lock\n' +
                '            ): name\n' +
                '            for name, data, path in variant_items\n' +
                '        }',
                'python', { filePath: '_engine/evaluation/evaluation_executor.py', highlightLines: [1, 6, 10, 16, 19, 20] }
              )
          },
          {
            module: 'evaluation/evaluation_executor.py',
            func: '_execute_single_variant(model_name, model_data, output_path, records, max_workers, lock) -> Tuple[int, Optional[str]]',
            file: '_engine/evaluation/evaluation_executor.py',
            tag: 'engine',
            detail:
              '<p>Processes all records for one target variant via inner thread pool.</p>' +
              '<ul>' +
              '<li>Inner <code>ThreadPoolExecutor(max_workers)</code> from config</li>' +
              '<li>Submits <code>evaluate_record()</code> for each record</li>' +
              '<li>Streams results to JSONL via <code>_save_result()</code></li>' +
              '<li>Runs <code>_aggregate_and_save_evaluators()</code> at the end</li>' +
              '</ul>' +
              createCodeBlock(
                'def _execute_single_variant(\n' +
                '    self,\n' +
                '    model_name: str,\n' +
                '    model_data: Dict[str, Any],\n' +
                '    output_path: Path,\n' +
                '    records: List[Dict[str, Any]],\n' +
                '    max_workers: int,\n' +
                '    lock: Any,\n' +
                '    on_advance: Any = None,\n' +
                ') -> Tuple[int, Optional[str]]:\n' +
                '    model_instance = model_data["model"]\n' +
                '    model_args = model_data["args"]\n' +
                '\n' +
                '    with ThreadPoolExecutor(max_workers=max_workers) as executor:\n' +
                '        futures = [\n' +
                '            executor.submit(\n' +
                '                contextvars.copy_context().run,\n' +
                '                self.evaluate_record, record, run_id,\n' +
                '                model_config_name, model_name, model_instance,\n' +
                '                **model_args,\n' +
                '            )\n' +
                '            for record in records\n' +
                '        ]\n' +
                '        for future in as_completed(futures):\n' +
                '            eval_output = future.result()\n' +
                '            self._save_result(eval_output, output_path)\n' +
                '\n' +
                '    self._aggregate_and_save_evaluators(output_path, model_name)\n' +
                '    return variant_failed, first_error',
                'python', { filePath: '_engine/evaluation/evaluation_executor.py', highlightLines: [1, 10, 14, 17, 26, 28] }
              )
          },
          {
            module: 'evaluation/evaluation_executor.py',
            func: 'evaluate_record(record, run_id, model_name, model_display_name, model, **kwargs) -> EvaluationOutput',
            file: '_engine/evaluation/evaluation_executor.py',
            tag: 'evaluator',
            detail:
              '<p>Innermost unit of work. Runs one record through target + all evaluators.</p>' +
              '<ul>' +
              '<li>Step 1: <code>_apply_target_input_mapping(record, target_mapping)</code></li>' +
              '<li>Step 2: <code>_run_inference(model, mapped_input)</code> with OTel tracing</li>' +
              '<li>Step 3: <code>_enrich_output_from_trace()</code> — extract tool_calls/tool_definitions</li>' +
              '<li>Step 4: <code>_compute_evaluators(inference_output)</code></li>' +
              '<li>Step 5: Assemble <code>EvaluationOutput</code></li>' +
              '<li>Catches exceptions per-record to avoid blocking the run</li>' +
              '</ul>' +
              createCodeBlock(
                'def evaluate_record(\n' +
                '    self,\n' +
                '    record: Dict[str, Any],\n' +
                '    run_id: str,\n' +
                '    model_name: str,\n' +
                '    model_display_name: str,\n' +
                '    model: Any,\n' +
                '    target_mapping: Optional[Dict[str, str]] = None,\n' +
                '    **kwargs: Any,\n' +
                ') -> EvaluationOutput:\n' +
                '    mapped_input = _apply_target_input_mapping(record, target_mapping or {})\n' +
                '    model_output, agent_trace, response_time_ms = self._run_inference(\n' +
                '        model, mapped_input, model_name, record_id,\n' +
                '    )\n' +
                '    # Enrich output with trace data (tool_calls, tool_definitions)\n' +
                '    if isinstance(model_output, dict):\n' +
                '        self._enrich_output_from_trace(model_output, agent_trace)\n' +
                '\n' +
                '    inference_output = self._build_inference_output(\n' +
                '        model_output, model_name, record, kwargs, agent_trace,\n' +
                '    )\n' +
                '    evaluator_results = self._compute_evaluators(inference_output)\n' +
                '    system_metrics = self._build_system_metrics(response_time_ms, agent_trace)\n' +
                '\n' +
                '    return EvaluationOutput(\n' +
                '        run_id=run_id,\n' +
                '        inference_output=inference_output,\n' +
                '        evaluators=evaluator_results,\n' +
                '        system_evaluators=system_metrics,\n' +
                '        model_display_name=model_display_name,\n' +
                '        metadata={},\n' +
                '    )',
                'python', { filePath: '_engine/evaluation/evaluation_executor.py', highlightLines: [1, 10, 11, 12, 19, 22, 25] }
              )
          },
          {
            module: 'evaluation/evaluators_aggregator.py',
            func: 'EvaluatorsAggregator.analyze_results(results_path) -> AggregatedEvaluators',
            file: '_engine/evaluation/evaluators_aggregator.py',
            tag: 'evaluator',
            detail:
              '<p>Aggregates per-record scores from JSONL into summary metrics.</p>' +
              '<ul>' +
              '<li>Instance method — requires <code>evaluator_registry</code> in constructor</li>' +
              '<li>Reads JSONL file line by line</li>' +
              '<li>Delegates to each evaluator\'s own <code>.aggregate()</code> method</li>' +
              '<li>Returns <code>AggregatedEvaluators</code> dataclass with prefixed metric names</li>' +
              '</ul>' +
              createCodeBlock(
                'class EvaluatorsAggregator:\n' +
                '    def __init__(self, evaluator_registry: Dict[str, BaseEvaluator]) -> None:\n' +
                '        self.evaluator_registry = evaluator_registry\n' +
                '\n' +
                '    def analyze_results(self, results_path: Path) -> AggregatedEvaluators:\n' +
                '        """Aggregate evaluator scores from a JSONL results file."""\n' +
                '        evaluator_scores: Dict[str, List] = defaultdict(list)\n' +
                '        with open(results_path) as fh:\n' +
                '            for line in fh:\n' +
                '                record = json.loads(line)\n' +
                '                for name, scores in record.get("evaluators", {}).items():\n' +
                '                    evaluator_scores[name].append(scores)\n' +
                '\n' +
                '        # Delegate to each evaluator\'s aggregate() method\n' +
                '        for name, scores_list in evaluator_scores.items():\n' +
                '            evaluator = self.evaluator_registry[name]\n' +
                '            aggregated = evaluator.aggregate(scores_list)\n' +
                '\n' +
                '        return AggregatedEvaluators(run_id=run_id,\n' +
                '                                    aggregated_evaluators=all_evaluators)',
                'python', { filePath: '_engine/evaluation/evaluators_aggregator.py', highlightLines: [2, 5, 11, 15, 17] }
              )
          },
          {
            module: 'evaluation/output_formatter.py',
            func: 'OutputFormatter.persist_aitk_sidebar_results() / persist_aitk_job_artifacts()',
            file: '_engine/evaluation/output_formatter.py',
            tag: 'engine',
            detail:
              '<p>Formats and persists results to multiple output locations.</p>' +
              '<ul>' +
              '<li><code>persist_aitk_sidebar_results()</code> — writes flat rows JSON to <code>test-results/</code> for VS Code Data Viewer</li>' +
              '<li><code>persist_aitk_job_artifacts()</code> — copies experiment dir to <code>AITK_EVALS_JOBS_DIR</code> if set</li>' +
              '<li>Both are called from <code>ModelEvaluator._persist_outputs(summary)</code></li>' +
              '</ul>'
          }
        ]
      ),

      // ── 2.2 Two-Level Threading Model ──
      '<h3 id="threading-model" style="margin-top:32px">Two-Level Threading Model</h3>',
      '<p style="color:var(--text-secondary);margin-bottom:16px">',
      'When multiple targets are configured, the engine uses a nested threading strategy. ',
      'With a single target, only one level of parallelism is used (<code>evaluate_model()</code> path). ',
      'Understanding this model is critical for performance tuning via <code>max_workers</code>.',
      '</p>',

      createFlowDiagram(
        'Two-Level Thread Pool Architecture',
        [
          { id: 'eval-all',   label: 'evaluate_all_parallel', subtitle: 'entry point',          type: 'class',    col: 1, row: 0 },
          { id: 'outer-pool', label: 'Outer ThreadPool',      subtitle: '1 thread per variant', type: 'function', col: 1, row: 1 },
          { id: 'var-a',      label: 'Variant A',             subtitle: 'gpt-4o, temp=0.7',     type: 'config',   col: 0, row: 2 },
          { id: 'var-b',      label: 'Variant B',             subtitle: 'gpt-4o-mini, temp=0',  type: 'config',   col: 2, row: 2 },
          { id: 'inner-a',    label: 'Inner ThreadPool',      subtitle: 'max_workers records',   type: 'function', col: 0, row: 3 },
          { id: 'inner-b',    label: 'Inner ThreadPool',      subtitle: 'max_workers records',   type: 'function', col: 2, row: 3 },
          { id: 'rec-a',      label: 'evaluate_record()',     subtitle: 'per dataset row',       type: 'io',       col: 0, row: 4 },
          { id: 'rec-b',      label: 'evaluate_record()',     subtitle: 'per dataset row',       type: 'io',       col: 2, row: 4 }
        ],
        [
          { from: 'eval-all',   to: 'outer-pool', label: 'submit variants' },
          { from: 'outer-pool', to: 'var-a',      label: 'thread 1' },
          { from: 'outer-pool', to: 'var-b',      label: 'thread 2' },
          { from: 'var-a',      to: 'inner-a',    label: '_execute_single_variant' },
          { from: 'var-b',      to: 'inner-b',    label: '_execute_single_variant' },
          { from: 'inner-a',    to: 'rec-a',      label: 'max_workers threads' },
          { from: 'inner-b',    to: 'rec-b',      label: 'max_workers threads' }
        ],
        { width: 680, height: 440 }
      ),

      createInfoCard(
        'Thread count calculation',
        'Total concurrent threads = <code>num_target_variants * max_workers</code>. ' +
        'With 3 target variants and <code>max_workers: 4</code>, up to 12 records are processed simultaneously. ' +
        'Set <code>max_workers</code> in your config to control inner parallelism per variant.',
        'info'
      ),

      createTabs(
        [
          {
            label: 'Outer Pool (per variant)',
            content:
              '<p style="color:var(--text-secondary);margin:12px 0">One thread per target variant. ' +
              'Variants are generated by <code>generate_args_combinations()</code> + <code>simplify_combination_names()</code> (Cartesian product of parameters).</p>' +
              createCodeBlock(
                '# combination_utils.py\n' +
                'def generate_args_combinations(\n' +
                '    model_cfg: TargetVariantConfig,\n' +
                ') -> List[Dict[str, Any]]:\n' +
                '    """Generate all argument combinations (Cartesian product).\n' +
                '\n' +
                '    Uses model_cfg.args (list of dicts with list values)\n' +
                '    to produce all parameter combinations.\n' +
                '    """\n' +
                '    if not model_cfg.args:\n' +
                '        return [{}]\n' +
                '    # ... build Cartesian product from args\n' +
                '    return combinations\n' +
                '\n' +
                'def simplify_combination_names(\n' +
                '    model_name: str, arg_combinations: List[Dict[str, Any]]\n' +
                ') -> Dict[str, Dict[str, Any]]:\n' +
                '    """Generate simplified names using only varying parameters."""',
                'python', { filePath: '_engine/combination_utils.py', highlightLines: [2, 10, 19] }
              )
          },
          {
            label: 'Inner Pool (per record)',
            content:
              '<p style="color:var(--text-secondary);margin:12px 0">Within each variant thread, a second ' +
              '<code>ThreadPoolExecutor(max_workers)</code> parallelizes across dataset records.</p>' +
              createCodeBlock(
                '# Inside _execute_single_variant:\n' +
                'with ThreadPoolExecutor(max_workers=max_workers) as executor:\n' +
                '    futures = [\n' +
                '        executor.submit(\n' +
                '            contextvars.copy_context().run,\n' +
                '            self.evaluate_record, record, run_id,\n' +
                '            model_config_name, model_name, model_instance,\n' +
                '            **model_args,\n' +
                '        )\n' +
                '        for record in records\n' +
                '    ]\n' +
                '    for future in as_completed(futures):\n' +
                '        eval_output = future.result()\n' +
                '        self._save_result(eval_output, output_path)',
                'python', { filePath: '_engine/evaluation/evaluation_executor.py', highlightLines: [2, 5, 12, 13] }
              )
          },
          {
            label: 'evaluate_record() detail',
            content:
              '<p style="color:var(--text-secondary);margin:12px 0">The innermost unit: runs one record through ' +
              'inference + all evaluators. This is where actual model calls happen.</p>' +
              createCodeBlock(
                'def evaluate_record(self, record, run_id, model_name,\n' +
                '                    model_display_name, model, **kwargs):\n' +
                '    # 1. Apply input mapping (dataset field → target param)\n' +
                '    mapped_input = _apply_target_input_mapping(record, target_mapping or {})\n' +
                '\n' +
                '    # 2. Run inference with OTel trace capture\n' +
                '    model_output, agent_trace, response_time_ms = self._run_inference(\n' +
                '        model, mapped_input, model_name, record_id,\n' +
                '    )\n' +
                '\n' +
                '    # 3. Enrich output from trace (tool_calls, tool_definitions)\n' +
                '    if isinstance(model_output, dict):\n' +
                '        self._enrich_output_from_trace(model_output, agent_trace)\n' +
                '\n' +
                '    # 4. Build InferenceOutput and run evaluators\n' +
                '    inference_output = self._build_inference_output(...)\n' +
                '    evaluator_results = self._compute_evaluators(inference_output)\n' +
                '\n' +
                '    # 5. Assemble output\n' +
                '    return EvaluationOutput(\n' +
                '        run_id=run_id,\n' +
                '        inference_output=inference_output,\n' +
                '        evaluators=evaluator_results,\n' +
                '        system_evaluators=system_metrics,\n' +
                '        model_display_name=model_display_name,\n' +
                '        metadata={},\n' +
                '    )',
                'python', { filePath: '_engine/evaluation/evaluation_executor.py', highlightLines: [4, 7, 11, 16, 20, 23] }
              )
          }
        ],
        'threading-tabs'
      ),

      // ── 2.3 Results Pipeline ──
      '<h3 id="results-pipeline" style="margin-top:32px">Results Pipeline</h3>',
      '<p style="color:var(--text-secondary);margin-bottom:16px">',
      'How results flow from per-record evaluation to final aggregated output.',
      '</p>',

      createFlowDiagram(
        'Results Pipeline',
        [
          { id: 'eval-rec',  label: 'evaluate_record()',    subtitle: 'per-record',          type: 'function', col: 0, row: 0 },
          { id: 'jsonl',     label: 'JSONL Append',         subtitle: '_save_result()',       type: 'io',       col: 2, row: 0 },
          { id: 'collect',   label: 'Collect Results',      subtitle: 'as_completed()',       type: 'function', col: 0, row: 1 },
          { id: 'agg',       label: 'EvaluatorsAggregator', subtitle: '.analyze_results()',   type: 'class',    col: 1, row: 2 },
          { id: 'formatter', label: 'OutputFormatter',      subtitle: '.persist_aitk_*()',    type: 'class',    col: 1, row: 3 },
          { id: 'aitk',      label: 'AITK Sidebar',         subtitle: 'VS Code integration', type: 'external', col: 0, row: 4 },
          { id: 'local-out', label: 'Local Output Dir',     subtitle: 'output/',              type: 'io',       col: 2, row: 4 }
        ],
        [
          { from: 'eval-rec',  to: 'jsonl',     label: 'stream line' },
          { from: 'eval-rec',  to: 'collect',   label: 'future.result()' },
          { from: 'collect',   to: 'agg',       label: 'all_results' },
          { from: 'agg',       to: 'formatter', label: 'metrics dict' },
          { from: 'formatter', to: 'aitk',      label: 'AITK JSON' },
          { from: 'formatter', to: 'local-out', label: 'JSONL + summary' }
        ],
        { width: 680, height: 440 }
      ),

      createInfoCard(
        'Streaming JSONL for resilience',
        'Each <code>evaluate_record()</code> result is appended to a JSONL file immediately via ' +
        '<code>_save_result()</code>. Partial results survive crashes or interruptions. ' +
        'The aggregator reads the complete JSONL at the end to compute summary metrics.',
        'tip'
      ),

      // ── 2.4 Target Factory and Cartesian Expansion ──
      '<h3 id="target-factory" style="margin-top:32px">Target Factory and Cartesian Expansion</h3>',
      '<p style="color:var(--text-secondary);margin-bottom:16px">',
      'The <code>TargetFactory</code> resolves target names from the registry and expands parameter combinations.',
      '</p>',

      createCodeBlock(
        'class TargetFactory:\n' +
        '    """Creates and registers evaluation targets from experiment configuration."""\n' +
        '\n' +
        '    def __init__(self, config, execution_context, connections_registry,\n' +
        '                 cloud_config=None, logger=None):\n' +
        '        self._config = config\n' +
        '        self._execution_context = execution_context\n' +
        '        self._connections_registry = connections_registry\n' +
        '        self._cloud_config = cloud_config\n' +
        '\n' +
        '    def register_targets(\n' +
        '        self, model_filter: Optional[List[str]] = None,\n' +
        '    ) -> Dict[str, Any]:\n' +
        '        """Register all targets from config and return the targets registry.\n' +
        '\n' +
        '        Args:\n' +
        '            model_filter: Optional list of target names to include.\n' +
        '        Returns:\n' +
        '            Dict mapping variant-name to target entry dict.\n' +
        '        """\n' +
        '        targets_registry: Dict[str, Any] = {}\n' +
        '        for target_cfg in self._config.experiment.targets:\n' +
        '            if model_filter and target_cfg.name not in model_filter:\n' +
        '                continue\n' +
        '            self._register_target(target_cfg, targets_registry)\n' +
        '        return targets_registry',
        'python',
        { filePath: '_engine/targets/target_factory.py', highlightLines: [4, 12, 13, 22, 26] }
      ),

      createCodeBlock(
        '# target_mapping.py — standalone utility functions (no class)\n' +
        '\n' +
        'def _apply_target_input_mapping(\n' +
        '    record: Dict[str, Any], mapping: Dict[str, str]\n' +
        ') -> Dict[str, Any]:\n' +
        '    """Apply target input mapping: build mapped input from dataset fields.\n' +
        '\n' +
        '    Mapping format uses "dataset.<field>" syntax:\n' +
        '      targets:\n' +
        '        - name: my_chatbot\n' +
        '          input_mapping:\n' +
        '            query: dataset.question_column\n' +
        '            context: dataset.context_column\n' +
        '    """\n' +
        '    if not mapping:\n' +
        '        return record\n' +
        '    input_mapping = {\n' +
        '        param: source.split(".", 1)[1]\n' +
        '        for param, source in mapping.items()\n' +
        '        if source.startswith("dataset.")\n' +
        '    }\n' +
        '    mapped = {param: record[field] for param, field in input_mapping.items()}\n' +
        '    # Pass through unmapped fields\n' +
        '    for key, value in record.items():\n' +
        '        if key not in mapped:\n' +
        '            mapped[key] = value\n' +
        '    return mapped',
        'python',
        { filePath: '_engine/targets/target_mapping.py', highlightLines: [3, 13, 18, 23] }
      ),

      // ── 2.5 Sequence Diagram ──
      '<h3 id="interaction-diagram" style="margin-top:32px">Detailed Component Interaction</h3>',
      '<p style="color:var(--text-secondary);margin-bottom:16px">',
      'Zoomed-in sequence showing how Runner, Backend, ModelEvaluator, and Executor interact during a local run.',
      '</p>',

      createSequenceDiagram(
        'Local Evaluation Sequence',
        [
          { id: 'runner-s',  label: 'ExperimentRunner', type: 'engine' },
          { id: 'backend-s', label: 'LocalBackend',     type: 'engine' },
          { id: 'meval-s',   label: 'ModelEvaluator',   type: 'evaluator' },
          { id: 'exec-s',    label: 'Executor',         type: 'engine' },
          { id: 'tgt-s',     label: 'Target',           type: 'target' },
          { id: 'evl-s',     label: 'Evaluator',        type: 'evaluator' },
          { id: 'agg-s',     label: 'Aggregator',       type: 'data' }
        ],
        [
          { from: 'runner-s',  to: 'backend-s', label: 'submit(context)' },
          { from: 'backend-s', to: 'meval-s',   label: 'new ModelEvaluator(config)' },
          { from: 'meval-s',   to: 'meval-s',   label: 'discover_components()' },
          { from: 'meval-s',   to: 'meval-s',   label: 'register_targets()' },
          { from: 'backend-s', to: 'meval-s',   label: 'load_dataset()' },
          { from: 'meval-s',   to: 'backend-s', label: 'BaseDataset',              type: 'return' },
          { from: 'backend-s', to: 'meval-s',   label: 'evaluate(dataset)' },
          { from: 'meval-s',   to: 'exec-s',    label: 'evaluate_all_parallel()' },
          { from: 'exec-s',    to: 'tgt-s',     label: '_run_inference(record)' },
          { from: 'tgt-s',     to: 'exec-s',    label: 'InferenceOutput',          type: 'return' },
          { from: 'exec-s',    to: 'evl-s',     label: 'evaluator.compute()' },
          { from: 'evl-s',     to: 'exec-s',    label: 'scores',                   type: 'return' },
          { from: 'exec-s',    to: 'exec-s',    label: '_save_result() JSONL' },
          { from: 'exec-s',    to: 'meval-s',   label: 'all_results',              type: 'return' },
          { from: 'meval-s',   to: 'agg-s',     label: 'analyze_results(jsonl_path)' },
          { from: 'agg-s',     to: 'meval-s',   label: 'AggregatedEvaluators',         type: 'return' }
        ]
      ),

      // ── 2.6 Preflight Validation ──
      '<h3 id="preflight" style="margin-top:32px">Preflight Validation</h3>',
      '<p style="color:var(--text-secondary);margin-bottom:16px">',
      'Before execution begins, the engine runs validation checks to catch common errors early.',
      '</p>',

      createCodeBlock(
        'def validate(config: Config) -> List[str]:\n' +
        '    """Run pre-flight checks before evaluation.\n' +
        '\n' +
        '    Checks:\n' +
        '      - Config file exists and is valid YAML\n' +
        '      - All referenced targets are in TARGET_REGISTRY\n' +
        '      - All referenced evaluators are in EVALUATOR_REGISTRY\n' +
        '      - Dataset file exists and is readable\n' +
        '      - Required environment variables are set\n' +
        '      - Target parameter types match expected signatures\n' +
        '\n' +
        '    Returns:\n' +
        '        List of error messages (empty = all checks passed)\n' +
        '    """',
        'python',
        { filePath: '_engine/preflight.py', highlightLines: [1, 6, 7, 8, 9, 10] }
      ),

      createInfoCard(
        'Fail fast',
        'Preflight runs <strong>before</strong> any model calls or dataset loading. It catches misconfigurations ' +
        'like missing registry entries, unreadable files, and missing environment variables so you do not waste ' +
        'time and API credits on a run that would fail mid-way.',
        'warning'
      ),

      // ── 2.7 OpenTelemetry Tracing ──
      '<h3 id="otel-tracing" style="margin-top:32px">OpenTelemetry Tracing</h3>',
      '<p style="color:var(--text-secondary);margin-bottom:16px">',
      'During inference, the engine captures OpenTelemetry spans to extract tool-call information from LLM responses.',
      '</p>',

      createCodeBlock(
        'class OTelTraceCapture:\n' +
        '    """Captures OTel traces from agent target invocations.\n' +
        '\n' +
        '    Sets up TracerProvider + LoggerProvider with in-memory collectors,\n' +
        '    auto-instruments the OpenAI SDK, and provides methods to wrap target\n' +
        '    invocations in parent spans and collect the resulting traces.\n' +
        '\n' +
        '    Usage (not a context manager):\n' +
        '        capture = OTelTraceCapture(capture_content=True)\n' +
        '        if capture.setup():  # returns True if OTel SDK available\n' +
        '            output, trace = capture.wrap_target_call(\n' +
        '                target_fn=model.infer,\n' +
        '                record=input_data,\n' +
        '                model_name="gpt-4o",\n' +
        '                record_id="abc123",\n' +
        '            )\n' +
        '        capture.shutdown()  # clean up providers\n' +
        '    """\n' +
        '\n' +
        '    def __init__(self, capture_content: bool = True) -> None:\n' +
        '        self._capture_content = capture_content\n' +
        '        self._setup_done = False\n' +
        '\n' +
        '    def setup(self) -> bool:\n' +
        '        """Set up OTel instrumentation. Returns True if successful."""\n' +
        '        # Auto-detects OTel SDK availability\n' +
        '        # Creates TracerProvider + SimpleSpanProcessor with in-memory collector\n' +
        '        # Optional OTLP export for external trace viewers\n' +
        '        ...\n' +
        '\n' +
        '    def shutdown(self) -> None:\n' +
        '        """Clean up OTel providers."""\n' +
        '        ...',
        'python',
        { filePath: '_engine/tracing/otel_trace_capture.py', highlightLines: [1, 10, 11, 21, 25, 32] }
      ),

      createInfoCard(
        'Why OTel tracing matters',
        'Agent evaluators like <code>ToolCallAccuracyEvaluator</code> need to know which tools the LLM called. ' +
        'The <code>OTelTraceCapture</code> context manager intercepts spans emitted by the Azure OpenAI SDK ' +
        'and extracts tool definitions automatically -- no manual instrumentation required.',
        'info'
      )
    ].join('\n');

    engineEl.innerHTML = engineContent;
  }

  // ── Register clickable node details for flow diagrams ──
  registerNodeDetails({
    'py-files': {
      title: 'Project Python Files',
      description: 'All .py files in the working directory are scanned. The scanner excludes hidden directories, __pycache__, .venv, and node_modules.',
    },
    'ast-scanner': {
      title: 'AST Scanner (discovery.py)',
      description: 'Uses ast module to parse source files and detect decorator usage on class definitions. Only files containing decorator strings are fully parsed.',
      code: 'def _has_decorator_on_class(tree, target_decorators):\n    for node in ast.walk(tree):\n        if isinstance(node, ast.ClassDef):\n            for decorator in node.decorator_list:\n                if isinstance(decorator, ast.Name) and decorator.id in target_decorators:\n                    return True\n    return False',
      lang: 'python',
      file: '_engine/discovery.py'
    },
    'eval-reg': {
      title: 'EVALUATOR_REGISTRY',
      description: 'Global dictionary mapping evaluator names to their wrapper classes. Populated when modules with @evaluator-decorated classes are imported.',
      code: 'EVALUATOR_REGISTRY: Dict[str, type] = {}\n\ndef evaluator(name: Optional[str] = None) -> Callable:\n    """Decorator factory for creating evaluators.\n    Wraps the user class in an EvaluatorWrapper(BaseEvaluator).\n    """\n    def decorator(cls):\n        evaluator_name = name or cls.__name__\n        class EvaluatorWrapper(BaseEvaluator): ...\n        EVALUATOR_REGISTRY[evaluator_name] = EvaluatorWrapper\n        return EvaluatorWrapper\n    return decorator',
      lang: 'python',
      file: '_engine/decorators.py'
    },
    'target-reg': {
      title: 'TARGET_REGISTRY',
      description: 'Global dictionary mapping target names to their wrapper classes. Works identically to the evaluator registry.',
      code: 'TARGET_REGISTRY: Dict[str, type] = {}\n\ndef target(name: Optional[str] = None) -> Callable:\n    """Decorator factory for creating targets.\n    Wraps the user class in a TargetWrapper(BaseTarget).\n    """\n    def decorator(cls):\n        target_name = name or cls.__name__\n        class TargetWrapper(BaseTarget): ...\n        TARGET_REGISTRY[target_name] = TargetWrapper\n        return TargetWrapper\n    return decorator',
      lang: 'python',
      file: '_engine/decorators.py'
    },
    'dataset-reg': {
      title: 'DATASET_REGISTRY',
      description: 'Global dictionary mapping dataset names to their wrapper classes.',
      code: 'DATASET_REGISTRY: Dict[str, type] = {}\n\ndef dataset(name: Optional[str] = None) -> Callable:\n    """Decorator factory for creating datasets.\n    Wraps the user class in a DatasetWrapper(BaseDataset).\n    """\n    def decorator(cls):\n        dataset_name = name or cls.__name__\n        class DatasetWrapper(BaseDataset): ...\n        DATASET_REGISTRY[dataset_name] = DatasetWrapper\n        return DatasetWrapper\n    return decorator',
      lang: 'python',
      file: '_engine/decorators.py'
    },
    'runner': {
      title: 'ExperimentRunner',
      description: 'Top-level entry point. Loads config, selects the compute backend, builds RunContext, and calls backend.submit().',
      code: 'class ExperimentRunner:\n    def run(self, config_path, env_path=None,\n            dataset_path=None, remote_compute=False,\n            model_filter=None, **kwargs) -> JobInfo:\n        config = Config.from_yaml(config_path)\n        backend = self._select_backend(config, remote_compute)\n        return backend.submit(RunContext(...))',
      lang: 'python',
      file: '_engine/runner.py'
    },
    'local': {
      title: 'LocalComputeBackend',
      description: 'Runs evaluation synchronously in the current process. Creates a ModelEvaluator, loads the dataset, and calls evaluate().',
    },
    'foundry': {
      title: 'FoundryComputeBackend',
      description: 'Packages the evaluation config and dataset, then submits to Azure AI Foundry for remote cloud execution. Returns immediately with SUBMITTED status.',
    },
    'evaluator': {
      title: 'ModelEvaluator',
      description: 'Main orchestration class. Initializes registries, loads datasets, creates the EvaluationExecutor, and drives the parallel evaluation pipeline.',
    },
    'eval-all': {
      title: 'evaluate_all_parallel()',
      description: 'Entry point for two-level parallel execution. Expands target variants and spawns outer threads.',
    },
    'outer-pool': {
      title: 'Outer ThreadPoolExecutor',
      description: 'One thread per target variant. Each thread runs _execute_single_variant() independently.',
    },
    'agg': {
      title: 'EvaluatorsAggregator',
      description: 'Reads all EvaluationOutput records and computes summary metrics (mean scores per evaluator by default).',
    },
    'formatter': {
      title: 'OutputFormatter',
      description: 'Writes results to AITK sidebar JSON for VS Code, local output directory, and terminal summary.',
    }
  });
}

// Initialize on DOMContentLoaded
document.addEventListener('DOMContentLoaded', initArchEngineContent);
