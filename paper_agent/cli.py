import asyncio

import click


@click.group()
def cli():
    """The command line interface for the paper writing agent."""
    pass


@cli.command()
@click.option(
    "--research_field",
    default="vq",
    help="The research field (e.g. vq, gnn, rec, diffu_flow).",
)
@click.option(
    "--instance_id",
    default="rotation_vq",
    help="The instance identifier for the paper.",
)
def write(research_field: str, instance_id: str):
    """Generate a full academic paper for the given research field and instance."""
    from paper_agent.writing import writing

    asyncio.run(writing(research_field, instance_id))
