/* ============================================================
   Content: CLI, Targets & Custom Components
   Populates sections: cli, targets, custom
   ============================================================ */

function initCliTargetsContent() {

  // ════════════════════════════════════════════════════════════
  // SECTION 1: CLI Commands Reference
  // ════════════════════════════════════════════════════════════
  document.getElementById('cli').innerHTML = `
    <h2>CLI Commands Reference</h2>
    <p class="section-intro">The <code>ev</code> CLI is the primary interface for the Azure AI Evaluation Engine. Built with Click, it manages evaluation runs, project scaffolding, result viewing, and component discovery.</p>

    <!-- ev run -->
    <h3 id="cli-run">ev run -- Execute Evaluations</h3>
    <p>The core command. Loads a YAML config, resolves targets, evaluators, and datasets, then orchestrates the full evaluation pipeline via <code>ExperimentRunner</code>.</p>

    <h4>Click Decorator Signature</h4>
    ${createCodeBlock(`@click.command()
@click.option("--path", "-p", default=".", type=click.Path(exists=True))
@click.option("--config", "-c", default=None)
@click.option("--dataset", "-d", "dataset_path", required=False, default=None)
@click.option("--env", "-e", default=".env")
@click.option("--remote", "-r", is_flag=True)
@click.option("--targets", "-t", required=False, default=None)
@click.option("--auto-approve", "-y", is_flag=True)
@click.option("--output", "-o", default=None)
@click.option("--stream-remote-logs", is_flag=True, default=False)
@click.option("--trace/--no-trace", default=None)
@click.option("--trace-endpoint", default=None)
@click.option("--trace-headers", default=None)
@click.option("--plain", is_flag=True, expose_value=False, is_eager=True)`, 'python', { filePath: 'ev_cli/commands/run.py', title: 'ev run -- Click Options' })}

    ${createTable(
      ['Option', 'Short', 'Default', 'Description'],
      [
        ['<code>--path</code>', '<code>-p</code>', '<code>.</code>', 'Working directory (must exist)'],
        ['<code>--config</code>', '<code>-c</code>', 'auto-detect', 'Config file path'],
        ['<code>--dataset</code>', '<code>-d</code>', '<code>None</code>', 'Dataset file override'],
        ['<code>--env</code>', '<code>-e</code>', '<code>.env</code>', 'Environment file path'],
        ['<code>--remote</code>', '<code>-r</code>', '<code>False</code>', 'Run on cloud compute backend'],
        ['<code>--targets</code>', '<code>-t</code>', '<code>None</code>', 'Comma-separated target filter'],
        ['<code>--auto-approve</code>', '<code>-y</code>', '<code>False</code>', 'Skip confirmation prompts'],
        ['<code>--output</code>', '<code>-o</code>', '<code>None</code>', 'Output directory override'],
        ['<code>--stream-remote-logs</code>', '', '<code>False</code>', 'Stream logs from remote compute'],
        ['<code>--trace/--no-trace</code>', '', 'auto', 'Enable or disable OpenTelemetry tracing'],
        ['<code>--trace-endpoint</code>', '', '<code>None</code>', 'OTLP HTTP endpoint URL'],
        ['<code>--trace-headers</code>', '', '<code>None</code>', 'OTLP auth headers'],
        ['<code>--plain</code>', '', '<code>False</code>', 'Plain output (no Rich formatting)'],
      ]
    )}

    <h4>Execution Flow</h4>
    ${createCallTrace('ev run -- Execution Trace', [
      { module: 'run.py', func: 'Auto-detect config file', file: 'ev_cli/commands/run.py', detail: 'Searches for config.yaml, evals.yaml, experiment/config.yaml in order', tag: 'cli' },
      { module: 'run.py', func: 'Parse --targets filter', file: 'ev_cli/commands/run.py', detail: 'Splits comma-separated target names for selective execution', tag: 'cli' },
      { module: 'run.py', func: 'Configure tracing env vars', file: 'ev_cli/commands/run.py', detail: 'Sets OTEL_EXPORTER_OTLP_ENDPOINT, OTEL_EXPORTER_OTLP_HEADERS if --trace is enabled', tag: 'engine' },
      { module: 'config', func: 'load_config_safe()', file: 'ev_cli/config/loader.py', detail: 'Parses YAML, resolves env vars, validates schema against Config model', tag: 'engine' },
      { module: 'run.py', func: 'Show Rich panel with experiment info', file: 'ev_cli/commands/run.py', detail: 'Displays experiment name, targets, evaluators, dataset path in a Rich formatted panel', tag: 'cli' },
      { module: 'runner', func: 'ExperimentRunner.run()', file: '_engine/runner.py', detail: 'Orchestrates target invocation, evaluator execution, result aggregation', tag: 'engine' },
      { module: 'run.py', func: 'Handle JobStatus result', file: 'ev_cli/commands/run.py', detail: 'Checks for JobStatus.COMPLETED or JobStatus.FAILED and exits accordingly', tag: 'cli' },
    ])}

    <p><strong>Example usage:</strong></p>
    ${createCodeBlock(`# Run with explicit config and tracing
ev run -c configs/model_comparison.yaml --trace

# Run only specific targets
ev run -t gpt-4o,gpt-4o-mini

# Remote execution with log streaming
ev run --remote --stream-remote-logs -y`, 'bash', { title: 'ev run -- Examples' })}

    ${createInfoCard('Config Auto-Detection', 'When <code>--config</code> is omitted, the CLI searches the working directory for <code>config.yaml</code>, <code>evals.yaml</code>, and <code>experiment/config.yaml</code> in that order.', 'info')}

    ${createInfoCard('Remote Execution', 'Use <code>--remote</code> to offload evaluation to Azure cloud compute. Combine with <code>--stream-remote-logs</code> to see real-time progress in the terminal.', 'tip')}

    <!-- ev new -->
    <h3 id="cli-new">ev new -- Create New Project</h3>
    <p>Scaffolds a new evaluation project with directory structure, sample config, and optional targets and evaluators.</p>

    <h4>Click Decorator Signature</h4>
    ${createCodeBlock(`@click.command()
@click.argument("name", required=False)
@click.option("--description", "-d", default="AI model evaluation experiment")
@click.option("--output", "-o", default=".")
@click.option("--from-source", type=click.Path(exists=True, file_okay=False))
@click.option("--from-git", is_flag=True)
@click.option("--interactive", "-i", is_flag=True)
@click.option("--force", "-f", is_flag=True)`, 'python', { filePath: 'ev_cli/commands/new.py', title: 'ev new -- Click Options' })}

    ${createTable(
      ['Option', 'Short', 'Default', 'Description'],
      [
        ['<code>NAME</code> (argument)', '', 'directory name', 'Project name'],
        ['<code>--description</code>', '<code>-d</code>', '<code>"AI model evaluation experiment"</code>', 'Project description'],
        ['<code>--output</code>', '<code>-o</code>', '<code>.</code>', 'Output directory'],
        ['<code>--from-source</code>', '', '<code>None</code>', 'Link to local engine source (development)'],
        ['<code>--from-git</code>', '', '<code>False</code>', 'Clone project template from Git'],
        ['<code>--interactive</code>', '<code>-i</code>', '<code>False</code>', 'Interactive setup wizard'],
        ['<code>--force</code>', '<code>-f</code>', '<code>False</code>', 'Overwrite existing directory'],
      ]
    )}

    <p><strong>Example usage:</strong></p>
    ${createCodeBlock(`# Interactive project creation
ev new my-eval-project -i

# Create with custom description
ev new safety-eval -d "Safety evaluation for chatbot v2"

# Scaffold from local engine source (for development)
ev new dev-project --from-source ../azure-ai-evaluation`, 'bash', { title: 'ev new -- Examples' })}

    <!-- ev validate -->
    <h3 id="cli-validate">ev validate -- Validate Configuration</h3>
    <p>Validates a YAML config without running the evaluation. Checks schema, resolves references, and reports errors.</p>

    <h4>Click Decorator Signature</h4>
    ${createCodeBlock(`@click.command()
@click.option("--config", "-c", default=None)
@click.option("--env", "-e", default=".env")
@click.option("--json", "output_json", is_flag=True)`, 'python', { filePath: 'ev_cli/commands/validate.py', title: 'ev validate -- Click Options' })}

    ${createTable(
      ['Option', 'Short', 'Default', 'Description'],
      [
        ['<code>--config</code>', '<code>-c</code>', 'auto-detect', 'Config file path'],
        ['<code>--env</code>', '<code>-e</code>', '<code>.env</code>', 'Environment file path'],
        ['<code>--json</code>', '', '<code>False</code>', 'Output validation results as JSON'],
      ]
    )}

    <p><strong>Example JSON output:</strong></p>
    ${createCodeBlock(`{
  "valid": true,
  "config_path": "config.yaml",
  "targets": ["my_agent"],
  "evaluators": ["coherence", "groundedness"],
  "dataset": "data/questions.jsonl",
  "warnings": [],
  "errors": []
}`, 'json', { title: 'Validation JSON output' })}

    <!-- ev view -->
    <h3 id="cli-view">ev view -- View Results in Browser</h3>
    <p>Launches a local HTTP server to browse evaluation results interactively.</p>

    <h4>Click Decorator Signature</h4>
    ${createCodeBlock(`@click.command()
@click.option("--port", "-p", "port", default=8765)
@click.option("--no-browser", is_flag=True)`, 'python', { filePath: 'ev_cli/commands/view.py', title: 'ev view -- Click Options' })}

    ${createTable(
      ['Option', 'Short', 'Default', 'Description'],
      [
        ['<code>--port</code>', '<code>-p</code>', '<code>8765</code>', 'HTTP server port'],
        ['<code>--no-browser</code>', '', '<code>False</code>', 'Do not auto-open browser'],
      ]
    )}

    <p><strong>Example usage:</strong></p>
    ${createCodeBlock(`# View results on default port
ev view

# Custom port, no auto-open
ev view -p 9000 --no-browser`, 'bash', { title: 'ev view -- Examples' })}

    <!-- ev discover -->
    <h3 id="cli-discover">ev discover -- List Available Components</h3>
    <p>Scans the working directory and engine registry to list all discovered evaluators, targets, and datasets. Uses AST-based scanning to find decorated classes.</p>

    ${createCodeBlock(`# List all discovered components
ev discover

# Example output:
# Evaluators:
#   - coherence          (built-in)
#   - groundedness       (built-in)
#   - word_count         (custom, evaluators/word_count.py)
#
# Targets:
#   - my_agent           (custom, targets/agent.py)
#
# Datasets:
#   - qa_dataset         (custom, datasets/qa.py)`, 'bash', { title: 'ev discover -- Usage' })}

    <!-- ev eval -->
    <h3 id="cli-eval">ev eval -- Quick Single-Evaluator Run</h3>
    <p>Runs a single evaluator against provided data without requiring a full config file. Useful for quick testing and iteration.</p>

    ${createCodeBlock(`# Quick evaluation without a config file
ev eval coherence --dataset data/responses.jsonl

# Evaluate with specific parameters
ev eval groundedness --dataset data/grounded.jsonl`, 'bash', { title: 'ev eval -- Examples' })}

    <!-- ev init-config -->
    <h3 id="cli-init-config">ev init-config -- Generate Config from Project</h3>
    <p>Generates a <code>config.yaml</code> from an existing project structure by scanning for targets, evaluators, and datasets already present in the directory.</p>

    ${createCodeBlock(`# Generate config from current directory
ev init-config

# Writes config.yaml based on discovered:
#   - targets/ directory contents
#   - evaluators/ directory contents
#   - datasets/ directory contents`, 'bash', { title: 'ev init-config -- Usage' })}

    <!-- ev env -->
    <h3 id="cli-env">ev env -- Show Environment Information</h3>
    <p>Displays diagnostic information about the current environment: Python version, installed packages, engine paths, and Azure configuration.</p>

    ${createCodeBlock(`ev env

# Example output:
# Python:     3.11.9
# Engine:     azure-ai-evaluation 1.4.0
# Platform:   macOS-14.5-arm64
# Packages:   promptflow-core==1.14.0, openai==1.40.0
# Config:     ~/.ev/config.json`, 'bash', { title: 'ev env -- Usage' })}

    <!-- ev convert -->
    <h3 id="cli-convert">ev convert -- Convert Between Formats</h3>
    <p>Converts between evaluation data formats (e.g., JSONL to CSV, or between different evaluation result schemas).</p>

    ${createCodeBlock(`# Convert JSONL dataset to CSV
ev convert --input data.jsonl --output data.csv`, 'bash', { title: 'ev convert -- Usage' })}

    <!-- ev login -->
    <h3 id="cli-login">ev login -- Azure Authentication</h3>
    <p>Authenticates with Azure for remote evaluation and Azure AI Foundry integration. Wraps the Azure Identity credential flow.</p>

    ${createCodeBlock(`# Interactive Azure login
ev login

# Verify authentication status
ev login --check`, 'bash', { title: 'ev login -- Usage' })}

    <h3 id="cli-summary">Command Summary</h3>
    ${createTable(
      ['Command', 'Purpose', 'Key Options'],
      [
        ['<code>ev run</code>', 'Execute evaluation pipeline', '<code>-c, -t, -r, --trace</code>'],
        ['<code>ev new</code>', 'Scaffold new project', '<code>-i, -f, --from-source</code>'],
        ['<code>ev validate</code>', 'Validate config without running', '<code>-c, --json</code>'],
        ['<code>ev view</code>', 'Browser-based result viewer', '<code>-p, --no-browser</code>'],
        ['<code>ev discover</code>', 'List discovered components', ''],
        ['<code>ev eval</code>', 'Quick single-evaluator run', '<code>--dataset</code>'],
        ['<code>ev init-config</code>', 'Generate config from project', ''],
        ['<code>ev env</code>', 'Show environment info', ''],
        ['<code>ev convert</code>', 'Convert data formats', '<code>--input, --output</code>'],
        ['<code>ev login</code>', 'Azure authentication', '<code>--check</code>'],
      ]
    )}

  `;

  // ════════════════════════════════════════════════════════════
  // SECTION 2: Targets System
  // ════════════════════════════════════════════════════════════
  document.getElementById('targets').innerHTML = `
    <h2>Targets System</h2>
    <p class="section-intro">Targets represent the systems under evaluation -- your models, agents, or APIs. The engine uses the <code>TargetFactory</code> to resolve YAML config into concrete target instances, supports Cartesian expansion of arguments, and maps dataset fields to target parameters.</p>

    <h3 id="target-types">Target Types</h3>
    ${createTable(
      ['Type', 'Description', 'Key Config Fields'],
      [
        ['<code>custom</code>', 'User-defined via <code>@target</code> decorator, registered in the global registry', '<code>name</code> (registry key), <code>args</code> (constructor kwargs)'],
        ['<code>azure_ai_model</code>', 'Azure OpenAI model deployment. Engine calls the chat completion API directly.', '<code>deployment_name</code>, <code>connection</code> (Azure endpoint + key)'],
        ['<code>azure_ai_agent</code>', 'Azure AI Foundry agent with tools and memory.', '<code>agent_name</code>, <code>agent_version</code>, <code>azure_ai_project</code>'],
      ]
    )}

    <h3 id="target-factory">TargetFactory -- Config to Instances</h3>
    <p>The <code>TargetFactory</code> reads the <code>targets</code> section of the YAML config, expands Cartesian products for list-valued arguments, and instantiates each variant.</p>

    ${createCodeBlock(`class TargetFactory:
    def __init__(self, config: Config, registry: Dict):
        self._config = config
        self._registry = registry

    def create_targets(self) -> List[TargetInstance]:
        targets = []
        for target_config in self._config.experiment.targets:
            expanded = expand_combinations(target_config)
            for variant in expanded:
                instance = self._create_single(variant)
                targets.append(instance)
        return targets

    def _create_single(self, config: TargetVariantConfig) -> TargetInstance:
        if config.type == "custom":
            cls = self._registry.get(config.name)
            return cls(**config.args)
        elif config.type == "azure_ai_model":
            return AzureAIModelTarget(config)
        elif config.type == "azure_ai_agent":
            return AzureAIAgentTarget(config)`, 'python', { filePath: '_engine/target_factory.py', title: 'TargetFactory -- Core Logic' })}

    ${createCallTrace('TargetFactory Execution Flow', [
      { module: 'TargetFactory', func: 'create_targets()', file: '_engine/target_factory.py', tag: 'engine',
        detail: 'Iterates over config.experiment.targets entries from the YAML config.' },
      { module: 'combination_utils', func: 'expand_combinations(target_config)', file: '_engine/combination_utils.py', tag: 'engine',
        detail: 'Detects list-valued args and computes Cartesian product of all combinations.' },
      { module: 'TargetFactory', func: '_create_single(variant)', file: '_engine/target_factory.py', tag: 'engine',
        detail: 'Dispatches by config.type: looks up registry for custom, or constructs built-in target class.' },
      { module: 'Registry', func: 'registry.get(config.name)', file: '_engine/decorators.py', tag: 'data',
        detail: 'For custom type: retrieves the class registered via @target(name=...) decorator.' },
      { module: 'Target', func: 'cls(**config.args)', file: 'targets/*.py', tag: 'target',
        detail: 'Constructs the target instance, passing expanded args as keyword arguments.' },
    ])}

    <h3 id="cartesian-expansion">Cartesian Product Expansion</h3>
    <p>When target arguments contain lists, <code>expand_combinations()</code> generates every combination. This is how you compare multiple models or parameter settings in a single run.</p>

    ${createCodeBlock(`# config.yaml -- list-valued args trigger Cartesian expansion
targets:
  - name: my_model
    type: azure_ai_model
    deployment_name: [gpt-4o, gpt-4o-mini]   # 2 values
    args:
      temperature: [0.0, 0.7]                 # x 2 values = 4 total variants

# The TargetFactory expands this into 4 target instances:
#   1. deployment_name=gpt-4o,      temperature=0.0
#   2. deployment_name=gpt-4o,      temperature=0.7
#   3. deployment_name=gpt-4o-mini, temperature=0.0
#   4. deployment_name=gpt-4o-mini, temperature=0.7`, 'yaml', { filePath: 'config.yaml', title: 'Cartesian Product Example' })}

    ${createInfoCard('Expansion Scale', 'The number of variants is the product of all list lengths. A target with 3 deployment names, 2 temperatures, and 2 system prompts creates 3 x 2 x 2 = 12 target instances. Each is evaluated independently against the full dataset.', 'warning')}

    <h3 id="input-mapping">Input Mapping</h3>
    <p>Input mapping renames dataset columns before they reach the target. This decouples your dataset schema from the target's expected parameter names.</p>

    ${createCodeBlock(`# config.yaml -- input_mapping section
targets:
  - name: my_target
    type: custom
    input_mapping:
      question: dataset.query        # dataset column "query" -> target param "question"
      context: dataset.context       # dataset column "context" -> target param "context"
      ground_truth: dataset.answer   # dataset column "answer" -> target param "ground_truth"`, 'yaml', { filePath: 'config.yaml', title: 'Input Mapping Configuration' })}

    ${createCodeBlock(`# target_mapping.py -- How mapping is applied at runtime
class TargetInputMapper:
    def __init__(self, mapping: Dict[str, str]):
        self._mapping = mapping  # {target_param: "dataset.column_name"}

    def apply(self, dataset_row: Dict[str, Any]) -> Dict[str, Any]:
        """Remap dataset fields to target parameter names."""
        mapped = {}
        for target_param, source_ref in self._mapping.items():
            # source_ref format: "dataset.<column_name>"
            column = source_ref.split(".", 1)[1] if "." in source_ref else source_ref
            if column in dataset_row:
                mapped[target_param] = dataset_row[column]
        return mapped`, 'python', { filePath: '_engine/target_mapping.py', title: 'TargetInputMapper Implementation' })}

    ${createSequenceDiagram('Target Invocation with Input Mapping', [
      { id: 'runner', label: 'ExperimentRunner', type: 'engine' },
      { id: 'mapper', label: 'TargetInputMapper', type: 'config' },
      { id: 'tgt', label: 'Target Instance', type: 'target' },
      { id: 'eval', label: 'Evaluators', type: 'evaluator' },
    ], [
      { from: 'runner', to: 'mapper', label: 'dataset_row (raw fields)' },
      { from: 'mapper', to: 'tgt', label: 'mapped input dict' },
      { from: 'tgt', to: 'runner', label: '{response, output_items, ...}', type: 'return' },
      { from: 'runner', to: 'eval', label: 'response + dataset context' },
      { from: 'eval', to: 'runner', label: 'scores per evaluator', type: 'return' },
    ])}

    <h3 id="target-config-examples">Target Configuration Examples</h3>
    ${createTabs([
      {
        label: 'Custom Target',
        content: `<p>A user-defined target discovered from the <code>targets/</code> directory via <code>@target</code> decorator.</p>
          ${createCodeBlock(`targets:
  - name: my_agent
    type: custom
    args:
      endpoint: \${MY_AGENT_ENDPOINT}
      api_key: \${MY_AGENT_KEY}
    input_mapping:
      query: dataset.question
      context: dataset.context`, 'yaml', { filePath: 'config.yaml', title: 'Custom Target Config' })}`
      },
      {
        label: 'Azure AI Model',
        content: `<p>Direct Azure OpenAI model evaluation -- no custom code required.</p>
          ${createCodeBlock(`targets:
  - name: gpt4o_comparison
    type: azure_ai_model
    connection: my_azure_connection
    deployment_name: [gpt-4o, gpt-4o-mini]
    args:
      temperature: [0.0, 0.5, 1.0]
      max_tokens: 1024`, 'yaml', { filePath: 'config.yaml', title: 'Azure AI Model Config' })}`
      },
      {
        label: 'Azure AI Agent',
        content: `<p>Azure AI Foundry agent with tool-calling capabilities.</p>
          ${createCodeBlock(`targets:
  - name: support_agent
    type: azure_ai_agent
    agent_name: customer-support-v2
    agent_version: "3"
    azure_ai_project:
      endpoint: \${FOUNDRY_ENDPOINT}
      project_name: \${FOUNDRY_PROJECT}`, 'yaml', { filePath: 'config.yaml', title: 'Azure AI Agent Config' })}`
      },
    ], 'target-config-examples')}
  `;

  // ════════════════════════════════════════════════════════════
  // SECTION 3: Custom Components (Extensibility)
  // ════════════════════════════════════════════════════════════
  document.getElementById('custom').innerHTML = `
    <h2>Custom Components</h2>
    <p class="section-intro">Extend the evaluation engine with custom evaluators, targets, and datasets using Python decorators. The engine discovers and registers them automatically via AST-based scanning.</p>

    <h3 id="decorator-registry">Decorator and Registry System</h3>
    <p>Three global registries hold custom components. Each has a corresponding decorator that registers the class at import time.</p>

    ${createCodeBlock(`# decorators.py -- Global registries and decorator definitions

_EVALUATOR_REGISTRY: Dict[str, Type] = {}
_TARGET_REGISTRY: Dict[str, Type] = {}
_DATASET_REGISTRY: Dict[str, Type] = {}

def evaluator(cls=None, *, name=None):
    """Register a class as a custom evaluator."""
    def wrapper(cls):
        key = name or cls.__name__
        _EVALUATOR_REGISTRY[key] = cls
        return cls
    return wrapper(cls) if cls else wrapper

def target(cls=None, *, name=None):
    """Register a class as a custom target."""
    def wrapper(cls):
        key = name or cls.__name__
        _TARGET_REGISTRY[key] = cls
        return cls
    return wrapper(cls) if cls else wrapper

def dataset(cls=None, *, name=None):
    """Register a class as a custom dataset."""
    def wrapper(cls):
        key = name or cls.__name__
        _DATASET_REGISTRY[key] = cls
        return cls
    return wrapper(cls) if cls else wrapper`, 'python', { filePath: '_engine/decorators.py', title: 'Decorator Definitions', highlightLines: [3, 4, 5, 8, 15, 22] })}

    ${createTable(
      ['Decorator', 'Registry', 'Use Case'],
      [
        ['<code>@evaluator(name="...")</code>', '<code>_EVALUATOR_REGISTRY</code>', 'Custom scoring logic (per-row compute + aggregate)'],
        ['<code>@target(name="...")</code>', '<code>_TARGET_REGISTRY</code>', 'Custom inference endpoints (models, agents, APIs)'],
        ['<code>@dataset(name="...")</code>', '<code>_DATASET_REGISTRY</code>', 'Custom data loading (databases, APIs, transforms)'],
      ]
    )}

    ${createInfoCard('Name Resolution', 'If the <code>name</code> parameter is omitted, the class name is used as the registry key. For example, <code>@evaluator</code> on <code>class WordCount</code> registers as <code>"WordCount"</code>. Use explicit names for stable references in YAML configs.', 'tip')}

    <h3 id="discovery-system">Discovery System</h3>
    <p>The <code>discover_components()</code> function uses AST parsing to find decorated classes without importing all project files blindly. Only files that match are imported to trigger registration.</p>

    ${createCodeBlock(`def discover_components(search_path: str) -> Dict[str, List[str]]:
    """
    AST-scans Python files in search_path for
    @evaluator, @target, @dataset decorators.
    Imports matching modules to trigger registration.

    Returns: {"evaluators": [...], "targets": [...], "datasets": [...]}
    """
    known_decorators = {"evaluator", "target", "dataset"}
    results = {"evaluators": [], "targets": [], "datasets": []}

    for py_file in walk_python_files(search_path):
        # Step 1: Parse AST without importing
        tree = ast.parse(py_file.read_text())

        # Step 2: Look for ClassDef nodes with known decorators
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for decorator in node.decorator_list:
                dec_name = get_decorator_name(decorator)
                if dec_name in known_decorators:
                    # Step 3: Import the module to trigger @decorator
                    module = importlib.import_module(path_to_module(py_file))
                    # Registration happens automatically via the decorator
                    results[dec_name + "s"].append(get_registered_name(decorator, node))
                    break

    return results`, 'python', { filePath: '_engine/discovery.py', title: 'Component Discovery', highlightLines: [14, 18, 25] })}

    ${createCallTrace('Discovery Pipeline', [
      { module: 'discovery', func: 'discover_components(search_path)', file: '_engine/discovery.py', tag: 'engine',
        detail: 'Entry point. Receives the project root path and scans for .py files recursively.' },
      { module: 'discovery', func: 'walk_python_files(search_path)', file: '_engine/discovery.py', tag: 'engine',
        detail: 'Walks directory tree, yields .py files. Skips .venv/, __pycache__/, .git/, node_modules/, *.egg-info/.' },
      { module: 'ast', func: 'ast.parse(source)', file: 'stdlib', tag: 'data',
        detail: 'Parses Python source into AST without executing. Safe and fast for scanning large codebases.' },
      { module: 'discovery', func: 'Check ClassDef decorators', file: '_engine/discovery.py', tag: 'engine',
        detail: 'Walks AST nodes. For each ClassDef, checks if any decorator name matches evaluator, target, or dataset.' },
      { module: 'importlib', func: 'import_module(module_path)', file: 'stdlib', tag: 'engine',
        detail: 'Dynamically imports the module. Importing triggers the decorator, which auto-registers the component in the global registry.' },
      { module: 'Registry', func: 'register()', file: '_engine/decorators.py', tag: 'data',
        detail: 'Component is stored in the registry dict with its name as key and class as value. Ready for TargetFactory or EvaluatorFactory.' },
    ])}

    <h3 id="custom-evaluators">Writing Custom Evaluators</h3>
    <p>Extend <code>BaseEvaluator</code> and implement <code>compute()</code> for per-row scoring. Optionally override <code>aggregate()</code> for summary statistics.</p>

    ${createCodeBlock(`class BaseEvaluator:
    def compute(self, **kwargs) -> Dict[str, Any]:
        """Score a single row. Must return a dict of metric values."""
        raise NotImplementedError

    def aggregate(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Summarize across all rows. Default: mean of numeric values."""
        numeric_keys = [k for k in results[0] if isinstance(results[0][k], (int, float))]
        return {
            k: sum(r[k] for r in results) / len(results)
            for k in numeric_keys
        }`, 'python', { filePath: '_engine/base_evaluator.py', title: 'BaseEvaluator Contract' })}

    ${createTabs([
      {
        label: 'Word Count (Simple)',
        content: `<p>A minimal evaluator that counts words in the model response.</p>
          ${createCodeBlock(`from azure.ai.evaluation._engine.decorators import evaluator, BaseEvaluator
from typing import Dict, Any, List

@evaluator(name="word_count")
class WordCountEvaluator(BaseEvaluator):
    """Counts words in the model response."""

    def compute(self, response: str = "", **kwargs) -> Dict[str, Any]:
        count = len(response.split()) if response else 0
        return {"word_count": count, "word_count_pass": count < 500}

    def aggregate(self, results: List[Dict]) -> Dict[str, Any]:
        counts = [r["word_count"] for r in results if "word_count" in r]
        if not counts:
            return {}
        return {
            "word_count_avg": sum(counts) / len(counts),
            "word_count_max": max(counts),
            "word_count_min": min(counts),
        }`, 'python', { filePath: 'evaluators/word_count.py', title: 'Word Count Evaluator', highlightLines: [4, 8, 12] })}`
      },
      {
        label: 'JSON Validity (Moderate)',
        content: `<p>Checks if a model response is valid JSON. Returns a boolean metric and optional parse error details.</p>
          ${createCodeBlock(`import json
from azure.ai.evaluation._engine.decorators import evaluator, BaseEvaluator
from typing import Dict, Any, List

@evaluator(name="json_validity")
class JsonValidityEvaluator(BaseEvaluator):
    """Validates that the response is parseable JSON."""

    def compute(self, response: str = "", **kwargs) -> Dict[str, Any]:
        try:
            json.loads(response)
            return {"json_valid": 1, "json_error": None}
        except (json.JSONDecodeError, TypeError) as e:
            return {"json_valid": 0, "json_error": str(e)}

    def aggregate(self, results: List[Dict]) -> Dict[str, Any]:
        valid = [r["json_valid"] for r in results if "json_valid" in r]
        return {
            "json_valid_rate": sum(valid) / len(valid) if valid else 0,
            "json_valid_count": sum(valid),
            "json_invalid_count": len(valid) - sum(valid),
        }`, 'python', { filePath: 'evaluators/json_validity.py', title: 'JSON Validity Evaluator', highlightLines: [5, 9, 16] })}`
      },
    ], 'custom-evaluator-examples')}

    <h3 id="custom-targets">Writing Custom Targets</h3>
    <p>Custom targets wrap your inference endpoint. Use <code>@target</code> and implement <code>__call__</code> to handle a single query.</p>

    ${createCodeBlock(`from azure.ai.evaluation._engine.decorators import target
from typing import Dict, Any

@target(name="my_agent")
class MyAgentTarget:
    """Custom target wrapping a REST API agent."""

    def __init__(self, endpoint: str, api_key: str):
        self.endpoint = endpoint
        self.api_key = api_key

    def __call__(self, query: str, **kwargs) -> str:
        import requests
        response = requests.post(
            self.endpoint,
            json={"query": query},
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()["answer"]`, 'python', { filePath: 'targets/my_agent.py', title: 'Custom Target Example', highlightLines: [4, 8, 12] })}

    ${createInfoCard('Target Return Types', 'A custom target can return either a plain <code>str</code> (the response text) or a <code>dict</code> with keys like <code>response</code>, <code>output_items</code>, and <code>tool_definitions</code>. The dict form is required for agent evaluators that inspect tool calls.', 'info')}

    <p>The corresponding YAML config references the target by its registered name:</p>
    ${createCodeBlock(`# config.yaml
targets:
  - name: my_agent          # Must match @target(name="my_agent")
    type: custom
    args:
      endpoint: \${MY_AGENT_ENDPOINT}
      api_key: \${MY_AGENT_KEY}
    input_mapping:
      query: dataset.question`, 'yaml', { filePath: 'config.yaml', title: 'Config for Custom Target' })}

    <h3 id="custom-datasets">Writing Custom Datasets</h3>
    <p>Custom datasets let you load data from any source -- databases, APIs, or complex file formats.</p>

    ${createCodeBlock(`from azure.ai.evaluation._engine.decorators import dataset
from typing import Dict, Any, List, Iterator

@dataset(name="sql_dataset")
class SqlDataset:
    """Load evaluation data from a SQL database."""

    def __init__(self, connection_string: str, query: str):
        self.connection_string = connection_string
        self.query = query

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        import sqlite3
        conn = sqlite3.connect(self.connection_string)
        cursor = conn.execute(self.query)
        columns = [desc[0] for desc in cursor.description]
        for row in cursor:
            yield dict(zip(columns, row))
        conn.close()

    def __len__(self) -> int:
        import sqlite3
        conn = sqlite3.connect(self.connection_string)
        count = conn.execute(f"SELECT COUNT(*) FROM ({self.query})").fetchone()[0]
        conn.close()
        return count`, 'python', { filePath: 'datasets/sql_dataset.py', title: 'Custom Dataset Example', highlightLines: [4, 12, 21] })}

    <h3 id="component-lifecycle">Component Lifecycle</h3>
    <p>The complete flow from code to execution:</p>

    ${createCallTrace('Decorator to Execution Pipeline', [
      { module: 'Author', func: 'Write class with @evaluator/@target/@dataset', file: 'evaluators/*.py, targets/*.py', tag: 'cli',
        detail: 'Developer writes a Python class with the appropriate decorator and places it in the project directory.' },
      { module: 'Discovery', func: 'discover_components(project_path)', file: '_engine/discovery.py', tag: 'engine',
        detail: 'AST scans all .py files in the project. Finds decorated classes without executing arbitrary code.' },
      { module: 'Import', func: 'importlib.import_module()', file: '_engine/discovery.py', tag: 'engine',
        detail: 'Only files with matching decorators are imported. Import triggers the decorator, registering the class.' },
      { module: 'Registry', func: '_EVALUATOR_REGISTRY[name] = cls', file: '_engine/decorators.py', tag: 'data',
        detail: 'Class is stored in the global registry dict, keyed by the name parameter or class name.' },
      { module: 'Factory', func: 'TargetFactory / EvaluatorFactory', file: '_engine/*_factory.py', tag: 'engine',
        detail: 'Factories read YAML config, look up names in the registry, and instantiate with provided args.' },
      { module: 'Runner', func: 'ExperimentRunner.run()', file: '_engine/runner.py', tag: 'engine',
        detail: 'Orchestrates the full pipeline: iterate dataset rows, invoke targets, run evaluators, aggregate results.' },
    ])}

    ${createFlowDiagram('Component Registration and Usage', [
      { id: 'code', label: 'Python File', subtitle: '@decorator class', type: 'config', col: 0, row: 0 },
      { id: 'ast', label: 'AST Scanner', subtitle: 'find decorators', type: 'method', col: 2, row: 0 },
      { id: 'import', label: 'Import Module', subtitle: 'trigger decorator', type: 'method', col: 0, row: 1 },
      { id: 'registry', label: 'Global Registry', subtitle: 'name -> class', type: 'data', col: 2, row: 1 },
      { id: 'factory', label: 'Factory', subtitle: 'instantiate', type: 'class', col: 1, row: 2 },
      { id: 'runner', label: 'ExperimentRunner', subtitle: 'execute pipeline', type: 'class', col: 1, row: 3 },
    ], [
      { from: 'code', to: 'ast', label: '*.py files' },
      { from: 'ast', to: 'import', label: 'decorator found' },
      { from: 'import', to: 'registry', label: 'register()' },
      { from: 'registry', to: 'factory', label: 'lookup by name' },
      { from: 'factory', to: 'runner', label: 'instances' },
    ], { width: 700, height: 380 })}

    ${createInfoCard('Excluded Directories',
      'Discovery skips these directories: <code>.venv/</code>, <code>venv/</code>, <code>__pycache__/</code>, <code>.git/</code>, <code>node_modules/</code>, <code>.tox/</code>, <code>*.egg-info/</code>. Only <code>.py</code> files in the project root and subdirectories are scanned.',
    'info')}
  `;
}

// ── Bootstrap ─────────────────────────────────────────────────
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initCliTargetsContent);
} else {
  initCliTargetsContent();
}
