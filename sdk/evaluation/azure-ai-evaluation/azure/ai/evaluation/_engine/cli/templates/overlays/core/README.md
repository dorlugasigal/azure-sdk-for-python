# {project_name}

{description}

## Quick Start

1. **Configure credentials**

   ```bash
   cp .env.sample .env
   # Edit .env with your Azure OpenAI credentials
   ```

2. **Install dependencies**

   ```bash
   uv sync
   ```

3. **Run evaluation**

   ```bash
   ev run
   ```

## Project Structure

```text
.
├── config.yaml              # Experiment configuration
├── data/                    # Your evaluation dataset
├── targets/                 # Your target implementations
│   └── baseline.py          # Example baseline target
├── evaluators/              # Your custom evaluators
│   └── word_count.py        # Example custom evaluator
└── .env                     # Credentials (not committed)
```

## Configuration

Edit `config.yaml` to configure:

- Target parameters and variations
- Evaluation metrics
- Dataset location

## Next Steps

1. Add your evaluation data to `data/`
2. Implement your target in `targets/baseline.py`
3. Create custom evaluators in `evaluators/`
4. Run evaluations with `ev run`
