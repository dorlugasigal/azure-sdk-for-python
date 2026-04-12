/* ============================================================
   Content: Evaluators & Configuration Reference
   Populates sections "evaluators" and "configuration"
   ============================================================ */

function initEvalConfigContent() {

  // ============================================================
  // SECTION 1: EVALUATORS
  // ============================================================

  // -- Class hierarchy diagram ---------------------------------

  const classDiagram = createClassDiagram('Evaluator Class Hierarchy', [
    // Row 0 - abstract root
    { id: 'base', label: 'EvaluatorBase[T]', type: 'abstract', col: 1.5, row: 0,
      methods: [
        { name: '__call__', abstract: true },
        { name: '_do_eval', abstract: true },
        { name: '_convert_conversation_to_eval_input', abstract: true }
      ] },

    // Row 1 - intermediate bases
    { id: 'prompty', label: 'PromptyEvaluatorBase', type: 'abstract', parent: 'base', col: 0, row: 1.4,
      methods: [{ name: '_do_eval' }, { name: '_load_prompty' }] },
    { id: 'rai', label: 'RaiServiceEvalBase', type: 'abstract', parent: 'base', col: 1.3, row: 1.4,
      methods: [{ name: '_do_eval' }, { name: '_call_rai_svc' }] },
    { id: 'multi', label: 'MultiEvaluatorBase', type: 'abstract', parent: 'base', col: 2.6, row: 1.4,
      methods: [{ name: '_do_eval' }, { name: '_aggregate' }] },
    { id: 'direct', label: 'Direct Impls', type: 'concrete', parent: 'base', col: 3.6, row: 1.4,
      methods: [{ name: '_do_eval' }] },

    // Row 2 - Prompty leaf evaluators
    { id: 'coherence', label: 'CoherenceEvaluator', type: 'concrete', parent: 'prompty', col: -1.4, row: 2.8, methods: [] },
    { id: 'fluency', label: 'FluencyEvaluator', type: 'concrete', parent: 'prompty', col: -0.3, row: 2.8, methods: [] },
    { id: 'relevance', label: 'RelevanceEvaluator', type: 'concrete', parent: 'prompty', col: -1.4, row: 3.6, methods: [] },
    { id: 'groundedness', label: 'GroundednessEval', type: 'concrete', parent: 'prompty', col: -0.3, row: 3.6, methods: [] },
    { id: 'similarity', label: 'SimilarityEvaluator', type: 'concrete', parent: 'prompty', col: 0.8, row: 2.8, methods: [] },
    { id: 'responsecomp', label: 'ResponseCompleteness', type: 'concrete', parent: 'prompty', col: 0.8, row: 3.6, methods: [] },
    { id: 'intentres', label: 'IntentResolution', type: 'concrete', parent: 'prompty', col: -1.4, row: 4.4, methods: [] },
    { id: 'toolcall', label: 'ToolCallAccuracy', type: 'concrete', parent: 'prompty', col: -0.3, row: 4.4, methods: [] },
    { id: 'taskadhere', label: 'TaskAdherence', type: 'concrete', parent: 'prompty', col: 0.8, row: 4.4, methods: [] },

    // Row 2 - RAI leaf evaluators
    { id: 'violence', label: 'ViolenceEvaluator', type: 'concrete', parent: 'rai', col: 1.3, row: 2.8, methods: [] },
    { id: 'sexual', label: 'SexualEvaluator', type: 'concrete', parent: 'rai', col: 2.1, row: 2.8, methods: [] },
    { id: 'selfharm', label: 'SelfHarmEvaluator', type: 'concrete', parent: 'rai', col: 1.3, row: 3.6, methods: [] },
    { id: 'hate', label: 'HateUnfairnessEval', type: 'concrete', parent: 'rai', col: 2.1, row: 3.6, methods: [] },
    { id: 'codevuln', label: 'CodeVulnerability', type: 'concrete', parent: 'rai', col: 1.3, row: 4.4, methods: [] },
    { id: 'protmat', label: 'ProtectedMaterial', type: 'concrete', parent: 'rai', col: 2.1, row: 4.4, methods: [] },
    { id: 'unground', label: 'UngroundedAttrs', type: 'concrete', parent: 'rai', col: 1.3, row: 5.2, methods: [] },
    { id: 'xpia', label: 'IndirectAttack', type: 'concrete', parent: 'rai', col: 2.1, row: 5.2, methods: [] },

    // Row 2 - Composite evaluators
    { id: 'qa', label: 'QAEvaluator', type: 'concrete', parent: 'multi', col: 2.9, row: 2.8,
      methods: [{ name: '6 sub-evaluators' }] },
    { id: 'safety', label: 'ContentSafetyEval', type: 'concrete', parent: 'multi', col: 2.9, row: 3.6,
      methods: [{ name: '4 sub-evaluators' }] },

    // Row 2 - Direct / algorithmic evaluators
    { id: 'f1', label: 'F1ScoreEvaluator', type: 'concrete', parent: 'direct', col: 3.6, row: 2.8, methods: [] },
    { id: 'bleu', label: 'BleuScoreEvaluator', type: 'concrete', parent: 'direct', col: 4.4, row: 2.8, methods: [] },
    { id: 'gleu', label: 'GleuScoreEvaluator', type: 'concrete', parent: 'direct', col: 3.6, row: 3.6, methods: [] },
    { id: 'meteor', label: 'MeteorScoreEval', type: 'concrete', parent: 'direct', col: 4.4, row: 3.6, methods: [] },
    { id: 'rouge', label: 'RougeScoreEvaluator', type: 'concrete', parent: 'direct', col: 3.6, row: 4.4, methods: [] },
  ]);

  // -- Engine BaseEvaluator contract ---------------------------

  const baseEvalCode = createCodeBlock(
`class BaseEvaluator(ABC):
    """Base class for all evaluators registered via @evaluator decorator."""

    def __init__(self, config=None, context=None):
        config = config or {}
        self.name = config.get("name", self.__class__.__name__)
        self.display_name = config.get("display_name") or self.name
        self.context = context
        self.mapping = config.get("mapping", {})

    @abstractmethod
    def compute(self, **kwargs) -> Dict[str, Any]:
        """Score a single row. Return {metric_name: value}."""
        ...

    @abstractmethod
    def aggregate(self, scores: List[Dict[str, Any]]) -> Dict[str, Number]:
        """Reduce per-row scores to summary statistics (mean, etc.)."""
        ...

    def _get_mapped_fields(self, inference_output) -> Dict[str, Any]:
        """Resolve mapping: 'target.X' / 'dataset.X' to actual values."""
        data = inference_output.to_dict()
        output = data.get("output", {})
        sources = {
            "model": output, "target": output,
            "dataset": data.get("record", {}),
        }
        mapped = {}
        for param, mapping in self.mapping.items():
            source, field = mapping.split(".", 1)
            mapped[param] = sources.get(source, {}).get(field)
        return mapped`, 'python', {
    filePath: 'azure/ai/evaluation/_engine/decorators.py',
    title: 'Engine BaseEvaluator Contract'
  });

  // -- Custom evaluator example --------------------------------

  const customEvalCode = createCodeBlock(
`"""Word count evaluator -- auto-discovered by the engine."""
from azure.ai.evaluation._engine.decorators import evaluator, BaseEvaluator


@evaluator(name="word_count")
class WordCountEvaluator(BaseEvaluator):
    """Counts the number of words in the target's response."""

    def compute(self, response: str = "", **kwargs):
        word_count = len(response.split())
        return {"word_count": word_count}

    def aggregate(self, scores):
        values = [s["word_count"] for s in scores]
        return {
            "word_count_mean": round(sum(values) / len(values), 1) if values else 0,
            "word_count_max": max(values) if values else 0,
            "word_count_min": min(values) if values else 0,
        }`, 'python', {
    filePath: 'evaluators/word_count.py',
    title: 'Custom Evaluator Example'
  });

  // -- @evaluator decorator internals --------------------------

  const decoratorCode = createCodeBlock(
`def evaluator(name=None):
    """Decorator that wraps a user class in an EvaluatorWrapper and registers it."""
    def decorator(cls):
        evaluator_name = name or cls.__name__

        class EvaluatorWrapper(BaseEvaluator):
            def __init__(self, config=None, context=None, **extra):
                super().__init__(config, context)
                # Inject cloud config, deployment_name, connections into inner class
                cls_sig = inspect.signature(cls.__init__)
                cloud = self.context.cloud_config if self.context else None
                init_params = {}
                for p in cls_sig.parameters:
                    if p == "deployment_name":
                        init_params[p] = (
                            config.get("deployment_name")
                            or (cloud.default_evaluator_deployment if cloud else None)
                        )
                    # ... other injected params: azure_endpoint, context, etc.
                self.inner = cls(**init_params)

            def compute(self, inference_output=None, **kwargs):
                if kwargs and not inference_output:
                    return self.inner.compute(**kwargs)      # Direct API
                elif inference_output:
                    fields = self._get_mapped_fields(inference_output)
                    return self.inner.compute(**fields)       # Engine mode
                return self.inner.compute()

            def aggregate(self, scores):
                return self.inner.aggregate(scores)

        EVALUATOR_REGISTRY[evaluator_name] = EvaluatorWrapper
        return EvaluatorWrapper
    return decorator`, 'python', {
    filePath: 'azure/ai/evaluation/_engine/decorators.py',
    title: '@evaluator Decorator (Simplified)'
  });

  // -- Quality evaluator metric cards --------------------------

  const qualityCards = [
    { name: 'CoherenceEvaluator', category: 'Quality', backend: 'Prompty',
      description: 'Measures logical flow and structural coherence of the response.',
      metric: 'coherence', scaleMin: 1, scaleMax: 5,
      inputs: ['query', 'response'], outputs: ['coherence', 'coherence_reason'] },
    { name: 'FluencyEvaluator', category: 'Quality', backend: 'Prompty',
      description: 'Evaluates grammatical correctness and natural language fluency.',
      metric: 'fluency', scaleMin: 1, scaleMax: 5,
      inputs: ['query', 'response'], outputs: ['fluency', 'fluency_reason'] },
    { name: 'RelevanceEvaluator', category: 'Quality', backend: 'Prompty',
      description: 'Assesses how well the response addresses the query.',
      metric: 'relevance', scaleMin: 1, scaleMax: 5,
      inputs: ['query', 'response'], outputs: ['relevance', 'relevance_reason'] },
    { name: 'SimilarityEvaluator', category: 'Quality', backend: 'Prompty',
      description: 'Compares semantic similarity between response and ground truth.',
      metric: 'similarity', scaleMin: 0, scaleMax: 5,
      inputs: ['query', 'response', 'ground_truth'], outputs: ['similarity', 'similarity_reason'] },
    { name: 'GroundednessEvaluator', category: 'Quality', backend: 'Prompty',
      description: 'Checks if the response is factually grounded in the provided context.',
      metric: 'groundedness', scaleMin: 1, scaleMax: 5,
      inputs: ['query', 'response', 'context'], outputs: ['groundedness', 'groundedness_reason'] },
    { name: 'GroundednessProEvaluator', category: 'Quality', backend: 'RAI',
      description: 'Azure RAI service-backed groundedness with binary pass/fail.',
      metric: 'groundedness_pro', scaleMin: 0, scaleMax: 1,
      inputs: ['query', 'response', 'context'], outputs: ['groundedness_pro', 'groundedness_pro_reason'] },
    { name: 'ResponseCompletenessEvaluator', category: 'Quality', backend: 'Prompty',
      description: 'Evaluates whether the response fully addresses all aspects of the query.',
      metric: 'response_completeness', scaleMin: 1, scaleMax: 5,
      inputs: ['query', 'response'], outputs: ['response_completeness', 'response_completeness_reason'] },
  ].map(createMetricCard).join('');

  // -- Agent evaluator metric cards ----------------------------

  const agentCards = [
    { name: 'IntentResolutionEvaluator', category: 'Agent', backend: 'Prompty',
      description: 'Measures how well the response resolves the user intent.',
      metric: 'intent_resolution', scaleMin: 1, scaleMax: 5,
      inputs: ['query', 'response'], outputs: ['intent_resolution', 'intent_resolution_reason'] },
    { name: 'ToolCallAccuracyEvaluator', category: 'Agent', backend: 'Prompty',
      description: 'Evaluates whether the agent selected the correct tools with proper parameters.',
      metric: 'tool_call_accuracy', scaleMin: 1, scaleMax: 5,
      inputs: ['query', 'response', 'tool_calls', 'tool_definitions'],
      outputs: ['tool_call_accuracy', 'tool_call_accuracy_reason'] },
    { name: 'TaskAdherenceEvaluator', category: 'Agent', backend: 'Prompty',
      description: 'Checks whether the agent output adheres to the assigned task.',
      metric: 'task_adherence', scaleMin: 0, scaleMax: 1,
      inputs: ['query', 'response'], outputs: ['task_adherence', 'task_adherence_reason'] },
  ].map(createMetricCard).join('');

  // -- Safety evaluator metric cards ---------------------------

  const safetyCards = [
    { name: 'ViolenceEvaluator', category: 'Safety', backend: 'RAI',
      description: 'Detects violent content. Severity 0 = safe, 7 = extreme.',
      metric: 'violence', scaleMin: 0, scaleMax: 7,
      inputs: ['query', 'response'], outputs: ['violence', 'violence_score', 'violence_reason'] },
    { name: 'SexualEvaluator', category: 'Safety', backend: 'RAI',
      description: 'Detects sexual content in the response.',
      metric: 'sexual', scaleMin: 0, scaleMax: 7,
      inputs: ['query', 'response'], outputs: ['sexual', 'sexual_score', 'sexual_reason'] },
    { name: 'SelfHarmEvaluator', category: 'Safety', backend: 'RAI',
      description: 'Detects self-harm related content in the response.',
      metric: 'self_harm', scaleMin: 0, scaleMax: 7,
      inputs: ['query', 'response'], outputs: ['self_harm', 'self_harm_score', 'self_harm_reason'] },
    { name: 'HateUnfairnessEvaluator', category: 'Safety', backend: 'RAI',
      description: 'Detects hateful or unfair content in the response.',
      metric: 'hate_unfairness', scaleMin: 0, scaleMax: 7,
      inputs: ['query', 'response'], outputs: ['hate_unfairness', 'hate_unfairness_score', 'hate_unfairness_reason'] },
  ].map(createMetricCard).join('');

  // -- Security evaluator metric cards -------------------------

  const securityCards = [
    { name: 'CodeVulnerabilityEvaluator', category: 'Security', backend: 'RAI',
      description: 'Detects potential code vulnerabilities in the generated response.',
      metric: 'code_vulnerability', scaleMin: 0, scaleMax: 1,
      inputs: ['query', 'response'], outputs: ['code_vulnerability', 'code_vulnerability_reason'] },
    { name: 'IndirectAttackEvaluator', category: 'Security', backend: 'RAI',
      description: 'Detects XPIA (cross-prompt injection attack) patterns.',
      metric: 'xpia', scaleMin: 0, scaleMax: 1,
      inputs: ['query', 'response'], outputs: ['xpia', 'xpia_reason'] },
    { name: 'ProtectedMaterialEvaluator', category: 'Security', backend: 'RAI',
      description: 'Detects copyrighted or protected material in output.',
      metric: 'protected_material', scaleMin: 0, scaleMax: 1,
      inputs: ['query', 'response'], outputs: ['protected_material', 'protected_material_reason'] },
    { name: 'UngroundedAttributesEvaluator', category: 'Security', backend: 'RAI',
      description: 'Detects unverifiable claims or hallucinated attributes.',
      metric: 'ungrounded_attributes', scaleMin: 0, scaleMax: 1,
      inputs: ['query', 'response'], outputs: ['ungrounded_attributes', 'ungrounded_attributes_reason'] },
  ].map(createMetricCard).join('');

  // -- Reference metric cards ----------------------------------

  const referenceCards = [
    { name: 'F1ScoreEvaluator', category: 'Reference', backend: 'Local',
      description: 'Token-level F1 overlap between response and ground truth.',
      metric: 'f1_score', scaleMin: 0, scaleMax: 1,
      inputs: ['response', 'ground_truth'], outputs: ['f1_score'] },
    { name: 'BleuScoreEvaluator', category: 'Reference', backend: 'Local',
      description: 'BLEU n-gram precision score for translation / generation quality.',
      metric: 'bleu_score', scaleMin: 0, scaleMax: 1,
      inputs: ['response', 'ground_truth'], outputs: ['bleu_score'] },
    { name: 'GleuScoreEvaluator', category: 'Reference', backend: 'Local',
      description: 'Google-BLEU variant that also penalizes over-generation.',
      metric: 'gleu_score', scaleMin: 0, scaleMax: 1,
      inputs: ['response', 'ground_truth'], outputs: ['gleu_score'] },
    { name: 'MeteorScoreEvaluator', category: 'Reference', backend: 'Local',
      description: 'METEOR score incorporating synonyms and stemming.',
      metric: 'meteor_score', scaleMin: 0, scaleMax: 1,
      inputs: ['response', 'ground_truth'], outputs: ['meteor_score'] },
    { name: 'RougeScoreEvaluator', category: 'Reference', backend: 'Local',
      description: 'ROUGE-L F1 measuring longest common subsequence overlap.',
      metric: 'rouge_f1_score', scaleMin: 0, scaleMax: 1,
      inputs: ['response', 'ground_truth'], outputs: ['rouge_f1_score', 'rouge_precision', 'rouge_recall'] },
  ].map(createMetricCard).join('');

  // -- Composite evaluator metric cards ------------------------

  const compositeCards = [
    { name: 'QAEvaluator', category: 'Composite', backend: 'Multi',
      description: 'Runs 6 quality sub-evaluators: coherence, fluency, relevance, groundedness, similarity, and F1.',
      metric: '6 metrics',
      inputs: ['query', 'response', 'context', 'ground_truth'],
      outputs: ['coherence', 'fluency', 'relevance', 'groundedness', 'similarity', 'f1_score'] },
    { name: 'ContentSafetyEvaluator', category: 'Composite', backend: 'Multi',
      description: 'Runs 4 safety sub-evaluators: violence, sexual, self_harm, hate_unfairness.',
      metric: '4 metrics',
      inputs: ['query', 'response'],
      outputs: ['violence', 'sexual', 'self_harm', 'hate_unfairness'] },
  ].map(createMetricCard).join('');

  // -- Backend call traces -------------------------------------

  const promptyTrace = createCallTrace('How PromptyEvaluatorBase Works', [
    { module: 'PromptyEvaluatorBase', func: '__call__(query, response, ...)',
      file: '_evaluators/_prompty_base.py', tag: 'evaluator',
      detail: 'Entry point -- validates inputs and converts conversation format.' },
    { module: 'PromptyEvaluatorBase', func: '_load_prompty()',
      file: '_evaluators/_prompty_base.py', tag: 'evaluator',
      detail: 'Loads .prompty file (Jinja2 template) from evaluator asset directory.' },
    { module: 'PromptyEvaluatorBase', func: '_render_prompt(template, vars)',
      file: '_evaluators/_prompty_base.py', tag: 'evaluator',
      detail: 'Renders the Jinja2 template with query, response, context, etc.' },
    { module: 'PromptyEvaluatorBase', func: '_call_model(prompt)',
      file: '_evaluators/_prompty_base.py', tag: 'external',
      detail: 'Sends rendered prompt to the configured LLM deployment (e.g. gpt-4.1-mini).' },
    { module: 'PromptyEvaluatorBase', func: '_parse_score(llm_output)',
      file: '_evaluators/_prompty_base.py', tag: 'evaluator',
      detail: 'Extracts numeric score and reasoning from the LLM JSON response.' },
    { module: 'PromptyEvaluatorBase', func: 'return {metric: score, metric_reason: reason}',
      file: '', tag: 'data',
      detail: 'Returns dict with the metric value and optional reasoning string.' },
  ]);

  const raiTrace = createCallTrace('How RaiServiceEvaluatorBase Works', [
    { module: 'RaiServiceEvaluatorBase', func: '__call__(query, response)',
      file: '_evaluators/_rai_base.py', tag: 'evaluator',
      detail: 'Entry point -- validates inputs.' },
    { module: 'RaiServiceEvaluatorBase', func: '_build_payload()',
      file: '_evaluators/_rai_base.py', tag: 'evaluator',
      detail: 'Constructs JSON payload with query, response, and evaluation task type.' },
    { module: 'RaiServiceEvaluatorBase', func: '_call_rai_service(payload)',
      file: '_evaluators/_rai_base.py', tag: 'external',
      detail: 'Sends POST to Azure RAI service endpoint with AAD auth token.' },
    { module: 'RaiServiceEvaluatorBase', func: '_poll_for_result(operation_id)',
      file: '_evaluators/_rai_base.py', tag: 'external',
      detail: 'Polls the async operation until completion or timeout.' },
    { module: 'RaiServiceEvaluatorBase', func: '_parse_response(rai_result)',
      file: '_evaluators/_rai_base.py', tag: 'evaluator',
      detail: 'Extracts severity level (0-7) or boolean and reasoning from RAI response.' },
    { module: 'RaiServiceEvaluatorBase', func: 'return {metric: severity, metric_reason: ...}',
      file: '', tag: 'data',
      detail: 'Returns dict with severity score and optional defect reasoning.' },
  ]);

  const engineEvalTrace = createCallTrace('How the Engine Runs an Evaluator', [
    { module: 'EvaluationExecutor', func: '_compute_evaluators(inference_output)',
      file: '_engine/evaluation/evaluation_executor.py', tag: 'engine',
      detail: 'Iterates over all registered evaluators for the current experiment.' },
    { module: 'EvaluatorWrapper', func: 'compute(inference_output=output)',
      file: '_engine/decorators.py', tag: 'evaluator',
      detail: 'The @evaluator wrapper resolves field mapping via _get_mapped_fields().' },
    { module: 'BaseEvaluator', func: '_get_mapped_fields(inference_output)',
      file: '_engine/decorators.py', tag: 'data',
      detail: 'Splits mapping "target.response" into source="target", field="response" and looks up values.' },
    { module: 'UserEvaluator', func: 'compute(response=..., query=...)',
      file: 'evaluators/my_eval.py', tag: 'evaluator',
      detail: 'Your compute() receives resolved kwargs. Returns {metric_name: value}.' },
    { module: 'EvaluationExecutor', func: '_save_result(eval_output, output_path)',
      file: '_engine/evaluation/evaluation_executor.py', tag: 'engine',
      detail: 'Appends per-row result dict to JSONL output file.' },
    { module: 'EvaluationExecutor', func: '_aggregate_and_save_evaluators(output_path)',
      file: '_engine/evaluation/evaluation_executor.py', tag: 'engine',
      detail: 'After all rows: calls aggregate() on each evaluator, writes summary.' },
  ]);

  // -- Category summary table ----------------------------------

  const categoryTable = createTable(
    ['Category', 'Backend', 'Count', 'Scale', 'Requires Azure'],
    [
      ['Quality',   'Prompty (LLM-as-judge)',  '7', '1-5',  'Yes (LLM deployment)'],
      ['Agent',     'Prompty (LLM-as-judge)',  '3', '0/1-5','Yes (LLM deployment)'],
      ['Safety',    'Azure RAI Service',       '4', '0-7',  'Yes (RAI endpoint)'],
      ['Security',  'Azure RAI Service',       '4', '0-1',  'Yes (RAI endpoint)'],
      ['Reference', 'Local (algorithmic)',      '5', '0-1',  'No'],
      ['Composite', 'Multi (delegates)',        '2', 'Mixed','Depends on children'],
    ]);

  // -- ASSEMBLE evaluators section -----------------------------

  document.getElementById('evaluators').innerHTML = `
    <div class="section-hero">
      <h1>All Evaluators</h1>
      <p>Complete catalog of built-in evaluators -- class hierarchy, contracts, metrics, and backends.</p>
    </div>

    <h2>Class Hierarchy</h2>
    <p>All evaluators descend from <code>EvaluatorBase[T_EvalValue]</code>, an abstract generic base.
       Three intermediate bases provide the execution backend:</p>
    ${createInfoCard('Scroll to explore',
      'The class diagram is wide. Scroll right to see Direct implementations and Composite evaluators.',
      'tip')}
    <div style="overflow-x:auto;">${classDiagram}</div>

    <h2>Engine Evaluator Contract</h2>
    <p>The evaluation engine wraps every evaluator in a <code>BaseEvaluator</code> adapter via the
       <code>@evaluator</code> decorator. This contract requires two methods:</p>
    ${baseEvalCode}
    ${createInfoCard('compute() vs aggregate()',
      '<code>compute(**kwargs)</code> scores a single row and returns a dict. ' +
      '<code>aggregate(scores)</code> reduces all per-row dicts to summary statistics. ' +
      'The engine calls compute() in parallel via ThreadPoolExecutor, then aggregate() once at the end.',
      'info')}

    <h2>The @evaluator Decorator</h2>
    <p>The <code>@evaluator(name="...")</code> decorator wraps your class in an <code>EvaluatorWrapper</code>,
       registers it in <code>EVALUATOR_REGISTRY</code>, and handles field mapping + dependency injection:</p>
    ${decoratorCode}
    ${createInfoCard('Deployment injection',
      'The decorator auto-injects <code>deployment_name</code> from config or ' +
      '<code>cloud.default_evaluator_deployment</code>. This is how Prompty evaluators ' +
      'know which LLM to call without explicit configuration.',
      'tip')}

    <h2>Writing a Custom Evaluator</h2>
    <p>Create a Python file in your project's <code>evaluators/</code> directory. The engine auto-discovers
       files containing <code>@evaluator</code> via <code>discovery.py</code>:</p>
    ${customEvalCode}
    ${createInfoCard('Auto-discovery',
      'Place evaluator files in your project root or <code>evaluators/</code> directory. ' +
      'The CLI runs <code>_import_decorated_files()</code> which scans for files containing ' +
      '@evaluator, @target, or @dataset decorators and imports them before the run starts.',
      'info')}

    <h2>Evaluator Categories at a Glance</h2>
    ${categoryTable}

    <h2>Evaluator Catalog</h2>

    <h3>Quality Evaluators (LLM-as-judge via Prompty)</h3>
    <p>These evaluators send a rendered prompt to an LLM and parse a numeric score (typically 1-5).</p>
    <div class="metric-grid">${qualityCards}</div>

    <h3>Agent Evaluators (LLM-as-judge via Prompty)</h3>
    <p>Specialized evaluators for agentic workflows -- tool usage, intent resolution, and task completion.</p>
    <div class="metric-grid">${agentCards}</div>

    <h3>Safety Evaluators (Azure RAI Service, severity 0-7)</h3>
    <p>These evaluators call the Azure Responsible AI service backend. Severity scale: 0 = safe, 7 = extreme.</p>
    <div class="metric-grid">${safetyCards}</div>

    <h3>Security Evaluators (RAI Service, boolean)</h3>
    <p>Binary pass/fail evaluators backed by the Azure RAI service.</p>
    <div class="metric-grid">${securityCards}</div>

    <h3>Reference Metrics (Local / Algorithmic)</h3>
    <p>Classic NLP metrics computed locally -- no LLM or service call required. All produce 0-1 scores.</p>
    <div class="metric-grid">${referenceCards}</div>

    <h3>Composite Evaluators (Multi-evaluator bundles)</h3>
    <p>Convenience evaluators that run multiple sub-evaluators in a single call.</p>
    <div class="metric-grid">${compositeCards}</div>

    <h2>How Evaluator Backends Work</h2>
    ${createTabs([
      { label: 'Prompty (LLM-as-judge)', content: promptyTrace },
      { label: 'RAI Service', content: raiTrace },
      { label: 'Engine Execution', content: engineEvalTrace },
    ], 'evaluator-backends')}
  `;


  // ============================================================
  // SECTION 2: CONFIGURATION
  // ============================================================

  // -- Interactive config schema tree --------------------------

  const configSchema = createConfigSchema([
    { key: 'experiment', type: 'object', required: true,
      desc: 'Top-level experiment definition. Used in: Config.from_yaml() in models/config.py', children: [

      { key: 'name', type: 'str', required: true,
        desc: 'Experiment name. Used in: output directory naming + AITK display panel title. Passed to OutputFormatter.' },
      { key: 'version', type: 'str', default: '1.0',
        desc: 'Semantic version stamped into results metadata JSON. Used in: OutputFormatter.format() header.' },
      { key: 'description', type: 'str', default: '""',
        desc: 'Human-readable description. Used in: CLI run panel header + AITK experiment list.' },
      { key: 'output_path', type: 'str', default: '"output"',
        desc: 'Base directory for JSONL results + summaries. Used in: OutputFormatter.format() to create <output_path>/<name>/<variant>/ directories.' },
      { key: 'max_workers', type: 'int?',
        desc: 'Thread pool size. Used in: EvaluationExecutor.evaluate_model() -> ThreadPoolExecutor(max_workers=N) in evaluation_executor.py:155.' },

      { key: 'dataset', type: 'object',
        desc: 'Input data source. Used in: DatasetFactory.create() in dataset_factory.py to instantiate the correct dataset type.', children: [
        { key: 'name', type: 'str', required: true,
          desc: 'Dataset identifier. Used in: DatasetFactory lookup key and output metadata.' },
        { key: 'type', type: 'str', required: true,
          desc: '"jsonl" | "csv" | "custom". Used in: DatasetFactory routes to DATASET_REGISTRY[type]. Validated by Config.deep_validate().' },
        { key: 'version', type: 'str', default: '"1.0.0"',
          desc: 'Dataset version string. Used in: results metadata for reproducibility tracking.' },
        { key: 'args', type: 'dict',
          desc: 'Type-specific arguments. Used in: passed as **kwargs to the dataset constructor.', children: [
          { key: 'data_path', type: 'str',
            desc: 'Path to JSONL/CSV file. Used in: JsonlDataset.__init__() / CsvDataset.__init__() to open the file.' },
        ] },
      ] },

      { key: 'targets', type: 'list',
        desc: 'Target models/agents to evaluate. Used in: target_factory.py expands each into variant combinations.', children: [
        { key: '[target]', type: 'object',
          desc: 'Individual target definition. Expanded via generate_args_combinations() in combination_utils.py.', children: [
          { key: 'name', type: 'str', required: true,
            desc: 'Target identifier. Used in: output subdirectory name + results JSON key. Validated by deep_validate() against TARGET_REGISTRY for custom types.' },
          { key: 'type', type: 'str', default: '"custom"',
            desc: '"custom" | "azure_ai_model" | "azure_ai_agent". Used in: target_factory.py to select TargetWrapper, ModelTarget, or AgentTarget. Validated against _VALID_TARGET_TYPES set.' },
          { key: 'connection_name', type: 'str', default: '"default"',
            desc: 'Which connection provides the endpoint. Used in: context.connections_registry[connection_name] inside target __init__. Validated by deep_validate() against connections list.' },
          { key: 'deployment_name', type: 'str | list',
            desc: 'Model deployment(s). Used in: azure_ai_model targets. List triggers Cartesian expansion via generate_args_combinations(). Single string passed directly to model client.' },
          { key: 'prompts', type: 'list[str]', default: '[]',
            desc: 'Prompt file paths. Used in: azure_ai_model targets -- each prompt produces a separate evaluation run.' },
          { key: 'agent_name', type: 'str?',
            desc: 'For azure_ai_agent targets. Used in: AgentTarget.__init__() to identify the Foundry agent to invoke.' },
          { key: 'agent_version', type: 'str?',
            desc: 'For azure_ai_agent targets. Used in: AgentTarget pinning a specific agent version.' },
          { key: 'azure_ai_project', type: 'str?',
            desc: 'Direct project override. Used in: AgentTarget to resolve project endpoint without requiring a connection. Falls back to cloud.foundry_project.' },
          { key: 'instructions', type: 'str?',
            desc: 'Agent system instructions. Used in: AgentTarget passes to agent invocation payload.' },
          { key: 'args', type: 'dict | list[dict]',
            desc: 'Parameter variants. Used in: generate_args_combinations() in combination_utils.py computes Cartesian product. Dict auto-normalized to [dict] by TargetVariantConfig.normalize_args().', children: [
            { key: 'system_prompt', type: 'str | list',
              desc: 'Prompt variants. List values expand via Cartesian product.' },
            { key: 'temperature', type: 'float | list',
              desc: 'Temperature variants. List values expand via Cartesian product.' },
          ] },
          { key: 'input_mapping', type: 'dict',
            desc: 'Maps target params to dataset fields. Format: {param: "dataset.field"}. Used in: target invocation -- infer() receives mapped values. Validated by validate_input_mapping_format().' },
        ] },
      ] },

      { key: 'evaluators', type: 'list',
        desc: 'Evaluators to run on each (target x row). Used in: EvaluationExecutor instantiates from EVALUATOR_REGISTRY.', children: [
        { key: '[evaluator]', type: 'object',
          desc: 'Individual evaluator config. Used in: @evaluator decorator wrapper constructor.', children: [
          { key: 'name', type: 'str', required: true,
            desc: 'Must match a registry key. Used in: EVALUATOR_REGISTRY[name] lookup. Validated by deep_validate() against registry + BUILTIN_EVALUATORS.' },
          { key: 'display_name', type: 'str?',
            desc: 'Human-friendly name. Used in: OutputFormatter column headers + AITK metric display.' },
          { key: 'deployment_name', type: 'str?',
            desc: 'Override LLM deployment. Used in: EvaluatorWrapper.__init__() -- takes precedence over cloud.default_evaluator_deployment for this evaluator only.' },
          { key: 'mapping', type: 'dict',
            desc: 'Field mapping: {param: "target.X" or "dataset.X"}. Used in: BaseEvaluator._get_mapped_fields() during _compute_evaluators(). Validated by EvaluatorConfig.validate_mapping_format() with regex ^(target|dataset)\\.[^.]+$.' },
        ] },
      ] },

      { key: 'compute', type: 'object?',
        desc: 'Backend selection. Used in: ExperimentRunner._select_backend() in runner.py:77 to choose Local vs Foundry compute.', children: [
        { key: 'type', type: 'str', default: '"local"',
          desc: '"local" or "foundry". Used in: _select_backend() branch logic. "local" uses ThreadPoolExecutor, "foundry" delegates to FoundryCompute.' },
        { key: 'azure_ai_project', type: 'str?',
          desc: 'Foundry project endpoint URL. Used in: FoundryCompute.__init__() to connect to remote evaluation service.' },
      ] },

      { key: 'cloud', type: 'object?',
        desc: 'Azure cloud configuration. Used in: ExecutionContext.cloud_config -- injected into evaluator/target constructors.', children: [
        { key: 'foundry_endpoint', type: 'str', default: '""',
          desc: 'Azure OpenAI endpoint URL. Used in: @evaluator wrapper injects as azure_endpoint param. Also used by ModelTarget for inference calls.' },
        { key: 'foundry_project', type: 'str?',
          desc: 'Azure AI Foundry project URL. Used in: AgentTarget project resolution fallback when target.azure_ai_project is not set.' },
        { key: 'default_evaluator_deployment', type: 'str', default: '"gpt-4.1-mini"',
          desc: 'Default LLM for evaluators. Used in: @evaluator wrapper -- cloud.default_evaluator_deployment passed as deployment_name to inner evaluator class unless overridden by evaluator-level deployment_name.' },
        { key: 'app_insights', type: 'str?',
          desc: 'Application Insights connection string. Used in: trace exporter setup for telemetry (TBD).' },
      ] },

      { key: 'connections', type: 'list',
        desc: 'Named connection definitions. Used in: ExperimentConfig.normalize_config() converts dict format to list. Stored in ExecutionContext.connections_registry dict.', children: [
        { key: '[connection]', type: 'object',
          desc: 'Individual connection. Used in: context.connections_registry[name] -- direct dict lookup in target/evaluator code.', children: [
          { key: 'name', type: 'str', required: true,
            desc: 'Connection identifier. Used in: target.connection_name references this. Validated by deep_validate() cross-reference check.' },
          { key: '...', type: 'any',
            desc: 'Extra fields (api_key, endpoint, etc.). ConfigDict(extra="allow") permits arbitrary keys. Accessed via context.connections_registry[name] dict lookup.' },
        ] },
      ] },

    ] },
  ]);

  // -- Environment variable interpolation ----------------------

  const envVarCode = createCodeBlock(
`# Environment variable interpolation patterns in YAML config

# Required -- raises error if AZURE_OPENAI_ENDPOINT is not set
foundry_endpoint: "\${AZURE_OPENAI_ENDPOINT}"

# With default fallback -- uses gpt-4.1-mini if AZURE_DEPLOYMENT is unset or empty
deployment: "\${AZURE_DEPLOYMENT:-gpt-4.1-mini}"

# Only if completely unset (empty string is kept)
api_key: "\${API_KEY-}"`, 'yaml', { title: 'Environment Variable Patterns' });

  const envVarRegex = createCodeBlock(
`# Regex from models/config.py line 13 -- used by _resolve_env_vars()
_ENV_VAR_PATTERN = re.compile(
    r"\\$\\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?:(?P<op>:-|-)(?P<arg>.*?))?"
    r"\\}"
)

def _resolve_env_vars(value: str) -> str:
    """Replace \${VAR}, \${VAR:-default}, \${VAR-default} in config values."""
    def _replace(m):
        name = m.group("name")
        op = m.group("op")
        arg = m.group("arg") or ""

        is_set = name in os.environ
        v = os.environ.get(name, "")

        if op is None:                      # \${VAR}
            if not is_set:
                raise ValueError(f"Missing required env var: {name}")
            return v
        if op == ":-":                      # \${VAR:-default}
            return v if (is_set and v != "") else arg
        if op == "-":                       # \${VAR-default}
            return v if is_set else arg

        return m.group(0)

    return _ENV_VAR_PATTERN.sub(_replace, value)


def _interpolate_env_vars(value):
    """Recursively interpolate env vars in config structure."""
    if isinstance(value, str):
        return _resolve_env_vars(value)
    if isinstance(value, dict):
        return {k: _interpolate_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate_env_vars(item) for item in value]
    return value`, 'python', {
    filePath: 'azure/ai/evaluation/_engine/models/config.py',
    title: 'Config Environment Resolution'
  });

  // -- Cartesian product expansion -----------------------------

  const cartesianYaml = createCodeBlock(
`targets:
  - name: "qa_model"
    type: "azure_ai_model"
    deployment_name: ["gpt-4.1-mini", "gpt-4.1"]   # 2 values
    args:
      - system_prompt:                                # 2 values
          - "Be concise"
          - "Be thorough"
        temperature: [0.3, 0.9]                       # 2 values
    # Total: 2 x 2 x 2 = 8 target variants`, 'yaml', { title: 'Cartesian Product Config' });

  const cartesianTable = createTable(
    ['Variant', 'deployment_name', 'system_prompt', 'temperature'],
    [
      ['1', '<code>gpt-4.1-mini</code>', '<code>Be concise</code>',  '<code>0.3</code>'],
      ['2', '<code>gpt-4.1-mini</code>', '<code>Be concise</code>',  '<code>0.9</code>'],
      ['3', '<code>gpt-4.1-mini</code>', '<code>Be thorough</code>', '<code>0.3</code>'],
      ['4', '<code>gpt-4.1-mini</code>', '<code>Be thorough</code>', '<code>0.9</code>'],
      ['5', '<code>gpt-4.1</code>',      '<code>Be concise</code>',  '<code>0.3</code>'],
      ['6', '<code>gpt-4.1</code>',      '<code>Be concise</code>',  '<code>0.9</code>'],
      ['7', '<code>gpt-4.1</code>',      '<code>Be thorough</code>', '<code>0.3</code>'],
      ['8', '<code>gpt-4.1</code>',      '<code>Be thorough</code>', '<code>0.9</code>'],
    ]);

  const cartesianCode = createCodeBlock(
`# combination_utils.py -- called from target_factory.py line 427
def generate_args_combinations(model_cfg: TargetVariantConfig) -> List[Dict[str, Any]]:
    """Compute Cartesian product of all list-valued args."""
    args_list = model_cfg.args  # Already normalized to list[dict]
    all_combos = []
    for args_dict in args_list:
        keys, value_lists = [], []
        for k, v in args_dict.items():
            keys.append(k)
            value_lists.append(v if isinstance(v, list) else [v])
        for combo in itertools.product(*value_lists):
            all_combos.append(dict(zip(keys, combo)))

    # Also expand deployment_name if it is a list
    if isinstance(model_cfg.deployment_name, list):
        expanded = []
        for deploy in model_cfg.deployment_name:
            for combo in all_combos:
                expanded.append({**combo, "deployment_name": deploy})
        return expanded
    return all_combos`, 'python', {
    filePath: 'azure/ai/evaluation/_engine/combination_utils.py',
    title: 'Cartesian Expansion Logic'
  });

  // -- Evaluator mapping deep dive -----------------------------

  const mappingCode = createCodeBlock(
`evaluators:
  - name: "relevance"
    mapping:
      query: "dataset.question"       # maps evaluator param "query" to dataset column "question"
      response: "target.response"     # maps "response" to target output field "response"

  - name: "groundedness"
    mapping:
      query: "dataset.question"
      response: "target.response"
      context: "dataset.context"      # ground truth context from dataset

  - name: "f1_score"
    mapping:
      response: "target.response"
      ground_truth: "dataset.answer"  # reference answer from dataset`, 'yaml', { title: 'Evaluator Mapping Examples' });

  const mappingResolution = createCodeBlock(
`# From decorators.py -- BaseEvaluator._get_mapped_fields()
def _get_mapped_fields(self, inference_output):
    data = inference_output.to_dict()
    output = data.get("output", {})
    sources = {
        "model": output,
        "target": output,              # "target.X" and "model.X" both resolve to output
        "dataset": data.get("record", {}),  # "dataset.X" resolves to input row
    }
    mapped_fields = {}
    for param, mapping in self.mapping.items():
        source, field = mapping.split(".", 1)
        value = sources.get(source, {}).get(field)
        if value is None:
            if field in ("tool_definitions", "tool_calls"):
                mapped_fields[param] = []  # Optional agent fields default to []
            else:
                raise KeyError(f"Field '{field}' not found in '{source}'")
        else:
            mapped_fields[param] = value
    return mapped_fields`, 'python', {
    filePath: 'azure/ai/evaluation/_engine/decorators.py',
    title: 'Mapping Resolution Logic'
  });

  const mappingValidation = createCodeBlock(
`# From models/config.py -- EvaluatorConfig.validate_mapping_format()
@model_validator(mode="after")
def validate_mapping_format(self) -> "EvaluatorConfig":
    """Validate mapping values match 'target.X' or 'dataset.X' format."""
    if self.mapping:
        pattern = re.compile(r"^(target|dataset)\\.[^.]+$")
        for field, mapping_val in self.mapping.items():
            if not pattern.match(mapping_val):
                raise ValueError(
                    f"Invalid mapping '{mapping_val}' for field '{field}' "
                    f"in evaluator '{self.name}': "
                    f"expected format 'target.X' or 'dataset.X'"
                )
    return self`, 'python', {
    filePath: 'azure/ai/evaluation/_engine/models/config.py',
    title: 'Mapping Validation (Pydantic)'
  });

  // -- Config loading flow -------------------------------------

  const configLoadTrace = createCallTrace('How Config Loading Works', [
    { module: 'Config', func: 'from_yaml(path)',
      file: '_engine/models/config.py', tag: 'engine',
      detail: 'Opens and reads the YAML file using yaml.safe_load().' },
    { module: 'config', func: '_interpolate_env_vars(data)',
      file: '_engine/models/config.py', tag: 'engine',
      detail: 'Recursively walks the dict/list tree and replaces ${VAR} patterns with environment values.' },
    { module: 'Config', func: 'cls(**data) -> Pydantic validation',
      file: '_engine/models/config.py', tag: 'data',
      detail: 'Pydantic parses into Config -> ExperimentConfig -> nested models. Type validation + normalize_args() + validate_mapping_format() run here.' },
    { module: 'Config', func: 'deep_validate()',
      file: '_engine/models/config.py', tag: 'engine',
      detail: 'Cross-references targets, evaluators, datasets against registries. Checks connection_name references exist.' },
    { module: 'ExperimentRunner', func: 'run(config)',
      file: '_engine/runner.py', tag: 'engine',
      detail: 'Calls _select_backend() using compute.type, then dispatches to Local or Foundry backend.' },
  ]);

  // -- Validation deep_validate flow ---------------------------

  const deepValidateCode = createCodeBlock(
`def deep_validate(self) -> List[str]:
    """Validate config against registered components."""
    from ..decorators import DATASET_REGISTRY, EVALUATOR_REGISTRY, TARGET_REGISTRY
    from ..dataset_factory import _ensure_builtin_datasets
    _ensure_builtin_datasets()

    errors = []
    exp = self.experiment

    # 1. Custom target names must exist in TARGET_REGISTRY
    for target_cfg in exp.targets:
        if target_cfg.type == "custom" and target_cfg.name not in TARGET_REGISTRY:
            errors.append(f"Target '{target_cfg.name}' not found in registry")

    # 2. Evaluator names must exist in EVALUATOR_REGISTRY or BUILTIN_EVALUATORS
    builtin_names = {name for name, _, _ in BUILTIN_EVALUATORS}
    for eval_cfg in exp.evaluators:
        if eval_cfg.name not in EVALUATOR_REGISTRY and eval_cfg.name not in builtin_names:
            errors.append(f"Evaluator '{eval_cfg.name}' not found in registry")

    # 3. Dataset type must exist in DATASET_REGISTRY
    if exp.dataset and exp.dataset.type not in DATASET_REGISTRY:
        errors.append(f"Dataset type '{exp.dataset.type}' not found")

    # 4. Connection references for non-custom targets
    conn_names = {c.name for c in exp.connections if hasattr(c, "name")}
    for target_cfg in exp.targets:
        if target_cfg.type != "custom":
            if target_cfg.connection_name not in conn_names:
                # ... check cloud.foundry_project fallback for agents
                errors.append(f"Connection '{target_cfg.connection_name}' not defined")

    return errors`, 'python', {
    filePath: 'azure/ai/evaluation/_engine/models/config.py',
    title: 'deep_validate() Cross-Reference Checks'
  });

  // -- Three complete config examples --------------------------

  const quickstartConfig = createCodeBlock(
`experiment:
  name: "quickstart-local"                    # Output: output/quickstart/
  version: "1.0"                              # Stamped in results metadata
  description: "Minimal local evaluation"     # Shown in CLI panel
  output_path: "output/quickstart"            # OutputFormatter base dir

  dataset:
    name: "qa_pairs"                          # DatasetFactory lookup key
    type: "jsonl"                             # Routes to JsonlDataset
    args:
      data_path: "data/qa_samples.jsonl"      # Passed to JsonlDataset.__init__()

  evaluators:
    - name: "f1_score"                        # EVALUATOR_REGISTRY["f1_score"]
      mapping:
        response: "dataset.response"          # _get_mapped_fields -> record["response"]
        ground_truth: "dataset.expected"      # _get_mapped_fields -> record["expected"]

    - name: "bleu_score"
      mapping:
        response: "dataset.response"
        ground_truth: "dataset.expected"

    - name: "rouge_score"
      mapping:
        response: "dataset.response"
        ground_truth: "dataset.expected"`, 'yaml', { title: 'quickstart.yaml -- Local Only' });

  const modelCompareConfig = createCodeBlock(
`experiment:
  name: "model-comparison"
  version: "2.0"
  description: "Compare GPT-4.1-mini vs GPT-4.1 across prompts"
  output_path: "output/model-compare"
  max_workers: 8                              # ThreadPoolExecutor(max_workers=8)

  dataset:
    name: "eval_questions"
    type: "jsonl"
    args:
      data_path: "data/eval_questions.jsonl"

  targets:
    - name: "qa_model"
      type: "azure_ai_model"                  # target_factory -> ModelTarget
      deployment_name:                        # List -> Cartesian expansion
        - "gpt-4.1-mini"
        - "gpt-4.1"
      args:
        - system_prompt:                      # List -> Cartesian expansion
            - "Answer concisely in 1-2 sentences."
            - "Give a thorough, detailed answer."
          temperature: [0.3, 0.7]             # List -> Cartesian expansion
      # Total: 2 x 2 x 2 = 8 variants via generate_args_combinations()
      input_mapping:
        query: "dataset.question"             # infer(query=row["question"])
        context: "dataset.context"            # infer(context=row["context"])

  evaluators:
    - name: "coherence"                       # Prompty evaluator (1-5 scale)
      mapping:
        query: "dataset.question"
        response: "target.response"           # From ModelTarget.infer() output

    - name: "relevance"
      mapping:
        query: "dataset.question"
        response: "target.response"

    - name: "groundedness"
      mapping:
        query: "dataset.question"
        response: "target.response"
        context: "dataset.context"

    - name: "f1_score"                        # Local evaluator (0-1 scale)
      mapping:
        response: "target.response"
        ground_truth: "dataset.expected"

  cloud:
    foundry_endpoint: "\${AZURE_OPENAI_ENDPOINT}"  # Required env var
    default_evaluator_deployment: "gpt-4.1-mini"   # Used by Prompty evaluators`, 'yaml', { title: 'model-compare.yaml -- Cartesian Sweep' });

  const agentConfig = createCodeBlock(
`experiment:
  name: "agent-evaluation"
  version: "1.0"
  description: "Evaluate an Azure AI Agent with tool usage"
  output_path: "output/agent-eval"

  dataset:
    name: "agent_tasks"
    type: "jsonl"
    args:
      data_path: "data/agent_tasks.jsonl"

  targets:
    - name: "support_agent"
      type: "azure_ai_agent"                  # target_factory -> AgentTarget
      agent_name: "customer-support-agent"    # AgentTarget.__init__(agent_name=...)
      connection_name: "foundry"              # context.connections_registry["foundry"]
      input_mapping:
        query: "dataset.user_query"

  evaluators:
    - name: "tool_call_accuracy"              # Prompty evaluator for agents
      mapping:
        query: "dataset.user_query"
        response: "target.response"
        tool_calls: "target.tool_calls"       # From agent trace
        tool_definitions: "target.tool_definitions"

    - name: "task_adherence"
      mapping:
        query: "dataset.user_query"
        response: "target.response"

    - name: "intent_resolution"
      mapping:
        query: "dataset.user_query"
        response: "target.response"

    - name: "violence"                        # RAI safety evaluator
      mapping:
        query: "dataset.user_query"
        response: "target.response"

  cloud:
    foundry_endpoint: "\${AZURE_OPENAI_ENDPOINT}"
    foundry_project: "\${AZURE_AI_PROJECT}"   # Fallback for agent project resolution
    default_evaluator_deployment: "gpt-4.1-mini"

  connections:
    - name: "foundry"                         # Referenced by target.connection_name
      endpoint: "\${AZURE_AI_PROJECT}"
      api_key: "\${AZURE_AI_API_KEY-}"        # Default: empty string if unset`, 'yaml', { title: 'agent-eval.yaml -- Agent + Safety' });

  const configExampleTabs = createTabs([
    { label: 'Quickstart (Local)', content:
      `<p>Minimal config for local-only evaluation using reference metrics. No Azure connection needed.</p>${quickstartConfig}` },
    { label: 'Model Comparison', content:
      `<p>Compare two models x two prompts x two temperatures = 8 target variants with quality evaluators.</p>${modelCompareConfig}` },
    { label: 'Agent Evaluation', content:
      `<p>Evaluate an Azure AI Agent with tool-call and task-adherence evaluators plus safety checks.</p>${agentConfig}` },
  ], 'config-examples');

  // -- Config field usage summary table ------------------------

  const fieldUsageTable = createTable(
    ['Config Field', 'Engine Location', 'What It Controls'],
    [
      ['<code>experiment.name</code>', '<code>OutputFormatter</code>', 'Output directory name + experiment display title'],
      ['<code>experiment.max_workers</code>', '<code>EvaluationExecutor.evaluate_model()</code>', '<code>ThreadPoolExecutor(max_workers=N)</code> for record-level parallelism'],
      ['<code>experiment.output_path</code>', '<code>OutputFormatter.format()</code>', 'Base directory for JSONL results and summary files'],
      ['<code>dataset.type</code>', '<code>DatasetFactory.create()</code>', 'Routes to <code>DATASET_REGISTRY[type]</code>'],
      ['<code>targets[].type</code>', '<code>target_factory.py</code>', 'Selects TargetWrapper / ModelTarget / AgentTarget'],
      ['<code>targets[].args</code>', '<code>generate_args_combinations()</code>', 'Cartesian product expansion into N variants'],
      ['<code>targets[].input_mapping</code>', '<code>target.infer()</code>', 'Renames dataset fields before passing to infer()'],
      ['<code>evaluators[].name</code>', '<code>EVALUATOR_REGISTRY[name]</code>', 'Instantiates the evaluator class from registry'],
      ['<code>evaluators[].mapping</code>', '<code>BaseEvaluator._get_mapped_fields()</code>', 'Resolves "target.X" / "dataset.X" to actual values'],
      ['<code>evaluators[].deployment_name</code>', '<code>@evaluator wrapper __init__</code>', 'Overrides <code>cloud.default_evaluator_deployment</code> for this evaluator'],
      ['<code>compute.type</code>', '<code>ExperimentRunner._select_backend()</code>', '"local" -> ThreadPoolExecutor, "foundry" -> FoundryCompute'],
      ['<code>cloud.foundry_endpoint</code>', '<code>@evaluator wrapper</code>', 'Injected as <code>azure_endpoint</code> into evaluator constructors'],
      ['<code>cloud.default_evaluator_deployment</code>', '<code>@evaluator wrapper __init__</code>', 'Default LLM deployment for all Prompty evaluators'],
      ['<code>cloud.foundry_project</code>', '<code>AgentTarget</code>', 'Fallback project URL when target.azure_ai_project is not set'],
      ['<code>connections[].name</code>', '<code>context.connections_registry[name]</code>', 'Looked up by target.connection_name via direct dict access on ExecutionContext'],
    ]);

  // -- Config lifecycle sequence diagram -----------------------

  const configSequence = createSequenceDiagram('Config Loading and Validation Lifecycle', [
    { id: 'user', label: 'User' },
    { id: 'cli', label: 'CLI' },
    { id: 'config', label: 'Config' },
    { id: 'pydantic', label: 'Pydantic' },
    { id: 'runner', label: 'ExperimentRunner' },
    { id: 'executor', label: 'EvaluationExecutor' },
  ], [
    { from: 'user', to: 'cli', label: 'ev run config.yaml' },
    { from: 'cli', to: 'config', label: 'Config.from_yaml(path)' },
    { from: 'config', to: 'config', label: '_interpolate_env_vars()' },
    { from: 'config', to: 'pydantic', label: 'Validate + normalize' },
    { from: 'pydantic', to: 'config', label: 'Config instance' },
    { from: 'config', to: 'config', label: 'deep_validate()' },
    { from: 'cli', to: 'runner', label: 'runner.run(config)' },
    { from: 'runner', to: 'runner', label: '_select_backend(compute.type)' },
    { from: 'runner', to: 'executor', label: 'execute(dataset, targets, evaluators)' },
    { from: 'executor', to: 'executor', label: 'ThreadPoolExecutor(max_workers)' },
  ]);

  // -- ASSEMBLE configuration section --------------------------

  document.getElementById('configuration').innerHTML = `
    <div class="section-hero">
      <h1>Configuration Reference</h1>
      <p>Complete schema for experiment YAML configs -- every field, type, default, and where it is used in the engine.</p>
    </div>

    <h2>Config Loading Lifecycle</h2>
    <p>Understanding how your YAML config flows through the engine:</p>
    ${configSequence}
    ${configLoadTrace}

    <h2>Full Config Schema</h2>
    <p>Interactive tree of all configuration options. Click nodes to expand/collapse.
       Each field shows where it is consumed in the engine codebase.</p>
    <div class="schema-tree">${configSchema}</div>

    <h2>Config Field Usage Map</h2>
    <p>Quick reference: which engine module consumes each config field.</p>
    ${fieldUsageTable}
    ${createInfoCard('How to read this table',
      'The "Engine Location" column shows the class and method where the config value is ' +
      'first consumed. Follow the code path from Config.from_yaml() through ExperimentRunner ' +
      'to EvaluationExecutor to see how each field propagates.',
      'info')}

    <h2>Environment Variable Interpolation</h2>
    <p>Config values can reference environment variables using <code>\${VAR}</code> syntax.
       Interpolation happens in <code>Config.from_yaml()</code> before Pydantic validation.</p>
    ${envVarCode}
    ${createInfoCard('Three patterns',
      '<code>\${VAR}</code> -- required, raises ValueError if missing. ' +
      '<code>\${VAR:-default}</code> -- uses default if VAR is unset or empty. ' +
      '<code>\${VAR-default}</code> -- uses default only if VAR is completely unset.',
      'info')}
    <p>Implementation from <code>models/config.py</code>:</p>
    ${envVarRegex}

    <h2>Cartesian Product Expansion</h2>
    <p>When target fields are <strong>lists</strong>, the engine computes the Cartesian product
       via <code>generate_args_combinations()</code> in <code>combination_utils.py</code>,
       called from <code>target_factory.py</code>:</p>
    ${cartesianYaml}
    ${createInfoCard('Expansion math',
      '2 deployments x 2 prompts x 2 temperatures = <strong>8 target variants</strong>. ' +
      'Each variant is evaluated independently against every dataset row.',
      'tip')}
    <p>The 8 generated variants:</p>
    ${cartesianTable}
    <p>Here is the expansion logic:</p>
    ${cartesianCode}

    <h2>Evaluator Mapping</h2>
    <p>The <code>mapping</code> field tells each evaluator where to find its inputs.
       Use <code>dataset.X</code> to reference a dataset column, or <code>target.X</code>
       for a target output field.</p>
    ${mappingCode}
    ${createInfoCard('Mapping validation',
      'Mapping values are validated at config load time by ' +
      '<code>EvaluatorConfig.validate_mapping_format()</code> using the regex ' +
      '<code>^(target|dataset)\\.[^.]+$</code>. Invalid patterns cause an immediate error.',
      'warning')}
    <p>At runtime, <code>_get_mapped_fields()</code> resolves the mappings:</p>
    ${mappingResolution}
    <p>The Pydantic validator that enforces the format:</p>
    ${mappingValidation}

    <h2>Config Validation</h2>
    <p><code>deep_validate()</code> cross-references your config against the component registries
       to catch errors before the run starts:</p>
    ${deepValidateCode}
    ${createInfoCard('When is deep_validate() called?',
      'The CLI calls deep_validate() after all components are imported (via auto-discovery) ' +
      'but before the experiment starts. This catches typos in evaluator names, missing connections, ' +
      'and unregistered target types early with clear error messages.',
      'info')}

    <h2>Complete Config Examples</h2>
    <p>Three real-world configurations from simple to complex. Inline comments show where each field is used:</p>
    ${configExampleTabs}
  `;
}

// -- Bootstrap -------------------------------------------------
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initEvalConfigContent);
} else {
  initEvalConfigContent();
}
