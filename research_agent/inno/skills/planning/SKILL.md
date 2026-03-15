# planning

## Name
planning

## Version
0.1.0

## Description
Plan the components of a machine learning research project: dataset
preparation, model architecture, training pipeline, and testing strategy.

## Author
HKUDS

## Tools
- plan_dataset
- plan_model
- plan_training
- plan_testing

## Tags
- research
- planning
- ml
- experiment

## Parameters
```json
{
  "plan_dataset": {
    "type": "object",
    "properties": {
      "description": {"type": "string", "description": "Dataset preparation plan"}
    },
    "required": ["description"]
  },
  "plan_model": {
    "type": "object",
    "properties": {
      "description": {"type": "string", "description": "Model architecture plan"}
    },
    "required": ["description"]
  },
  "plan_training": {
    "type": "object",
    "properties": {
      "description": {"type": "string", "description": "Training pipeline plan"}
    },
    "required": ["description"]
  },
  "plan_testing": {
    "type": "object",
    "properties": {
      "description": {"type": "string", "description": "Testing strategy plan"}
    },
    "required": ["description"]
  }
}
```

## Instructions
Use the planning tools to structure your ML experiment:
- `plan_dataset`: Define dataset loading, preprocessing, and dataloader steps.
- `plan_model`: Specify model inputs, outputs, and key architectural components.
- `plan_training`: Configure training pipeline, loss, optimizer, and monitoring.
- `plan_testing`: Set up test metrics, data, and evaluation code.
Call these tools in order after surveying the codebase.
