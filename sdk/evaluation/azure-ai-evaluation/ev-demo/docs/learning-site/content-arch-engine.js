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
        'def discover_components(search_path: str) -> Dict[str, List[str]]:\n' +
        '    """Scan CWD for @evaluator, @target, @dataset decorators via AST.\n' +
        '\n' +
        '    Steps:\n' +
        '      1. Walk all .py files under search_path\n' +
        '      2. Fast text pre-filter for decorator strings\n' +
        '      3. ast.parse() only matching files\n' +
        '      4. Import matching modules to trigger decorator registration\n' +
        '\n' +
        '    Skips: .venv, __pycache__, node_modules, .git directories\n' +
        '    """\n' +
        '    base_dir = Path(search_path or os.getcwd())\n' +
        '    if not force and base_dir in _DISCOVERED_DIRECTORIES:\n' +
        '        return\n' +
        '    from .decorators import DATASET_REGISTRY, EVALUATOR_REGISTRY, TARGET_REGISTRY\n' +
        '    _discover_in_directory(base_dir)\n' +
        '    _DISCOVERED_DIRECTORIES.add(base_dir)',
        'python',
        { filePath: '_engine/discovery.py', highlightLines: [1, 12, 15, 16], title: 'AST-based Component Discovery' }
      ),

      createCodeBlock(
        'def _has_decorator_on_class(tree: ast.AST, target_decorators: Set[str]) -> bool:\n' +
        '    """Check if any class definition has the target decorators."""\n' +
        '    for node in ast.walk(tree):\n' +
        '        if isinstance(node, ast.ClassDef):\n' +
        '            for decorator in node.decorator_list:\n' +
        '                if isinstance(decorator, ast.Name) and decorator.id in target_decorators:\n' +
        '                    return True\n' +
        '    return False',
        'python',
        { filePath: '_engine/discovery.py', highlightLines: [3, 4, 6] }
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
        '    """Abstract base for all compute backends."""\n' +
        '\n' +
        '    @abstractmethod\n' +
        '    def submit(self, context: RunContext, **kwargs: Any) -> JobInfo:\n' +
        '        """Submit an evaluation job.\n' +
        '\n' +
        '        Args:\n' +
        '            context: RunContext with config_path, env_path,\n' +
        '                     dataset_path, model_filter\n' +
        '        Returns:\n' +
        '            JobInfo with job_id and status (COMPLETED / SUBMITTED)\n' +
        '        """\n' +
        '        ...',
        'python',
        { filePath: '_engine/compute.py', highlightLines: [4, 5], title: 'ComputeBackend ABC' }
      ),

      createCodeBlock(
        'class LocalComputeBackend(ComputeBackend):\n' +
        '    """Run evaluation synchronously in the current process."""\n' +
        '\n' +
        '    def submit(self, context: RunContext, **kwargs: Any) -> JobInfo:\n' +
        '        from .evaluation.evaluator import ModelEvaluator\n' +
        '        evaluator = ModelEvaluator(\n' +
        '            config_path=context.config_path,\n' +
        '            model_filter=context.model_filter,\n' +
        '        )\n' +
        '        dataset = evaluator.load_dataset(context.dataset_path)\n' +
        '        evaluator.evaluate(dataset)\n' +
        '        return JobInfo(job_id=run_id, status=JobStatus.COMPLETED)',
        'python',
        { filePath: '_engine/compute.py', highlightLines: [4, 6, 10, 11], title: 'LocalComputeBackend' }
      ),

      createCodeBlock(
        'class FoundryComputeBackend(ComputeBackend):\n' +
        '    """Submit evaluation to Azure AI Foundry for remote execution.\n' +
        '\n' +
        '    Requires cloud.foundry_project in config.yaml.\n' +
        '    """\n' +
        '    def __init__(self, project_endpoint: str):\n' +
        '        self._endpoint = project_endpoint\n' +
        '\n' +
        '    def submit(self, context: RunContext, **kwargs: Any) -> JobInfo:\n' +
        '        # Package config + dataset, upload to Foundry\n' +
        '        # Returns immediately with SUBMITTED status\n' +
        '        return JobInfo(job_id=remote_id, status=JobStatus.SUBMITTED)',
        'python',
        { filePath: '_engine/foundry_compute.py', highlightLines: [6, 9], title: 'FoundryComputeBackend' }
      ),

      createTable(
        ['Backend', 'Class', 'File', 'Execution Model', 'Use Case'],
        [
          ['Local',   '<code>LocalComputeBackend</code>',   '<code>compute.py</code>',         'Synchronous, in-process',    'Development, CI/CD, local testing'],
          ['Foundry', '<code>FoundryComputeBackend</code>', '<code>foundry_compute.py</code>',  'Async, cloud API submission', 'Large-scale production evaluations']
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
        '    """Root configuration parsed from config.yaml."""\n' +
        '    experiment: ExperimentConfig\n' +
        '    cloud: Optional[CloudConfig] = None\n' +
        '\n' +
        '    @classmethod\n' +
        '    def from_yaml(cls, path: str) -> "Config":\n' +
        '        with open(path) as f:\n' +
        '            raw = yaml.safe_load(f)\n' +
        '        return cls.model_validate(raw)\n' +
        '\n' +
        'class ExperimentConfig(BaseModel):\n' +
        '    """Defines the experiment structure."""\n' +
        '    targets: List[TargetVariantConfig]\n' +
        '    evaluators: List[EvaluatorConfig]\n' +
        '    dataset: DatasetConfig\n' +
        '    max_workers: int = 4            # thread pool size\n' +
        '    output_dir: str = ".eval_output"',
        'python',
        { filePath: '_engine/models/config.py', highlightLines: [3, 7, 12, 14, 15, 16], title: 'Config Pydantic Model' }
      ),

      createCodeBlock(
        'class EvaluationOutput(BaseModel):\n' +
        '    """Result for a single dataset record."""\n' +
        '    record_index: int\n' +
        '    target_variant: str\n' +
        '    inference: InferenceOutput\n' +
        '    scores: Dict[str, float]        # evaluator_name -> score\n' +
        '    error: Optional[str] = None\n' +
        '\n' +
        'class InferenceOutput(BaseModel):\n' +
        '    """Response from a target invocation."""\n' +
        '    response: str\n' +
        '    latency_ms: float\n' +
        '    token_usage: Optional[Dict[str, int]] = None\n' +
        '    tool_calls: Optional[List[Dict]] = None  # via OTel tracing',
        'python',
        { filePath: '_engine/models/evaluation_output.py + inference_output.py', highlightLines: [1, 5, 6, 9, 13, 14] }
      ),

      createTable(
        ['Model', 'File', 'Purpose'],
        [
          ['<code>Config</code>',            '<code>models/config.py</code>',            'Root YAML config; holds ExperimentConfig + optional CloudConfig'],
          ['<code>ExperimentConfig</code>',   '<code>models/config.py</code>',            'Targets, evaluators, dataset, max_workers, output_dir'],
          ['<code>ExecutionContext</code>',    '<code>models/execution_context.py</code>', 'Runtime state: resolved paths, active run ID, progress tracker'],
          ['<code>EvaluationOutput</code>',   '<code>models/evaluation_output.py</code>', 'Per-record result: scores, inference output, errors'],
          ['<code>InferenceOutput</code>',    '<code>models/inference_output.py</code>',  'Target response: text, latency, token usage, tool calls']
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
          { from: 'srunner',    to: 'discovery',  label: 'discover_components(cwd)' },
          { from: 'discovery',  to: 'srunner',    label: 'registries populated',      type: 'return' },
          { from: 'srunner',    to: 'model-eval', label: 'LocalBackend.submit(ctx)' },
          { from: 'model-eval', to: 'model-eval', label: 'load_dataset()' },
          { from: 'model-eval', to: 'executor',   label: 'evaluate_all_parallel()' },
          { from: 'executor',   to: 'starget',    label: 'target.infer(record)' },
          { from: 'starget',    to: 'executor',   label: 'InferenceOutput',            type: 'return' },
          { from: 'executor',   to: 'sevaluator', label: 'evaluator.compute(record)' },
          { from: 'sevaluator', to: 'executor',   label: 'scores Dict[str, float]',    type: 'return' },
          { from: 'executor',   to: 'executor',   label: 'save JSONL line' },
          { from: 'executor',   to: 'aggregator', label: 'aggregate(all_results)' },
          { from: 'aggregator', to: 'output',     label: 'OutputFormatter.format()' },
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
          ['<code>EvaluatorsAggregator</code>','<code>evaluation/evaluators_aggregator.py</code>', 'Reads JSONL results, delegates to evaluator.aggregate(), produces summary'],
          ['<code>OutputFormatter</code>',     '<code>evaluation/output_formatter.py</code>',      'Writes AITK sidebar JSON, copies to AITK_EVALS_JOBS_DIR and local dir'],
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
              '<li>Detects execution mode (direct vs. project environment)</li>' +
              '<li>Delegates to <code>cli()</code> Click group</li>' +
              '</ul>' +
              createCodeBlock(
                'def main():\n' +
                '    """Entry point for the ev CLI."""\n' +
                '    if "--plain" in sys.argv:\n' +
                '        os.environ["EV_PLAIN"] = "1"\n' +
                '    cli()',
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
              '<li><code>ev init</code> -- Scaffold a new project config</li>' +
              '<li><code>ev eval</code> -- Run a single evaluator</li>' +
              '</ul>' +
              createCodeBlock(
                '@click.group()\n' +
                'def cli():\n' +
                '    """Azure AI Evaluation Engine CLI."""\n' +
                '    pass\n' +
                '\n' +
                'cli.add_command(run)\n' +
                'cli.add_command(init)\n' +
                'cli.add_command(eval_cmd)',
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
              '<li>Accepts <code>--config</code>, <code>--env</code>, <code>--dataset</code>, <code>--remote</code>, <code>--model</code></li>' +
              '<li>Calls <code>discover_components()</code> to populate registries</li>' +
              '<li>Runs <code>preflight.validate()</code> for early error detection</li>' +
              '</ul>' +
              createCodeBlock(
                '@cli.command()\n' +
                '@click.option("--config", default="config.yaml")\n' +
                '@click.option("--env", default=None)\n' +
                '@click.option("--dataset", default=None)\n' +
                '@click.option("--remote", is_flag=True)\n' +
                '@click.option("--model", multiple=True)\n' +
                'def run(config, env, dataset, remote, model):\n' +
                '    runner = ExperimentRunner()\n' +
                '    job_info = runner.run(\n' +
                '        config_path=config,\n' +
                '        env_path=env,\n' +
                '        dataset_path=dataset,\n' +
                '        remote_compute=remote,\n' +
                '        model_filter=list(model) or None,\n' +
                '    )',
                'python', { filePath: '_engine/cli/commands/run.py', highlightLines: [7, 8, 9] }
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
                'def _select_backend(self, config: Config, remote: bool) -> ComputeBackend:\n' +
                '    if remote and config.cloud and config.cloud.foundry_project:\n' +
                '        return FoundryComputeBackend(\n' +
                '            project_endpoint=config.cloud.foundry_project\n' +
                '        )\n' +
                '    return LocalComputeBackend()',
                'python', { filePath: '_engine/runner.py', highlightLines: [2, 3, 6] }
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
              '<li>Returns <code>JobInfo</code> with COMPLETED status</li>' +
              '</ul>' +
              createCodeBlock(
                'class LocalComputeBackend(ComputeBackend):\n' +
                '    def submit(self, context: RunContext, **kwargs) -> JobInfo:\n' +
                '        evaluator = ModelEvaluator(\n' +
                '            config_path=context.config_path,\n' +
                '            model_filter=context.model_filter,\n' +
                '        )\n' +
                '        dataset = evaluator.load_dataset(context.dataset_path)\n' +
                '        results = evaluator.evaluate(dataset)\n' +
                '        return JobInfo(job_id=run_id, status=JobStatus.COMPLETED)',
                'python', { filePath: '_engine/compute.py', highlightLines: [2, 3, 7, 8] }
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
              '<li>Parses config via <code>Config.from_yaml()</code></li>' +
              '<li>Calls <code>discover_components(os.getcwd())</code> for AST registries</li>' +
              '<li>Registers targets via <code>TargetFactory.register_targets()</code></li>' +
              '<li>Registers evaluators via <code>_register_evaluators()</code></li>' +
              '<li>Applies model_filter to subset targets if specified</li>' +
              '</ul>' +
              createCodeBlock(
                'class ModelEvaluator:\n' +
                '    def __init__(\n' +
                '        self,\n' +
                '        config_path: str,\n' +
                '        model_filter: Optional[List[str]] = None,\n' +
                '    ):\n' +
                '        self.config = Config.from_yaml(config_path)\n' +
                '        discover_components(os.getcwd())\n' +
                '        self.targets = TargetFactory.register_targets(\n' +
                '            self.config.experiment.targets\n' +
                '        )\n' +
                '        self.evaluators = self._register_evaluators(\n' +
                '            self.config.experiment.evaluators\n' +
                '        )',
                'python', { filePath: '_engine/evaluation/evaluator.py', highlightLines: [2, 7, 8, 9, 12] }
              )
          },
          {
            module: 'evaluation/evaluator.py',
            func: 'ModelEvaluator.load_dataset(dataset_path) -> List[Dict[str, Any]]',
            file: '_engine/evaluation/evaluator.py',
            tag: 'evaluator',
            detail:
              '<p>Loads the evaluation dataset from JSONL or CSV.</p>' +
              '<ul>' +
              '<li>If <code>dataset_path</code> is provided, uses it directly</li>' +
              '<li>Otherwise falls back to <code>config.experiment.dataset</code></li>' +
              '<li>Delegates to <code>DatasetFactory</code> for registry-aware loading</li>' +
              '</ul>' +
              createCodeBlock(
                'def load_dataset(\n' +
                '    self, dataset_path: Optional[str] = None\n' +
                ') -> List[Dict[str, Any]]:\n' +
                '    path = dataset_path or self.config.experiment.dataset.path\n' +
                '    return DatasetFactory.load(path)',
                'python', { filePath: '_engine/evaluation/evaluator.py', highlightLines: [1, 4, 5] }
              )
          },
          {
            module: 'evaluation/evaluator.py',
            func: 'ModelEvaluator.evaluate(dataset) -> Dict[str, Any]',
            file: '_engine/evaluation/evaluator.py',
            tag: 'evaluator',
            detail:
              '<p>Main evaluation entry point. Orchestrates parallel execution and aggregation.</p>' +
              '<ul>' +
              '<li>Creates <code>EvaluationExecutor</code> with configured max_workers</li>' +
              '<li>Calls <code>executor.evaluate_all_parallel()</code></li>' +
              '<li>Passes results to <code>EvaluatorsAggregator.aggregate()</code></li>' +
              '<li>Writes output via <code>OutputFormatter.format()</code></li>' +
              '</ul>' +
              createCodeBlock(
                'def evaluate(self, dataset: List[Dict[str, Any]]) -> Dict[str, Any]:\n' +
                '    executor = EvaluationExecutor(\n' +
                '        max_workers=self.config.experiment.max_workers\n' +
                '    )\n' +
                '    all_results = executor.evaluate_all_parallel(\n' +
                '        targets=self.targets,\n' +
                '        dataset=dataset,\n' +
                '        evaluators=self.evaluators,\n' +
                '    )\n' +
                '    metrics = EvaluatorsAggregator.aggregate(all_results)\n' +
                '    OutputFormatter.format(all_results, metrics)\n' +
                '    return {"results": all_results, "metrics": metrics}',
                'python', { filePath: '_engine/evaluation/evaluator.py', highlightLines: [1, 5, 10, 11] }
              )
          },
          {
            module: 'evaluation/evaluation_executor.py',
            func: 'EvaluationExecutor.evaluate_all_parallel(targets, dataset, evaluators) -> Dict',
            file: '_engine/evaluation/evaluation_executor.py',
            tag: 'engine',
            detail:
              '<p>Two-level parallel execution: outer threads per target variant, inner threads per record.</p>' +
              '<ul>' +
              '<li>Expands target variants via <code>expand_combinations()</code></li>' +
              '<li>Outer <code>ThreadPoolExecutor</code>: one thread per variant</li>' +
              '<li>Each thread calls <code>_execute_single_variant()</code></li>' +
              '</ul>' +
              createCodeBlock(
                'def evaluate_all_parallel(\n' +
                '    self,\n' +
                '    targets: List[TargetVariantConfig],\n' +
                '    dataset: List[Dict[str, Any]],\n' +
                '    evaluators: List[EvaluatorConfig],\n' +
                ') -> Dict:\n' +
                '    all_variants = []\n' +
                '    for t in targets:\n' +
                '        all_variants.extend(expand_combinations(t))\n' +
                '\n' +
                '    with ThreadPoolExecutor() as outer_pool:\n' +
                '        futures = {\n' +
                '            outer_pool.submit(\n' +
                '                self._execute_single_variant,\n' +
                '                variant, dataset, evaluators\n' +
                '            ): variant\n' +
                '            for variant in all_variants\n' +
                '        }',
                'python', { filePath: '_engine/evaluation/evaluation_executor.py', highlightLines: [1, 9, 11, 13, 14] }
              )
          },
          {
            module: 'evaluation/evaluation_executor.py',
            func: '_execute_single_variant(target, dataset, evaluators) -> List[EvaluationOutput]',
            file: '_engine/evaluation/evaluation_executor.py',
            tag: 'engine',
            detail:
              '<p>Processes all records for one target variant via inner thread pool.</p>' +
              '<ul>' +
              '<li>Inner <code>ThreadPoolExecutor(max_workers)</code> from config</li>' +
              '<li>Submits <code>evaluate_record()</code> for each record</li>' +
              '<li>Streams results to JSONL via <code>_save_result()</code></li>' +
              '</ul>' +
              createCodeBlock(
                'def _execute_single_variant(\n' +
                '    self, target, dataset, evaluators,\n' +
                ') -> List[EvaluationOutput]:\n' +
                '    results = []\n' +
                '    with ThreadPoolExecutor(max_workers=self.max_workers) as pool:\n' +
                '        futures = {\n' +
                '            pool.submit(\n' +
                '                self.evaluate_record, record, target, evaluators\n' +
                '            ): idx\n' +
                '            for idx, record in enumerate(dataset)\n' +
                '        }\n' +
                '        for future in as_completed(futures):\n' +
                '            result = future.result()\n' +
                '            results.append(result)\n' +
                '            self._save_result(result)  # JSONL\n' +
                '    return results',
                'python', { filePath: '_engine/evaluation/evaluation_executor.py', highlightLines: [1, 5, 8, 15] }
              )
          },
          {
            module: 'evaluation/evaluation_executor.py',
            func: 'evaluate_record(record, target, evaluators) -> EvaluationOutput',
            file: '_engine/evaluation/evaluation_executor.py',
            tag: 'evaluator',
            detail:
              '<p>Innermost unit of work. Runs one record through target + all evaluators.</p>' +
              '<ul>' +
              '<li>Step 1: <code>_run_inference(target, record)</code> with OTel tracing</li>' +
              '<li>Step 2: <code>_compute_evaluators(evaluators, record, inference)</code></li>' +
              '<li>Step 3: Assemble <code>EvaluationOutput</code></li>' +
              '<li>Catches exceptions per-record to avoid blocking the run</li>' +
              '</ul>' +
              createCodeBlock(
                'def evaluate_record(\n' +
                '    self, record, target, evaluators,\n' +
                ') -> EvaluationOutput:\n' +
                '    try:\n' +
                '        inference = self._run_inference(target, record)\n' +
                '        scores = self._compute_evaluators(\n' +
                '            evaluators, record, inference\n' +
                '        )\n' +
                '        return EvaluationOutput(\n' +
                '            record_index=record.get("__index__"),\n' +
                '            target_variant=target.name,\n' +
                '            inference=inference,\n' +
                '            scores=scores,\n' +
                '        )\n' +
                '    except Exception as e:\n' +
                '        return EvaluationOutput(\n' +
                '            record_index=record.get("__index__"),\n' +
                '            target_variant=target.name,\n' +
                '            error=str(e),\n' +
                '        )',
                'python', { filePath: '_engine/evaluation/evaluation_executor.py', highlightLines: [1, 5, 6, 9, 15] }
              )
          },
          {
            module: 'evaluation/evaluators_aggregator.py',
            func: 'EvaluatorsAggregator.aggregate(all_results) -> Dict[str, float]',
            file: '_engine/evaluation/evaluators_aggregator.py',
            tag: 'evaluator',
            detail:
              '<p>Aggregates per-record scores into summary metrics.</p>' +
              '<ul>' +
              '<li>Groups results by target variant and evaluator</li>' +
              '<li>Default aggregation: mean score per evaluator</li>' +
              '<li>Evaluators can override (e.g., F1 uses micro-average)</li>' +
              '</ul>' +
              createCodeBlock(
                'class EvaluatorsAggregator:\n' +
                '    @staticmethod\n' +
                '    def aggregate(\n' +
                '        all_results: List[EvaluationOutput],\n' +
                '    ) -> Dict[str, float]:\n' +
                '        scores_by_evaluator = defaultdict(list)\n' +
                '        for result in all_results:\n' +
                '            for name, score in result.scores.items():\n' +
                '                scores_by_evaluator[name].append(score)\n' +
                '        return {\n' +
                '            name: sum(scores) / len(scores)\n' +
                '            for name, scores in scores_by_evaluator.items()\n' +
                '        }',
                'python', { filePath: '_engine/evaluation/evaluators_aggregator.py', highlightLines: [3, 6, 10, 11] }
              )
          },
          {
            module: 'evaluation/output_formatter.py',
            func: 'OutputFormatter.format(results, metrics)',
            file: '_engine/evaluation/output_formatter.py',
            tag: 'engine',
            detail:
              '<p>Formats and persists results to multiple output locations.</p>' +
              '<ul>' +
              '<li>Writes JSONL results to <code>output_dir/</code></li>' +
              '<li>Generates AITK sidebar JSON for VS Code integration</li>' +
              '<li>Copies output to <code>AITK_EVALS_JOBS_DIR</code> if set</li>' +
              '<li>Prints summary table to terminal via Rich</li>' +
              '</ul>'
          }
        ]
      ),

      // ── 2.2 Two-Level Threading Model ──
      '<h3 id="threading-model" style="margin-top:32px">Two-Level Threading Model</h3>',
      '<p style="color:var(--text-secondary);margin-bottom:16px">',
      'The engine uses a nested threading strategy for maximum parallelism. ',
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
              'Variants are generated by <code>expand_combinations()</code> (Cartesian product of parameters).</p>' +
              createCodeBlock(
                '# combination_utils.py\n' +
                'def expand_combinations(\n' +
                '    target_config: TargetVariantConfig,\n' +
                ') -> List[TargetVariantConfig]:\n' +
                '    """Expand a target with multiple param values\n' +
                '    into concrete variants via Cartesian product.\n' +
                '\n' +
                '    Example: model=[gpt-4o, gpt-4o-mini], temperature=[0, 0.7]\n' +
                '    produces 4 variants.\n' +
                '    """\n' +
                '    param_lists = target_config.parameters\n' +
                '    combos = list(itertools.product(*param_lists.values()))\n' +
                '    return [\n' +
                '        target_config.with_params(dict(zip(param_lists.keys(), c)))\n' +
                '        for c in combos\n' +
                '    ]',
                'python', { filePath: '_engine/combination_utils.py', highlightLines: [2, 12, 13] }
              )
          },
          {
            label: 'Inner Pool (per record)',
            content:
              '<p style="color:var(--text-secondary);margin:12px 0">Within each variant thread, a second ' +
              '<code>ThreadPoolExecutor(max_workers)</code> parallelizes across dataset records.</p>' +
              createCodeBlock(
                '# Inside _execute_single_variant:\n' +
                'with ThreadPoolExecutor(max_workers=self.max_workers) as pool:\n' +
                '    futures = {\n' +
                '        pool.submit(\n' +
                '            self.evaluate_record, record, target, evaluators\n' +
                '        ): idx\n' +
                '        for idx, record in enumerate(dataset)\n' +
                '    }\n' +
                '    for future in as_completed(futures):\n' +
                '        result = future.result()\n' +
                '        results.append(result)\n' +
                '        self._save_result(result)  # JSONL append',
                'python', { filePath: '_engine/evaluation/evaluation_executor.py', highlightLines: [2, 5, 9, 12] }
              )
          },
          {
            label: 'evaluate_record() detail',
            content:
              '<p style="color:var(--text-secondary);margin:12px 0">The innermost unit: runs one record through ' +
              'inference + all evaluators. This is where actual model calls happen.</p>' +
              createCodeBlock(
                'def evaluate_record(self, record, target, evaluators):\n' +
                '    # 1. Run target inference with OpenTelemetry tracing\n' +
                '    with OTelTraceCapture() as tracer:\n' +
                '        inference = self._run_inference(target, record)\n' +
                '        inference.tool_calls = tracer.extract_tool_calls()\n' +
                '\n' +
                '    # 2. Run each evaluator on the record + inference result\n' +
                '    scores = {}\n' +
                '    for ev in evaluators:\n' +
                '        scores[ev.name] = ev.compute(\n' +
                '            record=record,\n' +
                '            inference=inference,\n' +
                '        )\n' +
                '\n' +
                '    # 3. Assemble output\n' +
                '    return EvaluationOutput(\n' +
                '        record_index=record["__index__"],\n' +
                '        target_variant=target.name,\n' +
                '        inference=inference,\n' +
                '        scores=scores,\n' +
                '    )',
                'python', { filePath: '_engine/evaluation/evaluation_executor.py', highlightLines: [3, 4, 10, 16] }
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
          { id: 'agg',       label: 'EvaluatorsAggregator', subtitle: '.aggregate()',         type: 'class',    col: 1, row: 2 },
          { id: 'formatter', label: 'OutputFormatter',      subtitle: '.format()',            type: 'class',    col: 1, row: 3 },
          { id: 'aitk',      label: 'AITK Sidebar',         subtitle: 'VS Code integration', type: 'external', col: 0, row: 4 },
          { id: 'local-out', label: 'Local Output Dir',     subtitle: '.eval_output/',        type: 'io',       col: 2, row: 4 }
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
        '    @staticmethod\n' +
        '    def register_targets(\n' +
        '        target_configs: List[TargetVariantConfig],\n' +
        '    ) -> List[TargetVariantConfig]:\n' +
        '        """Resolve target names from TARGET_REGISTRY\n' +
        '        and expand Cartesian parameter combinations.\n' +
        '\n' +
        '        Args:\n' +
        '            target_configs: Raw target configs from YAML\n' +
        '        Returns:\n' +
        '            Expanded list of concrete target variants\n' +
        '        """\n' +
        '        from ..decorators import TARGET_REGISTRY\n' +
        '        all_targets = []\n' +
        '        for tc in target_configs:\n' +
        '            cls = TARGET_REGISTRY[tc.name]\n' +
        '            expanded = expand_combinations(tc)\n' +
        '            all_targets.extend(expanded)\n' +
        '        return all_targets',
        'python',
        { filePath: '_engine/targets/target_factory.py', highlightLines: [3, 14, 17, 18] }
      ),

      createCodeBlock(
        'class TargetMapping:\n' +
        '    """Maps dataset columns to target function parameters.\n' +
        '\n' +
        '    Config example:\n' +
        '      targets:\n' +
        '        - name: my_chatbot\n' +
        '          mapping:\n' +
        '            query: question_column\n' +
        '            context: context_column\n' +
        '    """\n' +
        '    def apply(self, record: Dict) -> Dict:\n' +
        '        return {\n' +
        '            target_param: record[dataset_col]\n' +
        '            for target_param, dataset_col in self.mapping.items()\n' +
        '        }',
        'python',
        { filePath: '_engine/targets/target_mapping.py', highlightLines: [11, 12, 13, 14] }
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
          { from: 'meval-s',   to: 'backend-s', label: 'List[Dict]',              type: 'return' },
          { from: 'backend-s', to: 'meval-s',   label: 'evaluate(dataset)' },
          { from: 'meval-s',   to: 'exec-s',    label: 'evaluate_all_parallel()' },
          { from: 'exec-s',    to: 'tgt-s',     label: '_run_inference(record)' },
          { from: 'tgt-s',     to: 'exec-s',    label: 'InferenceOutput',          type: 'return' },
          { from: 'exec-s',    to: 'evl-s',     label: 'evaluator.compute()' },
          { from: 'evl-s',     to: 'exec-s',    label: 'scores',                   type: 'return' },
          { from: 'exec-s',    to: 'exec-s',    label: '_save_result() JSONL' },
          { from: 'exec-s',    to: 'meval-s',   label: 'all_results',              type: 'return' },
          { from: 'meval-s',   to: 'agg-s',     label: 'aggregate(all_results)' },
          { from: 'agg-s',     to: 'meval-s',   label: 'Dict[str, float]',         type: 'return' }
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
        '    """Context manager that captures OTel spans during inference.\n' +
        '\n' +
        '    Usage:\n' +
        '        with OTelTraceCapture() as tracer:\n' +
        '            result = target.infer(record)\n' +
        '            tool_calls = tracer.extract_tool_calls()\n' +
        '    """\n' +
        '    def __enter__(self):\n' +
        '        self._processor = SimpleSpanProcessor(self._exporter)\n' +
        '        trace.get_tracer_provider().add_span_processor(self._processor)\n' +
        '        return self\n' +
        '\n' +
        '    def __exit__(self, *args):\n' +
        '        self._processor.shutdown()\n' +
        '\n' +
        '    def extract_tool_calls(self) -> List[Dict]:\n' +
        '        """Parse captured spans for function/tool call attributes."""\n' +
        '        return trace_utils.extract_tool_definitions(self._spans)',
        'python',
        { filePath: '_engine/tracing/otel_trace_capture.py', highlightLines: [1, 5, 6, 7, 17, 19] }
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
      description: 'Global dictionary mapping evaluator names to their classes. Populated when modules with @evaluator-decorated classes are imported.',
      code: 'EVALUATOR_REGISTRY: Dict[str, Type] = {}\n\ndef evaluator(cls):\n    """Register a class as an evaluator."""\n    EVALUATOR_REGISTRY[cls.__name__] = cls\n    return cls',
      lang: 'python',
      file: '_engine/decorators.py'
    },
    'target-reg': {
      title: 'TARGET_REGISTRY',
      description: 'Global dictionary mapping target names to their classes. Works identically to the evaluator registry.',
      code: 'TARGET_REGISTRY: Dict[str, Type] = {}\n\ndef target(cls):\n    """Register a class as a target."""\n    TARGET_REGISTRY[cls.__name__] = cls\n    return cls',
      lang: 'python',
      file: '_engine/decorators.py'
    },
    'dataset-reg': {
      title: 'DATASET_REGISTRY',
      description: 'Global dictionary mapping dataset names to their loader classes.',
      code: 'DATASET_REGISTRY: Dict[str, Type] = {}\n\ndef dataset(cls):\n    """Register a class as a dataset loader."""\n    DATASET_REGISTRY[cls.__name__] = cls\n    return cls',
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
