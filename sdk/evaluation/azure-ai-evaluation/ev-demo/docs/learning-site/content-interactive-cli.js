/* ============================================================
   Content: Interactive CLI Deep Dive & Learning Roadmap
   Populates #interactive-cli and #roadmap sections
   Uses: createBranchingTerminal, createInteractiveTerminal,
         createCommandNavigator, createCallTrace,
         createInfoCard, createRoadmap,
         initTerminalAnimations
   ============================================================ */

function initInteractiveCliContent() {

  // ────────────────────────────────────────────────────────────
  // SECTION 1 -- Interactive CLI (#interactive-cli)
  // ────────────────────────────────────────────────────────────
  var cliEl = document.getElementById('interactive-cli');
  if (cliEl) {

    // ── ev run (branching: local vs remote) ──────────────────

    var evRunLocalOutput =
      '<span style="color:var(--accent)">Azure AI Evaluation Engine v2.0.0a1</span>\n\n' +
      '<span style="color:var(--text-muted)">╭─</span> <span style="color:var(--accent)">ev run</span> <span style="color:var(--text-muted)">────────────────────────────────────────────────╮</span>\n' +
      '<span style="color:var(--text-muted)">│</span> Config:      config.yaml                              <span style="color:var(--text-muted)">│</span>\n' +
      '<span style="color:var(--text-muted)">│</span> Experiment:  quickstart                               <span style="color:var(--text-muted)">│</span>\n' +
      '<span style="color:var(--text-muted)">│</span> Compute:     local                                    <span style="color:var(--text-muted)">│</span>\n' +
      '<span style="color:var(--text-muted)">│</span> Tracing:     disabled                                 <span style="color:var(--text-muted)">│</span>\n' +
      '<span style="color:var(--text-muted)">│</span> Evaluators:  f1_score, answer_length                  <span style="color:var(--text-muted)">│</span>\n' +
      '<span style="color:var(--text-muted)">│</span> Dataset:     data/qa_data.jsonl                       <span style="color:var(--text-muted)">│</span>\n' +
      '<span style="color:var(--text-muted)">│</span> Output:      output/                                  <span style="color:var(--text-muted)">│</span>\n' +
      '<span style="color:var(--text-muted)">╰─────────────────────────────────────────────────╯</span>\n\n' +
      'baseline <span style="color:var(--accent)">████████████████████</span> 15/15\n\n' +
      '       <span style="color:var(--accent)">Evaluation Results</span>\n' +
      '<span style="color:var(--text-muted)">┏━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┓</span>\n' +
      '<span style="color:var(--text-muted)">┃</span> Metric       <span style="color:var(--text-muted)">┃</span>                Value <span style="color:var(--text-muted)">┃</span>\n' +
      '<span style="color:var(--text-muted)">┡━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━┩</span>\n' +
      '<span style="color:var(--text-muted)">│</span> Status       <span style="color:var(--text-muted)">│</span>            completed <span style="color:var(--text-muted)">│</span>\n' +
      '<span style="color:var(--text-muted)">│</span> Records      <span style="color:var(--text-muted)">│</span>                   15 <span style="color:var(--text-muted)">│</span>\n' +
      '<span style="color:var(--text-muted)">│</span> Variants     <span style="color:var(--text-muted)">│</span>                    1 <span style="color:var(--text-muted)">│</span>\n' +
      '<span style="color:var(--text-muted)">│</span> Output       <span style="color:var(--text-muted)">│</span>    output/quickstart <span style="color:var(--text-muted)">│</span>\n' +
      '<span style="color:var(--text-muted)">│</span> f1_score     <span style="color:var(--text-muted)">│</span>               0.8467 <span style="color:var(--text-muted)">│</span>\n' +
      '<span style="color:var(--text-muted)">│</span> answer_length<span style="color:var(--text-muted)">│</span>             142.3000 <span style="color:var(--text-muted)">│</span>\n' +
      '<span style="color:var(--text-muted)">└──────────────┴──────────────────────┘</span>';

    var evRunLocalSteps = [
      { title: 'CLI Parses Options', description: '<strong style="color:var(--accent);font-size:11px;text-transform:uppercase;letter-spacing:0.5px">Setup</strong><br>Click parses --config, --experiment, --remote, --trace flags. Auto-detects config from candidates: config.yaml, evals.yaml, experiment/config.yaml.',
        tag: 'cli', file: '_engine/cli/commands/run.py' },
      { title: 'Load Configuration', description: 'Config.from_yaml() reads the YAML file, resolves environment variable interpolation (${}), validates schema, and returns a Config object. ' + deepDiveLink('configuration', 'Deep dive: Configuration System'),
        tag: 'config', file: '_engine/models/config.py' },
      { title: 'Discover Local Components', description: '<strong style="color:var(--accent);font-size:11px;text-transform:uppercase;letter-spacing:0.5px">Preparation</strong><br>AST-scans .py files for @evaluator, @target, @dataset decorators. Imports matching modules to trigger registration into EVALUATOR_REGISTRY and TARGET_REGISTRY. ' + deepDiveLink('custom', 'Deep dive: Custom Components'),
        tag: 'engine', file: '_engine/cli/utils/discovery.py' },
      { title: 'Build ExperimentRunner', description: 'Instantiates ExperimentRunner with the loaded config. Selects LocalComputeBackend based on compute: local setting. ' + deepDiveLink('engine-flow', 'Deep dive: Engine Flow'),
        tag: 'engine', file: '_engine/runner.py' },
      { title: 'Resolve Target Functions', description: 'TargetFactory resolves each target from config. For custom targets, imports the Python module. For Azure AI models, constructs the API client. ' + deepDiveLink('targets', 'Deep dive: Target System'),
        tag: 'engine', file: '_engine/targets/target_factory.py' },
      { title: 'Load Dataset', description: '<strong style="color:var(--accent);font-size:11px;text-transform:uppercase;letter-spacing:0.5px">Execution</strong><br>DatasetLoader reads the JSONL file, validates required columns match evaluator mappings, returns list of row dicts.',
        tag: 'engine', file: '_engine/datasets.py' },
      { title: 'Generate Argument Combinations', description: 'generate_args_combinations() creates the Cartesian product of targets x dataset rows, producing the full execution matrix.',
        tag: 'engine', file: '_engine/combination_utils.py' },
      { title: 'Execute Target Calls', description: 'Runs each target function against every dataset row. Uses ThreadPoolExecutor for parallel execution. Progress bar updates via Rich. ' + deepDiveLink('engine-flow', 'Deep dive: Engine Flow'),
        tag: 'engine', file: '_engine/evaluation/evaluation_executor.py' },
      { title: 'Run Evaluators', description: 'For each completed target call, runs all configured evaluators. Local evaluators (f1_score) run in-process. Cloud evaluators batch API calls. ' + deepDiveLink('evaluators', 'Deep dive: Evaluator Catalog'),
        tag: 'evaluator', file: '_engine/evaluation/evaluation_executor.py' },
      { title: 'Aggregate Results', description: '<strong style="color:var(--accent);font-size:11px;text-transform:uppercase;letter-spacing:0.5px">Output</strong><br>Collects per-row scores, computes aggregate metrics (mean, count). Builds the results summary dict. ' + deepDiveLink('engine-flow', 'Deep dive: Engine Flow'),
        tag: 'engine', file: '_engine/evaluation/evaluators_aggregator.py' },
      { title: 'Write Output', description: 'Saves results to output/quickstart/: eval_results.jsonl (per-row), summary.json (aggregates), and metadata.json (run info).',
        tag: 'engine', file: '_engine/evaluation/output_formatter.py' },
      { title: 'Display Results Table', description: 'show_results_table() renders the Rich table with metrics and status. Prints output directory path.',
        tag: 'cli', file: '_engine/cli/commands/run.py' }
    ];

    var evRunRemoteOutput =
      '<span style="color:var(--accent)">Azure AI Evaluation Engine v2.0.0a1</span>\n\n' +
      '<span style="color:var(--text-muted)">╭─</span> <span style="color:var(--accent)">ev run</span> <span style="color:var(--text-muted)">────────────────────────────────────────────────╮</span>\n' +
      '<span style="color:var(--text-muted)">│</span> Config:      config.yaml                              <span style="color:var(--text-muted)">│</span>\n' +
      '<span style="color:var(--text-muted)">│</span> Experiment:  quickstart                               <span style="color:var(--text-muted)">│</span>\n' +
      '<span style="color:var(--text-muted)">│</span> Compute:     remote (Azure AI Foundry)                 <span style="color:var(--text-muted)">│</span>\n' +
      '<span style="color:var(--text-muted)">│</span> Tracing:     disabled                                 <span style="color:var(--text-muted)">│</span>\n' +
      '<span style="color:var(--text-muted)">│</span> Evaluators:  f1_score, answer_length                  <span style="color:var(--text-muted)">│</span>\n' +
      '<span style="color:var(--text-muted)">│</span> Dataset:     data/qa_data.jsonl                       <span style="color:var(--text-muted)">│</span>\n' +
      '<span style="color:var(--text-muted)">│</span> Output:      output/                                  <span style="color:var(--text-muted)">│</span>\n' +
      '<span style="color:var(--text-muted)">╰─────────────────────────────────────────────────╯</span>\n\n' +
      'Submitting to Foundry...\n' +
      'Job submitted: <span style="color:var(--accent)">job-abc123</span>\n\n' +
      '<span style="color:var(--text-muted)">╭─</span> <span style="color:var(--accent)">Foundry Cloud Compute -- Evaluation Complete</span> <span style="color:var(--text-muted)">─╮</span>\n' +
      '<span style="color:var(--text-muted)">│</span> Job ID:        job-abc123                             <span style="color:var(--text-muted)">│</span>\n' +
      '<span style="color:var(--text-muted)">│</span> Evaluation ID: eval-def456                            <span style="color:var(--text-muted)">│</span>\n' +
      '<span style="color:var(--text-muted)">│</span> Status:        completed                              <span style="color:var(--text-muted)">│</span>\n' +
      '<span style="color:var(--text-muted)">│</span> Report:        https://ai.azure.com/...               <span style="color:var(--text-muted)">│</span>\n' +
      '<span style="color:var(--text-muted)">╰─────────────────────────────────────────────────╯</span>';

    var evRunRemoteSteps = [
      { title: 'CLI Parses Options', description: 'Click parses --config and --remote flags. Detects remote execution mode from --remote flag or config compute setting.',
        tag: 'cli', file: '_engine/cli/commands/run.py' },
      { title: 'Load Configuration', description: 'Config.from_yaml() reads YAML. Validates that cloud section exists with project endpoint and default deployment. ' + deepDiveLink('configuration', 'Deep dive: Configuration System'),
        tag: 'config', file: '_engine/models/config.py' },
      { title: 'Discover Components', description: 'discover_components(force=False) returns None if cache is fresh. Otherwise AST-scans for decorators and registers components.',
        tag: 'engine', file: '_engine/discovery.py' },
      { title: 'Build FoundryComputeBackend', description: 'Instantiates FoundryComputeBackend with Azure credentials. Validates connection to Foundry project endpoint. ' + deepDiveLink('engine-flow', 'Deep dive: Engine Flow'),
        tag: 'engine', file: '_engine/foundry_compute.py' },
      { title: 'Package and Upload', description: 'Packages config, dataset, evaluator code into a submission payload. Uploads to Azure AI Foundry.',
        tag: 'engine', file: '_engine/foundry_compute.py' },
      { title: 'Submit Remote Job', description: 'Calls Foundry API to create evaluation job. Returns job ID for tracking.',
        tag: 'engine', file: '_engine/foundry_compute.py' },
      { title: 'Poll for Completion', description: 'Polls job status until completed, failed, or cancelled. Shows spinner in terminal.',
        tag: 'engine', file: '_engine/foundry_compute.py' },
      { title: 'Download Results', description: 'Fetches results from Foundry. Writes to local output/ directory. Displays completion panel with links.',
        tag: 'cli', file: '_engine/cli/commands/run.py' }
    ];

    var termRun = createBranchingTerminal({
      id: 'branch-ev-run',
      scenario: 'Choose your execution mode:' +
        createTable(
          ['', 'Local', 'Remote (Foundry)'],
          [
            ['Requirements', 'Python + ev installed', 'Azure subscription + Foundry project'],
            ['Speed', 'Fast for small datasets', 'Scales to large datasets'],
            ['Cost', 'Free (your machine)', 'Azure compute charges'],
            ['Best for', 'Development, testing, &lt;50 rows', 'Production, benchmarks, &gt;100 rows'],
          ]
        ),
      choices: [
        {
          label: 'Local Execution',
          description: 'Run evaluations on your machine',
          terminal: {
            command: 'ev run -c config.yaml',
            output: evRunLocalOutput,
            steps: evRunLocalSteps,
            tips: [
              'Add <code>--trace</code> to enable OpenTelemetry tracing for debugging',
              'Use <code>--output ./my-output</code> to override the output directory'
            ]
          }
        },
        {
          label: 'Remote (Azure AI Foundry)',
          description: 'Submit to cloud compute',
          terminal: {
            command: 'ev run -c config.yaml --remote',
            output: evRunRemoteOutput,
            steps: evRunRemoteSteps,
            tips: [
              'Configure Foundry connection first with <code>ev cloud set</code>',
              'Remote runs support larger datasets and parallel cloud evaluators'
            ]
          }
        }
      ]
    });

    var evRunCallTrace = createCallTrace('ev run -- Execution Flow', [
      { module: 'CLI', func: 'run(path, config, ...)', file: '_engine/cli/commands/run.py',
        detail: 'Click parses all options. Auto-detects config from candidates: config.yaml, evals.yaml, experiment/config.yaml', tag: 'cli' },
      { module: 'Config', func: 'Config.from_yaml(path)', file: '_engine/models/config.py',
        detail: 'Reads YAML, resolves ${ENV_VAR} interpolation, validates schema, returns Config', tag: 'config' },
      { module: 'Discovery', func: 'import_local_components(cwd)', file: '_engine/cli/utils/discovery.py',
        detail: 'AST-scans .py files for @evaluator, @target, @dataset decorators. Imports matching modules to trigger registration.', tag: 'engine' },
      { module: 'Runner', func: 'ExperimentRunner.__init__(config)', file: '_engine/runner.py',
        detail: 'Builds runner with config. Selects LocalComputeBackend or FoundryComputeBackend based on compute setting.', tag: 'engine' },
      { module: 'Targets', func: 'TargetFactory.resolve(config)', file: '_engine/targets/target_factory.py',
        detail: 'Resolves each target: imports custom Python modules from TARGET_REGISTRY, or constructs Azure AI model clients.', tag: 'engine' },
      { module: 'Dataset', func: 'DatasetLoader.load(path)', file: '_engine/datasets.py',
        detail: 'Reads JSONL, validates required columns match evaluator column_mapping, returns list of row dicts.', tag: 'engine' },
      { module: 'Runner', func: 'generate_args_combinations()', file: '_engine/combination_utils.py',
        detail: 'Creates Cartesian product of targets x dataset rows. Produces the full execution matrix for parallel dispatch.', tag: 'engine' },
      { module: 'Executor', func: 'EvaluationExecutor.run_targets()', file: '_engine/evaluation/evaluation_executor.py',
        detail: 'ThreadPoolExecutor runs each target against every row in parallel. Rich progress bar tracks completion.', tag: 'engine' },
      { module: 'Executor', func: 'EvaluationExecutor.run_evaluators()', file: '_engine/evaluation/evaluation_executor.py',
        detail: 'Runs all evaluators against completed target outputs. Local evaluators run in-process; cloud evaluators batch API calls.', tag: 'evaluator' },
      { module: 'Aggregator', func: 'aggregate_results(rows)', file: '_engine/evaluation/evaluators_aggregator.py',
        detail: 'Collects per-row scores, computes mean/count aggregates, builds the summary dict for display and output.', tag: 'engine' },
      { module: 'Writer', func: 'ResultWriter.write(results)', file: '_engine/evaluation/output_formatter.py',
        detail: 'Saves eval_results.jsonl (per-row), summary.json (aggregates), metadata.json (run info) to output/quickstart/.', tag: 'engine' },
      { module: 'CLI', func: 'show_results_table(summary)', file: '_engine/cli/commands/run.py',
        detail: 'Renders Rich table with metrics and status. Prints the output directory path. Returns exit code 0.', tag: 'cli' }
    ]);


    // ── ev new (branching: basic vs Foundry) ─────────────────

    var evNewBasicOutput =
      'Created project: <span style="color:var(--accent)">my-eval</span>\n\n' +
      '  my-eval/\n' +
      '  <span style="color:var(--text-muted)">├──</span> pyproject.toml\n' +
      '  <span style="color:var(--text-muted)">├──</span> config.yaml\n' +
      '  <span style="color:var(--text-muted)">├──</span> data/\n' +
      '  <span style="color:var(--text-muted)">│   └──</span> sample_dataset.jsonl\n' +
      '  <span style="color:var(--text-muted)">├──</span> evaluators/\n' +
      '  <span style="color:var(--text-muted)">│   └──</span> word_count.py\n' +
      '  <span style="color:var(--text-muted)">└──</span> targets/\n' +
      '      <span style="color:var(--text-muted)">└──</span> baseline.py\n\n' +
      '<span style="color:var(--text-secondary)">Next steps:</span>\n' +
      '  cd my-eval\n' +
      '  uv sync\n' +
      '  ev run';

    var evNewFoundryOutput =
      'Created project: <span style="color:var(--accent)">my-eval</span> (with Azure AI Foundry)\n\n' +
      '  my-eval/\n' +
      '  <span style="color:var(--text-muted)">├──</span> pyproject.toml\n' +
      '  <span style="color:var(--text-muted)">├──</span> config.yaml\n' +
      '  <span style="color:var(--text-muted)">├──</span> data/\n' +
      '  <span style="color:var(--text-muted)">│   └──</span> sample_dataset.jsonl\n' +
      '  <span style="color:var(--text-muted)">├──</span> evaluators/\n' +
      '  <span style="color:var(--text-muted)">│   └──</span> word_count.py\n' +
      '  <span style="color:var(--text-muted)">├──</span> targets/\n' +
      '  <span style="color:var(--text-muted)">│   └──</span> baseline.py\n' +
      '  <span style="color:var(--text-muted)">└──</span> .env\n\n' +
      '<span style="color:var(--text-secondary)">Next steps:</span>\n' +
      '  cd my-eval\n' +
      '  uv sync\n' +
      '  ev cloud set\n' +
      '  ev run';

    var termNew = createBranchingTerminal({
      id: 'branch-ev-new',
      scenario: 'Choose the scaffolding mode:',
      choices: [
        {
          label: 'Basic Project',
          description: 'Local-only evaluation project',
          terminal: {
            command: 'ev new my-eval',
            output: evNewBasicOutput,
            steps: [
              { title: 'Parse Arguments', description: 'Reads project name from CLI args. Validates the name is a valid Python package identifier.',
                tag: 'cli', file: '_engine/cli/commands/new.py' },
              { title: 'Select Template', description: 'Chooses the basic template (no cloud config). Templates live in _engine/cli/templates/.',
                tag: 'engine', file: '_engine/cli/templates/' },
              { title: 'Scaffold Files', description: 'Copies template files to ./my-eval/. Renders Jinja2 templates with project name, creates directory structure. ' + deepDiveLink('configuration', 'Deep dive: Configuration System'),
                tag: 'engine', file: '_engine/cli/commands/new.py' },
              { title: 'Generate Sample Data', description: 'Creates sample_dataset.jsonl with 3 example rows containing question/answer/context fields.',
                tag: 'engine', file: '_engine/cli/templates/data/' },
              { title: 'Print Summary', description: 'Displays the directory tree and next steps instructions.',
                tag: 'cli', file: '_engine/cli/commands/new.py' }
            ],
            tips: [
              'The project uses <code>uv</code> for dependency management by default',
              'Edit <code>config.yaml</code> to add more evaluators and targets'
            ]
          }
        },
        {
          label: 'With Azure AI Foundry',
          description: 'Includes cloud configuration',
          terminal: {
            command: 'ev new my-eval --foundry',
            output: evNewFoundryOutput,
            steps: [
              { title: 'Parse Arguments', description: 'Reads project name and --foundry flag. Validates name is a valid Python package identifier.',
                tag: 'cli', file: '_engine/cli/commands/new.py' },
              { title: 'Select Foundry Template', description: 'Chooses the Foundry-enabled template which includes cloud section in config.yaml and .env file.',
                tag: 'engine', file: '_engine/cli/templates/' },
              { title: 'Scaffold Files', description: 'Creates project structure with .env for AZURE_AI_PROJECT_ENDPOINT and cloud-enabled config.yaml. ' + deepDiveLink('configuration', 'Deep dive: Configuration System'),
                tag: 'engine', file: '_engine/cli/commands/new.py' },
              { title: 'Generate Sample Data', description: 'Creates sample_dataset.jsonl with example rows.',
                tag: 'engine', file: '_engine/cli/templates/data/' },
              { title: 'Print Summary', description: 'Shows directory tree with .env file. Reminds to run ev cloud set for connection setup.',
                tag: 'cli', file: '_engine/cli/commands/new.py' }
            ],
            tips: [
              'Run <code>ev cloud set</code> next to configure your Foundry connection',
              'The <code>.env</code> file holds AZURE_AI_PROJECT_ENDPOINT -- add it to .gitignore'
            ]
          }
        }
      ]
    });


    // ── ev validate (simple terminal) ────────────────────────

    var termValidate = createInteractiveTerminal({
      id: 'cmd-ev-validate',
      command: 'ev validate -c config.yaml',
      output:
        'Validating config.yaml...\n\n' +
        '<span style="color:var(--text-muted)">╭─</span> <span style="color:var(--accent)">Validation Results</span> <span style="color:var(--text-muted)">──────────────────────────────────────╮</span>\n' +
        '<span style="color:var(--text-muted)">│</span> Status:      <span style="color:#3fb950">valid</span>                                    <span style="color:var(--text-muted)">│</span>\n' +
        '<span style="color:var(--text-muted)">│</span> Targets:     1 (baseline)                              <span style="color:var(--text-muted)">│</span>\n' +
        '<span style="color:var(--text-muted)">│</span> Evaluators:  2 (f1_score, answer_length)               <span style="color:var(--text-muted)">│</span>\n' +
        '<span style="color:var(--text-muted)">│</span> Dataset:     data/qa_data.jsonl                        <span style="color:var(--text-muted)">│</span>\n' +
        '<span style="color:var(--text-muted)">│</span> Warnings:    0                                         <span style="color:var(--text-muted)">│</span>\n' +
        '<span style="color:var(--text-muted)">│</span> Errors:      0                                         <span style="color:var(--text-muted)">│</span>\n' +
        '<span style="color:var(--text-muted)">╰────────────────────────────────────────────────────╯</span>',
      steps: [
        { title: 'Locate Config File', description: 'Resolves path from --config flag. Searches candidates: config.yaml, evals.yaml, experiment/config.yaml.',
          tag: 'cli', file: '_engine/cli/commands/validate.py' },
        { title: 'Parse YAML', description: 'Loads the YAML file and validates basic structure. Checks for required top-level keys: experiment, targets, evaluators. ' + deepDiveLink('configuration', 'Deep dive: Configuration System'),
          tag: 'config', file: '_engine/models/config.py' },
        { title: 'Validate Schema', description: 'Runs full schema validation: target types exist, evaluator names resolve, dataset path exists, column_mapping fields match.',
          tag: 'config', file: '_engine/cli/commands/validate.py' },
        { title: 'Check Component Resolution', description: 'Attempts to resolve each target and evaluator. Reports errors for missing custom modules or unknown built-in names. ' + deepDiveLink('evaluators', 'Deep dive: Evaluator Catalog') + ' ' + deepDiveLink('targets', 'Deep dive: Target System'),
          tag: 'engine', file: '_engine/discovery.py' },
        { title: 'Display Results', description: 'Prints the validation panel. On --json flag, outputs structured JSON instead of the Rich panel.',
          tag: 'cli', file: '_engine/cli/commands/validate.py' }
      ],
      tips: [
        'Add <code>--json</code> for machine-readable output in CI pipelines',
        'Validation catches missing files and typos before you run expensive evaluations'
      ]
    });


    // ── ev discover (simple terminal) ────────────────────────

    var termDiscover = createInteractiveTerminal({
      id: 'cmd-ev-discover',
      command: 'ev discover',
      output:
        '<span style="color:var(--accent)">Project Components</span>\n' +
        '  Targets:\n' +
        '    baseline              <span style="color:var(--text-muted)">(custom)</span>\n' +
        '  Evaluators:\n' +
        '    answer_length         <span style="color:var(--text-muted)">(custom)</span>\n\n' +
        '<span style="color:var(--accent)">Built-in Evaluators</span>\n' +
        '  coherence              <span style="color:var(--text-muted)">(cloud)</span>   Measure response coherence\n' +
        '  f1_score               <span style="color:var(--text-muted)">(local)</span>   F1 score metric\n' +
        '  relevance              <span style="color:var(--text-muted)">(cloud)</span>   LLM-based relevance\n' +
        '  groundedness           <span style="color:var(--text-muted)">(cloud)</span>   Response groundedness\n' +
        '  fluency                <span style="color:var(--text-muted)">(cloud)</span>   Measure response fluency\n' +
        '  similarity             <span style="color:var(--text-muted)">(cloud)</span>   Response similarity\n' +
        '  <span style="color:var(--text-muted)">...12 more</span>',
      steps: [
        { title: 'Scan Project Files', description: 'AST-scans all .py files in the current directory for @evaluator, @target, @dataset decorators. ' + deepDiveLink('custom', 'Deep dive: Custom Components'),
          tag: 'engine', file: '_engine/discovery.py' },
        { title: 'Query Registries', description: 'Reads EVALUATOR_REGISTRY and TARGET_REGISTRY for locally registered components. Tags each as (custom).',
          tag: 'engine', file: '_engine/decorators.py' },
        { title: 'List Built-in Evaluators', description: 'Enumerates all built-in evaluators from the SDK. Tags each as (local) or (cloud) based on compute requirements. ' + deepDiveLink('evaluators', 'Deep dive: Evaluator Catalog'),
          tag: 'engine', file: '_engine/decorators.py' },
        { title: 'Format Output', description: 'Groups by project vs built-in. Displays name, type tag, and description for each component.',
          tag: 'cli', file: '_engine/cli/commands/list_cmd.py' }
      ],
      tips: [
        'Custom components are found via AST scanning -- no manual registration needed',
        'Cloud evaluators require an Azure AI Foundry connection configured via <code>ev cloud set</code>'
      ]
    });


    // ── ev view (simple terminal) ────────────────────────────

    var termView = createInteractiveTerminal({
      id: 'cmd-ev-view',
      command: 'ev view --port 8765',
      output:
        'Found 2 experiments in output/\n\n' +
        'Starting results viewer...\n' +
        '  Server: <span style="color:var(--accent)">http://127.0.0.1:8765</span>\n' +
        '  Press Ctrl+C to stop',
      steps: [
        { title: 'Scan Output Directory', description: 'Walks output/ to find experiment result directories. Each must contain summary.json to be valid.',
          tag: 'engine', file: '_engine/cli/commands/view.py' },
        { title: 'Load Results', description: 'Reads summary.json and eval_results.jsonl from each experiment. Builds a combined dataset for the viewer.',
          tag: 'engine', file: '_engine/cli/commands/view.py' },
        { title: 'Start HTTP Server', description: 'Launches a local Flask/Starlette server on the specified port. Serves the viewer SPA with loaded results.',
          tag: 'engine', file: '_engine/cli/commands/view.py' },
        { title: 'Open Browser', description: 'Optionally opens the default browser to the viewer URL. Server runs until Ctrl+C.',
          tag: 'cli', file: '_engine/cli/commands/view.py' }
      ],
      tips: [
        'Use <code>--port</code> to change the default port if 8765 is in use',
        'The viewer shows per-row details, metric distributions, and experiment comparisons'
      ]
    });


    // ── ev clear (simple terminal) ───────────────────────────

    var termClear = createInteractiveTerminal({
      id: 'cmd-ev-clear',
      command: 'ev clear --keep-last 3',
      output:
        'Found 5 experiment runs in output/\n\n' +
        'Keeping 3 most recent:\n' +
        '  <span style="color:var(--accent)">quickstart_2024-01-15_14-30</span>\n' +
        '  <span style="color:var(--accent)">quickstart_2024-01-15_12-00</span>\n' +
        '  <span style="color:var(--accent)">quickstart_2024-01-14_18-45</span>\n\n' +
        '<span style="color:var(--text-muted)">Removed 2 old runs (freed 4.2 MB)</span>',
      steps: [
        { title: 'Parse Options', description: 'Reads --keep-last flag (default: 0 = remove all). Also supports --older-than for date-based cleanup.',
          tag: 'cli', file: '_engine/cli/commands/clear.py' },
        { title: 'Enumerate Runs', description: 'Lists all experiment run directories in output/. Sorts by creation timestamp descending.',
          tag: 'engine', file: '_engine/cli/commands/clear.py' },
        { title: 'Select for Removal', description: 'Keeps the N most recent runs. Marks the rest for deletion. Calculates total disk space to be freed.',
          tag: 'engine', file: '_engine/cli/commands/clear.py' },
        { title: 'Delete and Report', description: 'Removes selected directories. Prints kept runs, removed count, and freed disk space.',
          tag: 'cli', file: '_engine/cli/commands/clear.py' }
      ],
      tips: [
        'Without <code>--keep-last</code>, all runs are removed',
        'Use <code>--dry-run</code> to preview what would be deleted without removing anything'
      ]
    });


    // ── ev cloud set (simple terminal) ───────────────────────

    var termCloud = createInteractiveTerminal({
      id: 'cmd-ev-cloud-set',
      command: 'ev cloud set',
      output:
        '<span style="color:var(--accent)">Azure AI Foundry Configuration</span>\n\n' +
        '  Foundry project: https://my-project.services.ai.azure.com/...\n' +
        '  Default deployment: gpt-4.1-mini\n\n' +
        '  Testing connection... <span style="color:#3fb950">connected</span>\n\n' +
        'Updated config.yaml with cloud configuration.',
      steps: [
        { title: 'Read Current Config', description: 'Loads existing config.yaml if present. Checks for existing cloud section.',
          tag: 'config', file: '_engine/cli/commands/cloud.py' },
        { title: 'Prompt for Endpoint', description: 'If not provided via flags, prompts interactively for the Azure AI Foundry project endpoint URL.',
          tag: 'cli', file: '_engine/cli/commands/cloud.py' },
        { title: 'Test Connection', description: 'Authenticates using DefaultAzureCredential. Validates the endpoint responds and the deployment exists.',
          tag: 'engine', file: '_engine/foundry_compute.py' },
        { title: 'Update Config', description: 'Writes cloud section to config.yaml: project_endpoint, default_deployment, authentication method.',
          tag: 'config', file: '_engine/cli/commands/cloud.py' }
      ],
      tips: [
        'Uses DefaultAzureCredential -- make sure you are logged in via <code>az login</code>',
        'You can also pass <code>--endpoint</code> and <code>--deployment</code> flags to skip prompts'
      ]
    });


    // ── ev target add (branching) ────────────────────────────

    var termTargetAdd = createBranchingTerminal({
      id: 'branch-ev-target-add',
      scenario: 'Choose the target type to add:',
      choices: [
        {
          label: 'Custom Target',
          description: 'Python function target',
          terminal: {
            command: 'ev target add --name my_model --type custom',
            output:
              'Created target file: targets/my_model.py\n' +
              'Updated config.yaml\n\n' +
              '<span style="color:var(--text-secondary)">Next steps:</span>\n' +
              '  1. Implement the target function in targets/my_model.py\n' +
              '  2. Run: ev run',
            steps: [
              { title: 'Parse Arguments', description: 'Reads --name and --type flags. Validates name is a valid Python identifier.',
                tag: 'cli', file: '_engine/cli/commands/target.py' },
              { title: 'Generate Target File', description: 'Creates targets/my_model.py from template with @target decorator and placeholder function. ' + deepDiveLink('targets', 'Deep dive: Target System'),
                tag: 'engine', file: '_engine/cli/commands/target.py' },
              { title: 'Update Config', description: 'Adds the target entry to config.yaml targets section.',
                tag: 'config', file: '_engine/cli/commands/target.py' }
            ],
            tips: ['Custom targets are Python functions decorated with <code>@target</code>']
          }
        },
        {
          label: 'Azure AI Model',
          description: 'Cloud model endpoint',
          terminal: {
            command: 'ev target add --name my_model --type azure_ai_model',
            output:
              'Added target \'<span style="color:var(--accent)">my_model</span>\' to config.yaml\n\n' +
              '  targets:\n' +
              '    - name: my_model\n' +
              '      type: azure_ai_model\n' +
              '      connection_name: default\n\n' +
              '<span style="color:var(--text-secondary)">Next steps:</span>\n' +
              '  1. Update target configuration in config.yaml\n' +
              '  2. Run: ev run',
            steps: [
              { title: 'Parse Arguments', description: 'Reads --name and --type azure_ai_model. Validates Azure AI Foundry connection exists.',
                tag: 'cli', file: '_engine/cli/commands/target.py' },
              { title: 'Resolve Connection', description: 'Checks for configured Foundry connection. Uses connection_name: default unless overridden. ' + deepDiveLink('targets', 'Deep dive: Target System'),
                tag: 'engine', file: '_engine/cli/commands/target.py' },
              { title: 'Update Config', description: 'Adds azure_ai_model target entry to config.yaml with connection_name and deployment settings.',
                tag: 'config', file: '_engine/cli/commands/target.py' }
            ],
            tips: ['Requires an active Azure AI Foundry connection. Run <code>ev cloud set</code> first.']
          }
        },
        {
          label: 'Azure AI Agent',
          description: 'Agent-based target',
          terminal: {
            command: 'ev target add --name my_agent --type azure_ai_agent',
            output:
              'Added target \'<span style="color:var(--accent)">my_agent</span>\' to config.yaml\n\n' +
              '  targets:\n' +
              '    - name: my_agent\n' +
              '      type: azure_ai_agent\n' +
              '      agent_id: &lt;your-agent-id&gt;\n\n' +
              '<span style="color:var(--text-secondary)">Next steps:</span>\n' +
              '  1. Set the agent_id in config.yaml\n' +
              '  2. Run: ev run',
            steps: [
              { title: 'Parse Arguments', description: 'Reads --name and --type azure_ai_agent.',
                tag: 'cli', file: '_engine/cli/commands/target.py' },
              { title: 'Update Config', description: 'Adds azure_ai_agent target entry with placeholder agent_id.',
                tag: 'config', file: '_engine/cli/commands/target.py' }
            ],
            tips: ['Replace the placeholder agent_id with your deployed agent identifier']
          }
        }
      ]
    });


    // ── ev evaluator add (branching) ─────────────────────────

    var termEvalAdd = createBranchingTerminal({
      id: 'branch-ev-eval-add',
      scenario: 'Choose the evaluator type:',
      choices: [
        {
          label: 'Empty / Custom',
          description: 'Create a new evaluator from scratch',
          terminal: {
            command: 'ev evaluator add --type empty --name accuracy',
            output:
              'Created evaluator file: evaluators/<span style="color:var(--accent)">accuracy_evaluator.py</span>\n' +
              'Updated config.yaml\n\n' +
              '<span style="color:var(--text-secondary)">Next steps:</span>\n' +
              '  1. Implement compute() in accuracy_evaluator.py\n' +
              '  2. Update mapping in config.yaml\n' +
              '  3. Run: ev run',
            steps: [
              { title: 'Parse Arguments', description: 'Reads --type empty and --name accuracy. Validates name is a valid Python identifier.',
                tag: 'cli', file: '_engine/cli/commands/evaluator_cmd.py' },
              { title: 'Generate Evaluator File', description: 'Creates evaluators/accuracy_evaluator.py from template with @evaluator decorator and placeholder compute() method. ' + deepDiveLink('custom', 'Deep dive: Custom Components'),
                tag: 'engine', file: '_engine/cli/commands/evaluator_cmd.py' },
              { title: 'Update Config', description: 'Adds evaluator entry to config.yaml evaluators section with column_mapping template.',
                tag: 'config', file: '_engine/cli/commands/evaluator_cmd.py' }
            ],
            tips: [
              'The compute() method receives mapped columns and returns a score dict',
              'Use <code>ev validate</code> to check your column_mapping after editing config.yaml'
            ]
          }
        },
        {
          label: 'Built-in Evaluator',
          description: 'Add a pre-built evaluator from the SDK',
          terminal: {
            command: 'ev evaluator add --type builtin --name coherence',
            output:
              'Added built-in evaluator \'<span style="color:var(--accent)">coherence</span>\' to config.yaml\n\n' +
              '  evaluators:\n' +
              '    - name: coherence\n' +
              '      type: builtin\n' +
              '      column_mapping:\n' +
              '        query: ${data.query}\n' +
              '        response: ${data.response}\n\n' +
              '<span style="color:var(--text-secondary)">Note:</span> coherence is a <span style="color:var(--text-muted)">(cloud)</span> evaluator.\n' +
              'Requires Azure AI Foundry connection.',
            steps: [
              { title: 'Parse Arguments', description: 'Reads --type builtin and --name coherence. Validates the name exists in the built-in evaluator list.',
                tag: 'cli', file: '_engine/cli/commands/evaluator_cmd.py' },
              { title: 'Resolve Evaluator', description: 'Looks up coherence in EVALUATOR_REGISTRY. Determines it requires cloud compute and appropriate column_mapping. ' + deepDiveLink('evaluators', 'Deep dive: Evaluator Catalog'),
                tag: 'engine', file: '_engine/decorators.py' },
              { title: 'Update Config', description: 'Adds evaluator entry with auto-generated column_mapping based on the evaluator\'s required inputs.',
                tag: 'config', file: '_engine/cli/commands/evaluator_cmd.py' }
            ],
            tips: [
              'Cloud evaluators (coherence, relevance, groundedness) need <code>ev cloud set</code> configured',
              'Local evaluators (f1_score) run without any cloud connection'
            ]
          }
        }
      ]
    });


    // ── ev dataset add (branching) ───────────────────────────

    var termDatasetAdd = createBranchingTerminal({
      id: 'branch-ev-dataset-add',
      scenario: 'Choose how to create your dataset:',
      choices: [
        {
          label: 'Create JSONL',
          description: 'New JSONL dataset with sample records',
          terminal: {
            command: 'ev dataset add --type jsonl --name test_data',
            output:
              'Created dataset: data/<span style="color:var(--accent)">test_data.jsonl</span> (3 sample records)\n' +
              'Updated config.yaml\n\n' +
              '<span style="color:#d29922">Warning:</span> This is placeholder data for testing only.\n' +
              'Replace with your own data for real evaluations.',
            steps: [
              { title: 'Parse Arguments', description: 'Reads --type jsonl and --name test_data. Validates no file collision.',
                tag: 'cli', file: '_engine/cli/commands/dataset.py' },
              { title: 'Generate Sample Data', description: 'Creates data/test_data.jsonl with 3 placeholder records containing typical columns: query, response, context, ground_truth.',
                tag: 'engine', file: '_engine/cli/commands/dataset.py' },
              { title: 'Update Config', description: 'Sets dataset path in config.yaml to data/test_data.jsonl.',
                tag: 'config', file: '_engine/cli/commands/dataset.py' }
            ],
            tips: ['Sample data uses typical QA fields -- customize columns to match your evaluators']
          }
        },
        {
          label: 'Create CSV',
          description: 'New CSV dataset with sample records',
          terminal: {
            command: 'ev dataset add --type csv --name test_data',
            output:
              'Created dataset: data/<span style="color:var(--accent)">test_data.csv</span> (3 sample records)\n' +
              'Updated config.yaml\n\n' +
              '<span style="color:#d29922">Warning:</span> This is placeholder data for testing only.\n' +
              'Replace with your own data for real evaluations.',
            steps: [
              { title: 'Parse Arguments', description: 'Reads --type csv and --name test_data.',
                tag: 'cli', file: '_engine/cli/commands/dataset.py' },
              { title: 'Generate CSV', description: 'Creates data/test_data.csv with header row and 3 sample rows.',
                tag: 'engine', file: '_engine/cli/commands/dataset.py' },
              { title: 'Update Config', description: 'Sets dataset path in config.yaml to data/test_data.csv.',
                tag: 'config', file: '_engine/cli/commands/dataset.py' }
            ],
            tips: ['CSV datasets are auto-detected by file extension']
          }
        },
        {
          label: 'Import Existing',
          description: 'Point to an existing data file',
          terminal: {
            command: 'ev dataset add --path ./my-data/eval_set.jsonl',
            output:
              'Validated dataset: ./my-data/eval_set.jsonl (47 records)\n' +
              'Updated config.yaml\n\n' +
              'Columns found: query, response, context, ground_truth',
            steps: [
              { title: 'Parse Arguments', description: 'Reads --path flag. Resolves to absolute path.',
                tag: 'cli', file: '_engine/cli/commands/dataset.py' },
              { title: 'Validate File', description: 'Reads the file, validates format (JSONL or CSV), counts records, extracts column names.',
                tag: 'engine', file: '_engine/cli/commands/dataset.py' },
              { title: 'Update Config', description: 'Sets dataset path in config.yaml to the provided path.',
                tag: 'config', file: '_engine/cli/commands/dataset.py' }
            ],
            tips: ['Importing validates the file but does not copy it -- the path is used as-is']
          }
        }
      ]
    });


    // ── Build command navigator ──────────────────────────────

    var commands = [
      { name: 'ev run',           terminal: termRun + evRunCallTrace },
      { name: 'ev new',           terminal: termNew },
      { name: 'ev validate',      terminal: termValidate },
      { name: 'ev discover',      terminal: termDiscover },
      { name: 'ev view',          terminal: termView },
      { name: 'ev clear',         terminal: termClear },
      { name: 'ev cloud set',     terminal: termCloud },
      { name: 'ev target add',    terminal: termTargetAdd },
      { name: 'ev evaluator add', terminal: termEvalAdd },
      { name: 'ev dataset add',   terminal: termDatasetAdd }
    ];

    var navigatorHtml = createCommandNavigator(commands, 'cli-commands');

    cliEl.innerHTML =
      '<h2 class="section-title">Interactive CLI Deep Dive</h2>' +
      '<p style="color:var(--text-secondary);margin-bottom:24px">' +
      'Explore each CLI command with realistic output and step-by-step execution flow.' +
      '</p>' +
      createInfoCard(
        'How to use',
        'Use <strong>Next / Previous</strong> to navigate between commands. ' +
        'For branching commands (ev run, ev new, ev target add, ev evaluator add, ev dataset add), ' +
        'click a choice button to see the terminal output for that execution path. ' +
        'Expand <strong>Behind the Scenes</strong> to see what the engine does at every step.',
        'info'
      ) +
      navigatorHtml;

    // Initialize all interactive behaviors
    setTimeout(function() {
      initTerminalAnimations();
    }, 100);
  }

  // ────────────────────────────────────────────────────────────
  // SECTION 2 -- Learning Roadmap (#roadmap)
  // ────────────────────────────────────────────────────────────
  var roadmapEl = document.getElementById('roadmap');
  if (roadmapEl) {

    var stops = [
      {
        id: 'roadmap-arch',
        title: '1. Architecture Overview',
        description: 'Understand the high-level structure: directory layout, component registries, compute abstraction, and the data model hierarchy.',
        section: 'architecture',
        status: 'completed'
      },
      {
        id: 'roadmap-config',
        title: '2. Configuration System',
        description: 'Learn the config.yaml schema -- experiment name, targets, evaluators, dataset, output, and cloud sections. Master environment variable interpolation.',
        section: 'configuration',
        status: 'completed'
      },
      {
        id: 'roadmap-cli-basics',
        title: '3. CLI Basics',
        description: 'Get comfortable with ev new (scaffolding), ev validate (config checks), and ev discover (component listing). These are your daily-driver commands.',
        section: 'cli',
        status: 'current'
      },
      {
        id: 'roadmap-running',
        title: '4. Running Evaluations',
        description: 'Deep dive into ev run: option parsing, config loading, backend selection, parallel execution, and result aggregation.',
        section: 'interactive-cli',
        status: 'upcoming'
      },
      {
        id: 'roadmap-engine',
        title: '5. Engine Flow',
        description: 'Trace the full execution path from ExperimentRunner through ComputeBackend to EvaluationExecutor. Understand how rows flow through the pipeline.',
        section: 'engine-flow',
        status: 'upcoming'
      },
      {
        id: 'roadmap-evaluators',
        title: '6. Evaluators',
        description: 'Explore built-in evaluators (f1_score, coherence, relevance) and learn to create custom ones with the @evaluator decorator.',
        section: 'evaluators',
        status: 'upcoming'
      },
      {
        id: 'roadmap-targets',
        title: '7. Targets and Expansion',
        description: 'Understand target types, the TargetFactory, and Cartesian expansion via generate_args_combinations() for multi-parameter sweeps.',
        section: 'targets',
        status: 'upcoming'
      },
      {
        id: 'roadmap-custom',
        title: '8. Custom Components',
        description: 'Build your own evaluators and targets using decorators. Learn how AST-based discovery finds and registers your components automatically.',
        section: 'custom',
        status: 'upcoming'
      },
      {
        id: 'roadmap-cloud',
        title: '9. Cloud Execution',
        description: 'Configure Azure AI Foundry for remote evaluation. Understand the FoundryComputeBackend, authentication, and how results sync back locally.',
        section: 'engine-flow',
        status: 'upcoming'
      },
      {
        id: 'roadmap-advanced',
        title: '10. Advanced Topics',
        description: 'OpenTelemetry tracing, the results viewer, CI/CD integration, and performance tuning for large-scale evaluations.',
        section: 'cli',
        status: 'upcoming'
      }
    ];

    var roadmapHtml = createRoadmap(stops);

    roadmapEl.innerHTML =
      '<div class="hero-banner">' +
        '<h2 class="section-title">Learn the Evaluation Engine</h2>' +
        '<p class="hero-desc">The Azure AI Evaluation Engine runs your AI models against datasets, scores them with evaluators, and produces comparison reports — all from one <code>ev run</code> command. Think of it as a test harness for AI quality.</p>' +
        '<div class="hero-actions">' +
          '<a class="hero-btn primary" onclick="navigateTo(\'interactive-cli\');return false;">Start the CLI Explorer</a>' +
          '<a class="hero-btn secondary" onclick="navigateTo(\'architecture\');return false;">Read the Architecture</a>' +
        '</div>' +
      '</div>' +
      '<h2 class="section-title">Learning Roadmap</h2>' +
      '<p style="color:var(--text-secondary);margin-bottom:24px">' +
      'Start with the Learning Roadmap to understand the big picture. ' +
      'Then explore the CLI Explorer -- our interactive walkthrough of every command. ' +
      'Each step links to Deep Dives for detailed explanations. ' +
      'Topics build on each other -- start at the top and work your way down.' +
      '</p>' +
      roadmapHtml;
  }
}

// Bootstrap
document.addEventListener('DOMContentLoaded', initInteractiveCliContent);
